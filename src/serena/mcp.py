"""
The Serena Model Context Protocol (MCP) Server
"""

import sys
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from logging import Formatter, Logger, StreamHandler
from pathlib import Path
from typing import Any, Literal

import click  # Add click import
import docstring_parser
from mcp.server.fastmcp import server
from mcp.server.fastmcp.server import FastMCP, Settings
from mcp.server.fastmcp.tools.base import Tool as MCPTool
from mcp.server.fastmcp.utilities.func_metadata import func_metadata
from sensai.util import logging
from sensai.util.helper import mark_used

from serena.agent import SerenaAgent, Tool, show_fatal_exception_safe
from serena.config import SerenaAgentContext, SerenaAgentMode, init_user_config
from serena.constants import DEFAULT_CONTEXT, DEFAULT_MODES

log = logging.getLogger(__name__)
LOG_FORMAT = "%(levelname)-5s %(asctime)-15s %(name)s:%(funcName)s:%(lineno)d - %(message)s"
LOG_LEVEL = logging.INFO


def configure_logging(*args, **kwargs) -> None:  # type: ignore
    # configure logging to stderr (will be captured by Claude Desktop); stdio is the MCP communication stream and cannot be used!
    Logger.root.setLevel(LOG_LEVEL)
    handler = StreamHandler(stream=sys.stderr)
    handler.formatter = Formatter(LOG_FORMAT)
    Logger.root.addHandler(handler)


# patch the logging configuration function in fastmcp, because it's hard-coded and broken
server.configure_logging = configure_logging


@dataclass
class SerenaMCPRequestContext:
    agent: SerenaAgent


def make_tool(
    tool: Tool,
) -> MCPTool:
    func_name = tool.get_name()

    apply_fn = getattr(tool, "apply")
    if apply_fn is None:
        raise ValueError(f"Tool does not have an apply method: {tool}")

    func_doc = apply_fn.__doc__ or ""
    is_async = False

    func_arg_metadata = func_metadata(apply_fn)
    parameters = func_arg_metadata.arg_model.model_json_schema()

    docstring = docstring_parser.parse(func_doc)

    # Mount the tool description as a combination of the docstring description and
    # the return value description, if it exists.
    if docstring.description:
        func_doc = f"{docstring.description.strip().strip('.')}."
    else:
        func_doc = ""
    if (docstring.returns) and (docstring_returns := docstring.returns.description):
        # Only add a space before "Returns" if func_doc is not empty
        prefix = " " if func_doc else ""
        func_doc = f"{func_doc}{prefix}Returns {docstring_returns.strip().strip('.')}."

    # Parse the parameter descriptions from the docstring and add pass its description
    # to the parameters schema.
    docstring_params = {param.arg_name: param for param in docstring.params}
    parameters_properties: dict[str, dict[str, Any]] = parameters["properties"]
    for parameter, properties in parameters_properties.items():
        if (param_doc := docstring_params.get(parameter)) and (param_doc.description):
            param_desc = f"{param_doc.description.strip().strip('.') + '.'}"
            properties["description"] = param_desc[0].upper() + param_desc[1:]

    def execute_fn(**kwargs) -> str:  # type: ignore
        return tool.apply_ex(log_call=True, catch_exceptions=True, **kwargs)

    return MCPTool(
        fn=execute_fn,
        name=func_name,
        description=func_doc,
        parameters=parameters,
        fn_metadata=func_arg_metadata,
        is_async=is_async,
        context_kwarg=None,
    )


def create_mcp_server_and_agent(
    project: str | None,
    host: str = "0.0.0.0",
    port: int = 8000,
    context: str = DEFAULT_CONTEXT,
    modes: Sequence[str] = DEFAULT_MODES,
    enable_web_dashboard: bool | None = None,
    enable_gui_log_window: bool | None = None,
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None,
    trace_lsp_communication: bool | None = None,
) -> tuple[FastMCP, SerenaAgent]:
    """
    Create an MCP server.

    :param project: "Either an absolute path to the project directory or a name of an already registered project. "
        "If the project passed here hasn't been registered yet, it will be registered automatically and can be activated by its name "
        "afterwards.
    :param host: The host to bind to
    :param port: The port to bind to
    :param context: The context name or path to context file
    :param modes: List of mode names or paths to mode files
    :param enable_web_dashboard: Whether to enable the web dashboard. If not specified, will take the value from the serena configuration.
    :param enable_gui_log_window: Whether to enable the GUI log window. It currently does not work on macOS, and setting this to True will be ignored then.
        If not specified, will take the value from the serena configuration.
    :param log_level: Log level. If not specified, will take the value from the serena configuration.
    :param trace_lsp_communication: Whether to trace the communication between Serena and the language servers.
        This is useful for debugging language server issues.
    """
    # Initialize user configuration before anything else
    init_user_config()

    mcp: FastMCP | None = None
    context_instance = SerenaAgentContext.load(context)
    modes_instances = [SerenaAgentMode.load(mode) for mode in modes]

    try:
        agent = SerenaAgent(
            project=project,
            # Callback disabled for the time being (see above)
            # project_activation_callback=update_tools
            context=context_instance,
            modes=modes_instances,
            enable_web_dashboard=enable_web_dashboard,
            enable_gui_log_window=enable_gui_log_window,
            log_level=log_level,
            trace_lsp_communication=trace_lsp_communication,
        )
    except Exception as e:
        show_fatal_exception_safe(e)
        raise

    def update_tools() -> None:
        """Update the tools in the MCP server."""
        # Tools may change as a result of project activation.
        # NOTE: While we could pass updated tool information on to the MCP server via the callback, Claude Desktop does not,
        # unfortunately, query for changed tools. It only queries for changed resources and prompts regularly,
        # so we need to register all tools at startup, unfortunately.
        nonlocal mcp, agent
        tools = agent.get_exposed_tool_instances()
        if mcp is not None:
            mcp._tool_manager._tools = {}
            for tool in tools:
                # noinspection PyProtectedMember
                mcp._tool_manager._tools[tool.get_name()] = make_tool(tool)

    @asynccontextmanager
    async def server_lifespan(mcp_server: FastMCP) -> AsyncIterator[None]:
        """Manage server startup and shutdown lifecycle."""
        nonlocal agent
        mark_used(mcp_server)
        yield
        if agent.language_server is not None:
            agent.language_server.stop()

    mcp_settings = Settings(lifespan=server_lifespan, host=host, port=port)
    mcp = FastMCP(**mcp_settings.model_dump())

    update_tools()

    return mcp, agent


class ProjectType(click.ParamType):
    name = "[PROJECT_NAME|PROJECT_PATH]"

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> str:
        path = Path(value).resolve()
        if path.exists() and path.is_dir():
            return str(path)  # Valid path
        return value  # Assume it's a project name


PROJECT_TYPE = ProjectType()


@click.command()
@click.option(
    "--project",
    "project_file_opt",
    type=PROJECT_TYPE,
    default=None,
    help="Either an absolute path to the project directory or a name of an already registered project. "
    "If the project passed here hasn't been registered yet, it will be registered automatically and can be activated by its name afterwards.",
)
# Keep --project-file for backwards compatibility
@click.option(
    "--project-file",
    "project_file_opt",  # Use same destination variable to avoid conflicts
    type=PROJECT_TYPE,
    default=None,
    help="[DEPRECATED] Use --project instead.",
)
# Positional argument for backwards compatibility
@click.argument(
    "project_file_arg",
    type=PROJECT_TYPE,
    required=False,
    default=None,
    metavar="",  # don't display anything since it's deprecated
)
@click.option(
    "--context",
    type=str,
    show_default=True,
    default=DEFAULT_CONTEXT,
    help="Context to use. This can be a name of a built-in context ('desktop-app', 'agent', 'ide-assistant') "
    "or a path to a custom context YAML file.",
)
@click.option(
    "--mode",
    "modes",
    type=str,
    multiple=True,
    default=DEFAULT_MODES,
    show_default=True,
    help="Mode(s) to use. This can be names of built-in modes ('planning', 'editing', 'one-shot', 'interactive') "
    "or paths to custom mode YAML files. Can be specified multiple times to combine modes.",
)
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    show_default=True,
    help="Transport protocol. If you start the server yourself (as opposed to an MCP Client starting the server), sse is recommended.",
)
@click.option(
    "--host",
    type=str,
    show_default=True,
    default="0.0.0.0",
    help="Host to bind to (for SSE transport).",
)
@click.option(
    "--port",
    type=int,
    show_default=True,
    default=8000,
    help="Port to bind to (for SSE transport).",
)
@click.option(
    "--enable-web-dashboard",
    type=bool,
    is_flag=False,
    default=None,
    help="Whether to enable the web dashboard. If not specified, will take the value from the serena configuration.",
)
@click.option(
    "--enable-gui-log-window",
    type=bool,
    is_flag=False,
    default=None,
    help="Whether to enable the GUI log window. It currently does not work on macOS, and setting this to True will be ignored then. "
    "If not specified, will take the value from the serena configuration.",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    default=None,
    help="Log level for GUI, dashboard and other logging. If not specified, will take the value from the serena configuration.",
)
@click.option(
    "--trace-lsp-communication",
    type=bool,
    is_flag=False,
    default=None,
    help="Whether to trace the communication between Serena and the language servers. This is useful for debugging language server issues.",
)
def start_mcp_server(
    project_file_opt: str | None,
    project_file_arg: str | None,
    context: str = DEFAULT_CONTEXT,
    modes: tuple[str, ...] = DEFAULT_MODES,
    transport: Literal["stdio", "sse"] = "stdio",
    host: str = "0.0.0.0",
    port: int = 8000,
    enable_web_dashboard: bool | None = None,
    enable_gui_log_window: bool | None = None,
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None,
    trace_lsp_communication: bool | None = None,
) -> None:
    """Starts the Serena MCP server. By default, will not activate any project at startup.
    If you want to start with an already active project, use --project to pass the project name or path.

    Use --context to specify the execution environment and --mode to specify behavior mode(s).
    The modes may be adjusted after startup (via the corresponding tool), but the context cannot be changed.
    """
    # Prioritize the positional argument if provided
    # This is for backward compatibility with the old CLI, should be removed in the future!
    project_file = project_file_arg if project_file_arg is not None else project_file_opt

    mcp_server, agent = create_mcp_server_and_agent(
        project=project_file,
        host=host,
        port=port,
        context=context,
        modes=modes,
        enable_web_dashboard=enable_web_dashboard,
        enable_gui_log_window=enable_gui_log_window,
        log_level=log_level,
        trace_lsp_communication=trace_lsp_communication,
    )

    # log after server creation such that the log appears in the GUI
    if project_file_arg is not None:
        log.warning(
            "The positional argument for the project file path is deprecated and will be removed in the future! "
            "Please pass the project file path via the `--project` option instead.\n"
            f"Used path: {project_file}"
        )

    log.info(
        f"Starting serena agent in MCP server with config:\n{agent.get_current_config_overview()}."
        f"\n Log level: {agent.serena_config.log_level}"
    )

    mcp_server.run(transport=transport)
