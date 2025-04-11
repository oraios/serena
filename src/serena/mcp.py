"""
The Serena Model Context Protocol (MCP) Server
"""

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from logging import Formatter, Logger, StreamHandler

from mcp.server.fastmcp import server
from mcp.server.fastmcp.server import FastMCP, Settings
from mcp.server.fastmcp.tools.base import Tool as MCPTool
from mcp.server.fastmcp.utilities.func_metadata import func_metadata
from sensai.util import logging
from sensai.util.helper import mark_used

from serena.agent import SerenaAgent, SerenaConfig, Tool
from serena.gui_log_viewer import show_fatal_exception

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


def create_mcp_server() -> FastMCP:
    argv = sys.argv[1:]

    if (len(argv) == 1 and argv[0] == "--help") or len(argv) > 1:
        print("\nUsage: mcp_server [.yml project file]", file=sys.stderr)
        sys.exit(0)

    mcp: FastMCP | None = None

    def update_tools() -> None:
        """Update the tools in the MCP server."""
        # Tools may change as a result of project activation.
        # NOTE: While we could pass updated tool information on to the MCP server via the callback, Claude Desktop does not,
        # unfortunately, query for changed tools. It only queries for changed resources and prompts regularly,
        # so we need to register all tools at startup, unfortunately.
        nonlocal mcp
        tools = agent.get_exposed_tools()
        if mcp is not None:
            mcp._tool_manager._tools = {}
            for tool in tools:
                # noinspection PyProtectedMember
                mcp._tool_manager._tools[tool.get_name()] = make_tool(tool)

    project_file_path = argv[0] if len(argv) == 1 else None
    try:
        agent = SerenaAgent(
            project_file_path,
            # Callback disabled for the time being (see above)
            # project_activation_callback=update_tools
        )
    except Exception as e:
        if SerenaConfig().gui_log_window_enabled:
            show_fatal_exception(e)
        else:
            log.exception("Failed to start Serena MCP server.")
        raise

    @asynccontextmanager
    async def server_lifespan(mcp_server: FastMCP) -> AsyncIterator[None]:
        """Manage server startup and shutdown lifecycle."""
        nonlocal agent
        mark_used(mcp_server)
        yield

    mcp_settings = Settings(lifespan=server_lifespan)
    mcp = FastMCP(**mcp_settings.model_dump())

    update_tools()

    return mcp


def start_mcp_server() -> None:
    create_mcp_server().run()
