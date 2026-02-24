"""
Tools for querying other running Serena HTTP services (cross-project queries).
"""

from datetime import timedelta
from typing import Any

import anyio.from_thread
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from sensai.util import logging

from serena.service_registry import ServiceRegistry
from serena.tools.tools_base import Tool, ToolMarkerDoesNotRequireActiveProject, ToolMarkerOptional

log = logging.getLogger(__name__)

ALLOWED_REMOTE_TOOLS = frozenset(
    {
        "find_symbol",
        "get_symbols_overview",
        "find_referencing_symbols",
        "read_file",
        "list_dir",
        "find_file",
        "search_for_pattern",
        "list_memories",
        "read_memory",
    }
)


class QueryRemoteProjectTool(Tool, ToolMarkerDoesNotRequireActiveProject, ToolMarkerOptional):
    """
    Queries another running Serena HTTP service for read-only information about a different project.
    Use this to inspect symbols, files, or patterns in a project that is served by a separate
    Serena instance (started via ``serena service start``).
    """

    def apply(
        self,
        project: str,
        tool_name: str,
        tool_arguments: dict[str, Any] | None = None,
    ) -> str:
        """
        Calls a read-only tool on a remote Serena service that manages a different project.

        :param project: name of the project whose service to query (as shown in ``serena service status``)
        :param tool_name: name of the tool to call on the remote service. Must be one of the
            allowed read-only tools.
        :param tool_arguments: arguments dict passed to the remote tool (default: empty dict)
        """
        if tool_arguments is None:
            tool_arguments = {}

        # Validate tool name against allowlist
        if tool_name not in ALLOWED_REMOTE_TOOLS:
            sorted_tools = sorted(ALLOWED_REMOTE_TOOLS)
            return f"Error: Tool '{tool_name}' is not allowed for remote queries. " f"Allowed tools: {', '.join(sorted_tools)}"

        # Look up the project in the service registry
        registry = ServiceRegistry()
        entry = registry.get_service(project)
        if entry is None:
            available = registry.list_services(clean_stale=True)
            if available:
                names = ", ".join(sorted(available.keys()))
                return f"Error: No running service found for project '{project}'. Available services: {names}"
            else:
                return (
                    f"Error: No running service found for project '{project}'. "
                    "No services are currently registered. Start a service with 'serena service start'."
                )

        url = f"http://127.0.0.1:{entry.port}/mcp"
        log.info(f"Querying remote project '{project}' at {url}: {tool_name}")

        try:
            result = anyio.from_thread.run(self._call_remote_tool, url, tool_name, tool_arguments)
        except Exception as e:
            return f"Error calling remote service for project '{project}': {e.__class__.__name__} - {e}"

        return result

    @staticmethod
    async def _call_remote_tool(url: str, tool_name: str, tool_arguments: dict[str, Any]) -> str:
        """Connect to a remote Serena MCP service and call a tool.

        :param url: the streamable-HTTP endpoint URL
        :param tool_name: name of the tool to invoke
        :param tool_arguments: arguments to pass to the tool
        :return: the text content from the tool result
        """
        async with streamablehttp_client(url=url, timeout=30) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream, read_timeout_seconds=timedelta(seconds=120)) as session:
                await session.initialize()
                result = await session.call_tool(name=tool_name, arguments=tool_arguments)

        # Extract text content from the result
        text_parts = []
        for content in result.content:
            if hasattr(content, "text"):
                text_parts.append(content.text)
        return "\n".join(text_parts) if text_parts else "(no text content in response)"
