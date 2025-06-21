"""
The Serena Model Context Protocol (MCP) Server
"""

import asyncio
import contextlib
import os
import signal
import sys
import threading
import time
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from logging import Formatter, Logger, StreamHandler
from pathlib import Path
from typing import Any, Literal

import click
import docstring_parser
from mcp.server.fastmcp import server
from mcp.server.fastmcp.server import FastMCP, Settings
from mcp.server.fastmcp.tools.base import Tool as MCPTool
from pydantic_settings import SettingsConfigDict
from sensai.util import logging
from sensai.util.helper import mark_used

from serena.agent import (
    ActivateProjectTool,
    Project,
    SerenaAgent,
    ToolInterface,
    ToolRegistry,
    create_serena_config,
    show_fatal_exception_safe,
)
from serena.config import RegisteredContext, SerenaAgentContext, SerenaAgentMode
from serena.constants import DEFAULT_CONTEXT, DEFAULT_MODES
from serena.process_isolated_agent import (
    ProcessIsolatedDashboard,
    ProcessIsolatedSerenaAgent,
    ProcessIsolatedTool,
    SerenaAgentWorker,
    global_shutdown_event,
    request_global_shutdown,
)

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
    tool: ToolInterface,
) -> MCPTool:
    func_name = tool.get_name()
    func_doc = tool.get_apply_docstring() or ""
    func_arg_metadata = tool.get_apply_fn_metadata()
    is_async = False
    parameters = func_arg_metadata.arg_model.model_json_schema()

    docstring = docstring_parser.parse(func_doc)

    # Mount the tool description as a combination of the docstring description and
    # the return value description, if it exists.
    if docstring.description:
        func_doc = f"{docstring.description.strip().strip('.')}."
    else:
        func_doc = ""
    if docstring.returns and (docstring_returns_descr := docstring.returns.description):
        # Only add a space before "Returns" if func_doc is not empty
        prefix = " " if func_doc else ""
        func_doc = f"{func_doc}{prefix}Returns {docstring_returns_descr.strip().strip('.')}."

    # Parse the parameter descriptions from the docstring and add pass its description
    # to the parameters schema.
    docstring_params = {param.arg_name: param for param in docstring.params}
    parameters_properties: dict[str, dict[str, Any]] = parameters["properties"]
    for parameter, properties in parameters_properties.items():
        if (param_doc := docstring_params.get(parameter)) and param_doc.description:
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
        annotations=None,
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
    tool_timeout: float | None = None,
) -> tuple[FastMCP, ProcessIsolatedSerenaAgent]:
    """
    Create an MCP server with process-isolated SerenaAgent to prevent asyncio contamination.

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
    :param tool_timeout: Timeout in seconds for tool execution. If not specified, will take the value from the serena configuration.
    """
    mcp: FastMCP | None = None
    context_instance = SerenaAgentContext.load(context)
    modes_instances = [SerenaAgentMode.load(mode) for mode in modes]

    is_ide_assistant = context_instance.name == RegisteredContext.IDE_ASSISTANT.value

    project_instance: Project | None = None
    if project is not None:
        # Fail early if the project cannot be loaded
        log.info(f"Will activate project {project} at mcp server startup")
        try:
            project_instance = Project.load(project)
        except Exception as e:
            log.error(f"Failed to load or generate project config for {project}: {e}")
            raise
    else:
        log.warning("No project passed at startup, you will have to activate a project yourself (by asking the agent to do so).")

    tools_excluded_in_this_session = context_instance.get_excluded_tool_classes()
    if is_ide_assistant and project_instance is not None:
        tools_excluded_in_this_session.extend(project_instance.project_config.get_excluded_tool_classes())
        # if a project has been loaded, it will be activated at startup and in ide-assistant context,
        # we assume that no other project will be activated in this session.
        # Therefore, we exclude the activate project tool
        # NOTE: Even though project activation is now asynchronous, we still exclude the tool
        # because the project will be activated automatically
        tools_excluded_in_this_session.append(ActivateProjectTool)
    tool_names_excluded_in_this_session = {tool.get_name_from_cls() for tool in tools_excluded_in_this_session}

    all_tool_names = set(ToolRegistry.get_tool_names())
    tool_names_included_in_this_session = all_tool_names - tool_names_excluded_in_this_session

    try:
        # Start agent and dashboard processes (the latter only if enabled)
        serena_dashboard_process = None
        serena_config = create_serena_config(
            enable_web_dashboard=enable_web_dashboard,
            enable_gui_log_window=enable_gui_log_window,
            log_level=log_level,
            trace_lsp_communication=trace_lsp_communication,
            tool_timeout=tool_timeout,
        )
        if serena_config.web_dashboard:
            serena_dashboard_process = ProcessIsolatedDashboard(tool_names=sorted(tool_names_included_in_this_session))
        # Don't pass project to ProcessIsolatedSerenaAgent to avoid synchronous activation during startup
        serena_agent_process = ProcessIsolatedSerenaAgent(
            project=None, serena_config=serena_config, modes=modes_instances, context=context_instance
        )

    except Exception as e:
        show_fatal_exception_safe(e)
        raise

    def update_tools() -> None:
        """Update the tools in the MCP server - adapted for process isolation."""
        nonlocal mcp, serena_agent_process

        # Get tool names from agent
        # Tools may change as a result of project or mode activation.
        # NOTE: While we could pass updated tool information on to the MCP server via the callback, Claude Desktop does not,
        # unfortunately, query for changed tools. It only queries for changed resources and prompts regularly,
        # so we need to register all potentially active tools at startup, unfortunately.
        if mcp is not None:
            mcp._tool_manager._tools = {}
            for tool_name in tool_names_included_in_this_session:
                process_isolated_tool = ProcessIsolatedTool(process_agent=serena_agent_process, tool_name=tool_name)
                mcp_tool = make_tool(process_isolated_tool)
                mcp._tool_manager._tools[tool_name] = mcp_tool

    @asynccontextmanager
    async def server_lifespan(mcp_server: FastMCP) -> AsyncIterator[None]:
        """Manage server startup and shutdown lifecycle."""
        mark_used(mcp_server)

        def signal_handler(signum: int, frame: Any) -> None:
            log.info(f"Received signal {signum} in main process")
            request_global_shutdown()

            def force_exit() -> None:
                time.sleep(2.0)  # Wait 2 seconds for graceful shutdown
                log.warning("Forcing exit after timeout")
                os._exit(1)

            threading.Thread(target=force_exit, daemon=True).start()

        # Install signal handlers
        sigint_singal = signal.signal(signal.SIGINT, signal_handler)
        sigterm_signal = signal.signal(signal.SIGTERM, signal_handler)

        if serena_dashboard_process is not None:
            log.info("Starting dashboard process")
            serena_dashboard_process.start()
        log.info("Starting serena agent process")
        serena_agent_process.start()
        update_tools()

        # If a project was specified, activate it asynchronously after MCP server is ready
        async def activate_initial_project() -> None:
            if project is not None:
                try:
                    log.info(f"Activating initial project {project} asynchronously")
                    # Use asyncio.to_thread to run the blocking project activation in a thread
                    await asyncio.to_thread(
                        serena_agent_process._make_request_with_result,
                        SerenaAgentWorker.RequestMethod.TOOL_CALL,
                        {"tool_name": "activate_project", "arguments": {"project": project}},
                    )
                    log.info(f"Successfully activated initial project {project}")
                except Exception as e:
                    log.error(f"Failed to activate initial project {project}: {e}")

        # Start project activation task (non-blocking)
        if project is not None:
            asyncio.create_task(activate_initial_project())

        async def monitor_global_shutdown() -> None:
            """Monitor the global shutdown event and trigger local shutdown."""
            while not global_shutdown_event.is_set():
                # Poll the multiprocessing Event in async context
                await asyncio.sleep(0.1)
                continue
            log.info("Global shutdown event detected, initiating server shutdown")
            request_global_shutdown()
            # Send SIGTERM to self to trigger graceful shutdown
            os.kill(os.getpid(), signal.SIGTERM)

        # Start monitoring task
        monitor_task = asyncio.create_task(monitor_global_shutdown())

        try:
            yield
        except (KeyboardInterrupt, SystemExit):
            log.info("Received shutdown signal")
            request_global_shutdown()
        except Exception as e:
            log.error(f"Error in server lifespan: {e}")
            request_global_shutdown()
        finally:
            # Cancel monitor task
            monitor_task.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await monitor_task

            serena_agent_process.stop()
            if serena_dashboard_process is not None:
                serena_dashboard_process.stop()
            request_global_shutdown()
            log.info("Shutting down all processes")
            signal.signal(signal.SIGINT, sigint_singal)
            signal.signal(signal.SIGTERM, sigterm_signal)

    # Override model_config to disable the use of `.env` files for reading settings, because user projects are likely to contain
    # `.env` files (e.g. containing LOG_LEVEL) that are not supposed to override the MCP settings;
    # retain only FASTMCP_ prefix for already set environment variables.
    Settings.model_config = SettingsConfigDict(env_prefix="FASTMCP_")

    mcp_settings = Settings(lifespan=server_lifespan, host=host, port=port)
    mcp = FastMCP(**mcp_settings.model_dump())
    return mcp, serena_agent_process


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
    "project",
    type=PROJECT_TYPE,
    default=None,
    help="Either an absolute path to the project directory or a name of an already registered project. "
    "If the project passed here hasn't been registered yet, it will be registered automatically and can be activated by its name afterwards.",
)
# Keep --project-file for backwards compatibility
@click.option(
    "--project-file",
    "project",  # Use same destination variable to avoid conflicts
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
@click.option(
    "--tool-timeout",
    type=float,
    default=None,
    help="Timeout in seconds for tool execution. If not specified, will take the value from the serena configuration.",
)
def start_mcp_server(
    project: str | None,
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
    tool_timeout: float | None = None,
) -> None:
    """Starts the Serena MCP server. By default, will not activate any project at startup.
    If you want to start with an already active project, use --project to pass the project name or path.

    Use --context to specify the execution environment and --mode to specify behavior mode(s).
    The modes may be adjusted after startup (via the corresponding tool), but the context cannot be changed.
    """
    # Prioritize the positional argument if provided
    # This is for backward compatibility with the old CLI, should be removed in the future!
    project_file = project_file_arg if project_file_arg is not None else project

    # Use process isolation by default to prevent asyncio event loop contamination
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
        tool_timeout=tool_timeout,
    )

    # log after server creation such that the log appears in the GUI
    if project_file_arg is not None:
        log.warning(
            "The positional argument for the project file path is deprecated and will be removed in the future! "
            "Please pass the project file path via the `--project` option instead.\n"
            f"Used path: {project_file}"
        )

    log.info(f"Starting MCP server with config:\n{agent.serena_config}.\n Log level: {agent.serena_config.log_level}")

    mcp_server.run(transport=transport)
