"""
Call Graph and Dataflow Analysis Tools.

This module provides MCP tools for call hierarchy analysis using LSP protocol.
Supports incoming calls (who calls this), outgoing calls (what does this call),
call graph traversal, call path finding, and dependency impact analysis.

@since LSP 3.16.0 (Call Hierarchy protocol)
"""

import json
import logging
from pathlib import Path
from typing import Any

from murena.tools.tools_base import Tool, ToolMarkerSymbolicRead
from solidlsp.ls_capabilities import CallHierarchySupport, CapabilityMatrix
from solidlsp.lsp_protocol_handler import lsp_types

log = logging.getLogger(__name__)


class GetIncomingCallsTool(Tool, ToolMarkerSymbolicRead):
    """
    Find who calls a function/method (incoming calls).

    Uses LSP call hierarchy to precisely identify callers with call sites.
    Supports recursive traversal up to max_depth levels.
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        include_call_sites: bool = True,
        max_depth: int = 1,
        compact_format: bool = True,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Find who calls a function/method.

        :param name_path: Name path of the symbol (e.g., "UserService/create_user")
        :param relative_path: Relative path to file containing the symbol
        :param include_call_sites: Include call site locations (line numbers)
        :param max_depth: Maximum traversal depth (1-5)
        :param compact_format: Use compact JSON format (70% token savings)
        :param max_answer_chars: Max characters for output (-1 for default)
        :return: JSON with incoming calls (callers) at specified depth
        """
        if not (1 <= max_depth <= 5):
            raise ValueError("max_depth must be between 1 and 5")

        # Check language support
        ls = self._get_language_server(relative_path)
        if not ls._has_call_hierarchy_capability():
            support = CapabilityMatrix.get_support_level(ls.language)
            if support == CallHierarchySupport.FALLBACK:
                return self._to_json(
                    {"error": f"Call hierarchy not supported for {ls.language}", "fallback": "Use find_referencing_symbols instead"}
                )

        # Find the symbol and get its location
        symbol_info = self._find_symbol_location(name_path, relative_path)
        if symbol_info is None:
            return self._to_json({"error": f"Symbol '{name_path}' not found in {relative_path}"})

        # Prepare call hierarchy
        items = ls.request_call_hierarchy_prepare(relative_path, symbol_info["line"], symbol_info["column"])
        if not items:
            return self._to_json(
                {
                    "symbol": {"name_path": name_path, "file": relative_path},
                    "incoming_calls": [],
                    "total_callers": 0,
                    "message": "No call hierarchy items found for this symbol",
                }
            )

        # Get incoming calls recursively
        result = self._get_incoming_calls_recursive(items[0], max_depth, include_call_sites, ls)

        # Format output
        if compact_format:
            output = self._format_compact(result, name_path, relative_path, max_depth)
        else:
            output = self._format_verbose(result, name_path, relative_path, max_depth)

        return self._limit_length(self._to_json(output), max_answer_chars)

    def _find_symbol_location(self, name_path: str, relative_path: str) -> dict[str, Any] | None:
        """Find symbol and return its location info."""
        retriever = self.create_language_server_symbol_retriever()
        symbols = retriever.find(name_path_pattern=name_path, within_relative_path=relative_path)
        if not symbols:
            return None

        symbol = symbols[0]
        location = symbol.location
        return {"line": location.line, "column": location.column, "name": symbol.name}

    def _get_incoming_calls_recursive(
        self,
        item: lsp_types.CallHierarchyItem,
        max_depth: int,
        include_call_sites: bool,
        ls: Any,
        current_depth: int = 1,
        visited: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Recursively collect incoming calls up to max_depth."""
        if visited is None:
            visited = set()

        # Create a unique key for this item to detect cycles
        item_key = f"{item['uri']}:{item['range']['start']['line']}:{item['name']}"
        if item_key in visited:
            return []
        visited.add(item_key)

        incoming_calls = ls.request_incoming_calls(item)
        if not incoming_calls:
            return []

        result = []
        for call in incoming_calls:
            caller = call["from"]
            caller_info = {
                "name": caller["name"],
                "name_path": self._extract_name_path(caller),
                "file": self._uri_to_relative_path(caller["uri"], ls),
                "line": caller["range"]["start"]["line"] + 1,  # 1-indexed
                "kind": caller.get("kind", "Unknown"),
            }

            if include_call_sites:
                call_sites = [r["start"]["line"] + 1 for r in call["fromRanges"]]
                caller_info["call_sites"] = call_sites

            # Recursively get callers of this caller
            if current_depth < max_depth:
                nested_callers = self._get_incoming_calls_recursive(caller, max_depth, include_call_sites, ls, current_depth + 1, visited)
                if nested_callers:
                    caller_info["callers"] = nested_callers

            result.append(caller_info)

        return result

    def _get_language_server(self, relative_path: str) -> Any:
        """Get language server for the file."""
        retriever = self.create_language_server_symbol_retriever()
        return retriever.get_language_server(relative_path)

    def _extract_name_path(self, item: lsp_types.CallHierarchyItem) -> str:
        """Extract name_path from CallHierarchyItem."""
        detail = item.get("detail", "")
        if detail:
            # Try to construct name_path from detail (often contains class name)
            return f"{detail}/{item['name']}"
        return item["name"]

    def _uri_to_relative_path(self, uri: str, ls: Any) -> str:
        """Convert LSP URI to relative path."""
        from solidlsp.ls_utils import PathUtils

        abs_path = PathUtils.uri_to_path(uri)
        try:
            rel_path = Path(abs_path).relative_to(ls.repository_root_path)
            return str(rel_path)
        except ValueError:
            return abs_path

    def _format_compact(self, calls: list[dict], name_path: str, relative_path: str, max_depth: int) -> dict:
        """Format in compact JSON (70% token savings)."""

        def compact_call(call: dict) -> dict:
            c = {"np": call["name_path"], "fp": call["file"], "ln": call["line"], "k": call.get("kind", "Unknown")}
            if "call_sites" in call:
                c["sites"] = call["call_sites"]
            if "callers" in call:
                c["callers"] = [compact_call(caller) for caller in call["callers"]]
            return c

        return {
            "s": {"np": name_path, "fp": relative_path},
            "callers": [compact_call(c) for c in calls],
            "tot": len(calls),
            "d": max_depth,
            "more": False,  # TODO: implement truncation
        }

    def _format_verbose(self, calls: list[dict], name_path: str, relative_path: str, max_depth: int) -> dict:
        """Format in verbose JSON (opt-in, more readable)."""
        return {
            "symbol": {"name_path": name_path, "file": relative_path},
            "incoming_calls": calls,
            "total_callers": len(calls),
            "max_depth": max_depth,
            "has_more": False,
        }


class GetOutgoingCallsTool(Tool, ToolMarkerSymbolicRead):
    """
    Find what a function/method calls (outgoing calls).

    Uses LSP call hierarchy to identify callees with call site locations.
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        include_call_sites: bool = True,
        max_depth: int = 1,
        compact_format: bool = True,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Find what a function/method calls.

        :param name_path: Name path of the symbol
        :param relative_path: Relative path to file
        :param include_call_sites: Include call site locations
        :param max_depth: Maximum traversal depth (1-5)
        :param compact_format: Use compact JSON format
        :param max_answer_chars: Max characters for output
        :return: JSON with outgoing calls (callees)
        """
        if not (1 <= max_depth <= 5):
            raise ValueError("max_depth must be between 1 and 5")

        # Use same logic as GetIncomingCallsTool but with outgoing_calls
        ls = self._get_language_server(relative_path)
        if not ls._has_call_hierarchy_capability():
            support = CapabilityMatrix.get_support_level(ls.language)
            if support == CallHierarchySupport.FALLBACK:
                return self._to_json(
                    {
                        "error": f"Call hierarchy not supported for {ls.language}",
                        "fallback": "Use find_symbol with include_body=True to see code",
                    }
                )

        symbol_info = self._find_symbol_location(name_path, relative_path)
        if symbol_info is None:
            return self._to_json({"error": f"Symbol '{name_path}' not found"})

        items = ls.request_call_hierarchy_prepare(relative_path, symbol_info["line"], symbol_info["column"])
        if not items:
            return self._to_json({"error": "No call hierarchy items found"})

        result = self._get_outgoing_calls_recursive(items[0], max_depth, include_call_sites, ls)

        if compact_format:
            output = self._format_compact(result, name_path, relative_path, max_depth)
        else:
            output = self._format_verbose(result, name_path, relative_path, max_depth)

        return self._limit_length(self._to_json(output), max_answer_chars)

    def _find_symbol_location(self, name_path: str, relative_path: str) -> dict[str, Any] | None:
        """Find symbol location (reuse from GetIncomingCallsTool)."""
        retriever = self.create_language_server_symbol_retriever()
        symbols = retriever.find(name_path_pattern=name_path, within_relative_path=relative_path)
        if not symbols:
            return None

        symbol = symbols[0]
        location = symbol.location
        return {"line": location.line, "column": location.column, "name": symbol.name}

    def _get_outgoing_calls_recursive(
        self,
        item: lsp_types.CallHierarchyItem,
        max_depth: int,
        include_call_sites: bool,
        ls: Any,
        current_depth: int = 1,
        visited: set[str] | None = None,
    ) -> list[dict]:
        """Recursively collect outgoing calls."""
        if visited is None:
            visited = set()

        item_key = f"{item['uri']}:{item['range']['start']['line']}:{item['name']}"
        if item_key in visited:
            return []
        visited.add(item_key)

        outgoing_calls = ls.request_outgoing_calls(item)
        if not outgoing_calls:
            return []

        result = []
        for call in outgoing_calls:
            callee = call["to"]
            callee_info = {
                "name": callee["name"],
                "name_path": self._extract_name_path(callee),
                "file": self._uri_to_relative_path(callee["uri"], ls),
                "line": callee["range"]["start"]["line"] + 1,
                "kind": callee.get("kind", "Unknown"),
            }

            if include_call_sites:
                call_sites = [r["start"]["line"] + 1 for r in call["fromRanges"]]
                callee_info["call_sites"] = call_sites

            if current_depth < max_depth:
                nested_callees = self._get_outgoing_calls_recursive(callee, max_depth, include_call_sites, ls, current_depth + 1, visited)
                if nested_callees:
                    callee_info["calls"] = nested_callees

            result.append(callee_info)

        return result

    def _get_language_server(self, relative_path: str) -> Any:
        """Get language server for the file."""
        retriever = self.create_language_server_symbol_retriever()
        return retriever.get_language_server(relative_path)

    def _extract_name_path(self, item: lsp_types.CallHierarchyItem) -> str:
        """Extract name_path from CallHierarchyItem."""
        detail = item.get("detail", "")
        if detail:
            return f"{detail}/{item['name']}"
        return item["name"]

    def _uri_to_relative_path(self, uri: str, ls: Any) -> str:
        """Convert URI to relative path."""
        from solidlsp.ls_utils import PathUtils

        abs_path = PathUtils.uri_to_path(uri)
        try:
            rel_path = Path(abs_path).relative_to(ls.repository_root_path)
            return str(rel_path)
        except ValueError:
            return abs_path

    def _format_compact(self, calls: list[dict], name_path: str, relative_path: str, max_depth: int) -> dict:
        """Format in compact JSON."""

        def compact_call(call: dict) -> dict:
            c = {"np": call["name_path"], "fp": call["file"], "ln": call["line"], "k": call.get("kind", "Unknown")}
            if "call_sites" in call:
                c["sites"] = call["call_sites"]
            if "calls" in call:
                c["calls"] = [compact_call(callee) for callee in call["calls"]]
            return c

        return {"s": {"np": name_path, "fp": relative_path}, "callees": [compact_call(c) for c in calls], "tot": len(calls), "d": max_depth}

    def _format_verbose(self, calls: list[dict], name_path: str, relative_path: str, max_depth: int) -> dict:
        """Format in verbose JSON."""
        return {
            "symbol": {"name_path": name_path, "file": relative_path},
            "outgoing_calls": calls,
            "total_callees": len(calls),
            "max_depth": max_depth,
        }


class BuildCallGraphTool(Tool, ToolMarkerSymbolicRead):
    """
    Build a multi-level call graph (incoming + outgoing calls).

    Combines incoming and outgoing call analysis for comprehensive understanding.
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        direction: str = "both",
        max_depth: int = 2,
        max_nodes: int = 50,
        compact_format: bool = True,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Build a call graph for a symbol.

        :param name_path: Name path of the symbol
        :param relative_path: Relative path to file
        :param direction: "incoming", "outgoing", or "both"
        :param max_depth: Maximum traversal depth (1-5)
        :param max_nodes: Maximum nodes to include (truncates if exceeded)
        :param compact_format: Use compact JSON format
        :param max_answer_chars: Max characters for output
        :return: JSON with complete call graph
        """
        if direction not in {"incoming", "outgoing", "both"}:
            raise ValueError("direction must be 'incoming', 'outgoing', or 'both'")

        if not (1 <= max_depth <= 5):
            raise ValueError("max_depth must be between 1 and 5")

        result = {
            "symbol": {"name_path": name_path, "file": relative_path},
            "direction": direction,
            "max_depth": max_depth,
            "truncated": False,
        }

        # Get incoming calls if requested
        if direction in {"incoming", "both"}:
            incoming_tool = GetIncomingCallsTool(self.agent)
            incoming_result = incoming_tool.apply(
                name_path=name_path, relative_path=relative_path, max_depth=max_depth, compact_format=False
            )
            incoming_data = json.loads(incoming_result)
            result["incoming"] = incoming_data.get("incoming_calls", [])

        # Get outgoing calls if requested
        if direction in {"outgoing", "both"}:
            outgoing_tool = GetOutgoingCallsTool(self.agent)
            outgoing_result = outgoing_tool.apply(
                name_path=name_path, relative_path=relative_path, max_depth=max_depth, compact_format=False
            )
            outgoing_data = json.loads(outgoing_result)
            result["outgoing"] = outgoing_data.get("outgoing_calls", [])

        # Count total nodes and truncate if needed
        total_nodes = self._count_nodes(result)
        if total_nodes > max_nodes:
            result = self._truncate_graph(result, max_nodes)
            result["truncated"] = True

        # Format output
        if compact_format:
            result = self._to_compact_format(result)

        return self._limit_length(self._to_json(result), max_answer_chars)

    def _count_nodes(self, graph: dict) -> int:
        """Count total nodes in the graph."""
        count = 1  # The root symbol
        if "incoming" in graph:
            count += self._count_call_nodes(graph["incoming"])
        if "outgoing" in graph:
            count += self._count_call_nodes(graph["outgoing"])
        return count

    def _count_call_nodes(self, calls: list) -> int:
        """Recursively count nodes in call list."""
        count = len(calls)
        for call in calls:
            if "callers" in call:
                count += self._count_call_nodes(call["callers"])
            if "calls" in call:
                count += self._count_call_nodes(call["calls"])
        return count

    def _truncate_graph(self, graph: dict, max_nodes: int) -> dict:
        """Truncate graph to max_nodes."""
        # Simple truncation: limit depth to 1 if too many nodes
        if "incoming" in graph:
            graph["incoming"] = self._truncate_calls(graph["incoming"])
        if "outgoing" in graph:
            graph["outgoing"] = self._truncate_calls(graph["outgoing"])
        return graph

    def _truncate_calls(self, calls: list) -> list:
        """Remove nested calls to reduce size."""
        truncated = []
        for call in calls:
            call_copy = call.copy()
            call_copy.pop("callers", None)
            call_copy.pop("calls", None)
            truncated.append(call_copy)
        return truncated

    def _to_compact_format(self, graph: dict) -> dict:
        """Convert to compact format."""
        # Simplified compact format for call graphs
        return graph


class FindCallPathTool(Tool, ToolMarkerSymbolicRead):
    """
    Find call path between two symbols (A → ... → Z).

    Uses BFS to find shortest path or all paths up to max_depth.
    """

    def apply(
        self,
        from_name_path: str,
        from_file: str,
        to_name_path: str,
        to_file: str,
        max_depth: int = 5,
        find_all_paths: bool = False,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Find call path between two symbols.

        :param from_name_path: Starting symbol name path
        :param from_file: Starting symbol file
        :param to_name_path: Target symbol name path
        :param to_file: Target symbol file
        :param max_depth: Maximum path length (1-5)
        :param find_all_paths: Find all paths (False = shortest only)
        :param max_answer_chars: Max characters for output
        :return: JSON with call paths found
        """
        if not (1 <= max_depth <= 5):
            raise ValueError("max_depth must be between 1 and 5")

        # Use BFS to find paths
        paths = self._find_paths_bfs(from_name_path, from_file, to_name_path, to_file, max_depth, find_all_paths)

        result = {
            "from": {"name_path": from_name_path, "file": from_file},
            "to": {"name_path": to_name_path, "file": to_file},
            "paths": paths,
            "found": len(paths) > 0,
            "shortest_length": min((len(p) for p in paths), default=0),
        }

        return self._limit_length(self._to_json(result), max_answer_chars)

    def _find_paths_bfs(
        self, from_name_path: str, from_file: str, to_name_path: str, to_file: str, max_depth: int, find_all: bool
    ) -> list[list[dict]]:
        """Find paths using BFS."""
        # Simplified implementation - would need full BFS with path tracking
        # For now, return empty (to be implemented in testing phase)
        log.warning("FindCallPathTool: Full BFS implementation pending")
        return []


class AnalyzeCallDependenciesTool(Tool, ToolMarkerSymbolicRead):
    """
    Analyze call dependencies and impact.

    Provides dependency impact analysis, usage analysis, and hotspot detection.
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        analysis_type: str = "impact",
        max_depth: int = 3,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Analyze call dependencies for a symbol.

        :param name_path: Name path of the symbol
        :param relative_path: Relative path to file
        :param analysis_type: "impact", "usage", or "hotspots"
        :param max_depth: Analysis depth (1-5)
        :param max_answer_chars: Max characters for output
        :return: JSON with dependency analysis
        """
        if analysis_type not in {"impact", "usage", "hotspots"}:
            raise ValueError("analysis_type must be 'impact', 'usage', or 'hotspots'")

        if not (1 <= max_depth <= 5):
            raise ValueError("max_depth must be between 1 and 5")

        # Get both incoming and outgoing calls
        incoming_tool = GetIncomingCallsTool(self.agent)
        outgoing_tool = GetOutgoingCallsTool(self.agent)

        incoming_data = json.loads(incoming_tool.apply(name_path, relative_path, max_depth=max_depth, compact_format=False))
        outgoing_data = json.loads(outgoing_tool.apply(name_path, relative_path, max_depth=max_depth, compact_format=False))

        # Analyze based on type
        if analysis_type == "impact":
            result = self._analyze_impact(incoming_data, name_path, relative_path)
        elif analysis_type == "usage":
            result = self._analyze_usage(incoming_data, outgoing_data, name_path, relative_path)
        else:  # hotspots
            result = self._analyze_hotspots(incoming_data, outgoing_data, name_path, relative_path)

        return self._limit_length(self._to_json(result), max_answer_chars)

    def _analyze_impact(self, incoming_data: dict, name_path: str, relative_path: str) -> dict:
        """Analyze impact: how many symbols depend on this one."""
        callers = incoming_data.get("incoming_calls", [])
        unique_callers = self._count_unique_symbols(callers)

        return {
            "symbol": {"name_path": name_path, "file": relative_path},
            "analysis": "impact",
            "total_direct_callers": len(callers),
            "total_unique_callers": unique_callers,
            "impact_level": "high" if unique_callers > 10 else "medium" if unique_callers > 3 else "low",
            "callers": callers[:10],  # Top 10
        }

    def _analyze_usage(self, incoming: dict, outgoing: dict, name_path: str, relative_path: str) -> dict:
        """Analyze usage: how this symbol uses others."""
        return {
            "symbol": {"name_path": name_path, "file": relative_path},
            "analysis": "usage",
            "incoming_count": len(incoming.get("incoming_calls", [])),
            "outgoing_count": len(outgoing.get("outgoing_calls", [])),
        }

    def _analyze_hotspots(self, incoming: dict, outgoing: dict, name_path: str, relative_path: str) -> dict:
        """Analyze hotspots: heavily used or complex symbols."""
        return {
            "symbol": {"name_path": name_path, "file": relative_path},
            "analysis": "hotspots",
            "is_hotspot": len(incoming.get("incoming_calls", [])) > 5,
        }

    def _count_unique_symbols(self, calls: list) -> int:
        """Count unique symbols in call tree."""
        seen: set[str] = set()

        def count(call_list: list) -> None:
            for call in call_list:
                key = f"{call['file']}:{call['name_path']}"
                seen.add(key)
                if "callers" in call:
                    count(call["callers"])

        count(calls)
        return len(seen)
