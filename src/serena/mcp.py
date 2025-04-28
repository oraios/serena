"""
The Serena Model Context Protocol (MCP) Server
"""

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from logging import Formatter, Logger, StreamHandler
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


def create_mcp_server(project_file_path: str | None, host: str = "0.0.0.0", port: int = 8000) -> FastMCP:
    """
    Create an MCP server.

    :param project_file_path: The path to the project file, or None.
    :param host: The host to bind to
    :param port: The port to bind to
    """
    mcp: FastMCP | None = None

    try:
        agent = SerenaAgent(
            project_file_path,
            # Callback disabled for the time being (see above)
            # project_activation_callback=update_tools
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
        tools = agent.get_exposed_tools()
        if mcp is not None:
            mcp._tool_manager._tools = {}
            for tool in tools:
                # noinspection PyProtectedMember
                mcp._tool_manager._tools[tool.get_name()] = make_tool(tool)

    @asynccontextmanager
    async def server_lifespan(mcp_server: FastMCP) -> AsyncIterator[None]:
        """Manage server startup and shutdown lifecycle."""
        mark_used(mcp_server)
        yield

    mcp_settings = Settings(lifespan=server_lifespan, host=host, port=port)
    mcp = FastMCP(**mcp_settings.model_dump())

    update_tools()

    return mcp


@click.command()
@click.option(
    "--project-file",
    "project_file_opt",  # Rename to avoid conflict with argument
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    default=None,
    help="Optional path to the .yml project file via option."
    "Does not need to be provided at startup since you can activate a project later by simply asking the agent to do so "
    "(there is a dedicated tool for this purpose).",
)
@click.argument(
    "project_file_arg",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    required=False,
    default=None,
)
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    show_default=True,
    help="Transport protocol.",
)
@click.option(
    "--host",
    type=str,
    default="0.0.0.0",
    show_default=True,
    help="Host to bind to (for SSE transport).",
)
@click.option(
    "--port",
    type=int,
    default=8000,
    show_default=True,
    help="Port to bind to (for SSE transport).",
)
def start_mcp_server(
    project_file_opt: str | None, project_file_arg: str | None, transport: Literal["stdio", "sse"], host: str, port: int
) -> None:
    """Starts the Serena MCP server.

    Accepts the project file path either via the --project-file option or as a positional argument.
    """
    # Prioritize the positional argument if provided
    # This is for backward compatibility with the old CLI, should be removed in the future!
    project_file = project_file_arg if project_file_arg is not None else project_file_opt
    mcp_server = create_mcp_server(project_file_path=project_file, host=host, port=port)

    # log after server creation such that the log appears in the GUI
    if project_file_arg is not None:
        log.warning(
            "The positional argument for the project file path is deprecated and will be removed in the future!"
            "Please pass the project file path via the `--project-file` option instead.\n"
            f"Used path: {project_file}"
        )
    mcp_server.run(transport=transport)
