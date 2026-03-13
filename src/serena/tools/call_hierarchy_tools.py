"""Call hierarchy traversal tools for tracing execution flow and impact analysis."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from solidlsp.lsp_protocol_handler import lsp_types
from solidlsp.ls_utils import PathUtils

from serena.tools.tools_base import Tool, ToolMarkerSymbolicRead

log = logging.getLogger(__name__)


class GetIncomingCallsTool(Tool, ToolMarkerSymbolicRead):
    """
    Finds all callers of a symbol by traversing the incoming call hierarchy.
    Useful for impact analysis: understanding what would break if a symbol changes.
    With depth > 1, recursively traces callers-of-callers to show the full blast radius.
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        depth: int = 1,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Traces incoming calls (callers) for the symbol identified by ``name_path``.

        Returns a tree of callers grouped by depth. Depth 1 = direct callers,
        depth 2 = callers of callers, etc.

        :param name_path: the name path of the symbol to find callers for, same logic as in the ``find_symbol`` tool.
            Examples: ``"my_function"``, ``"MyClass/my_method"``.
        :param relative_path: the relative path to the file containing the symbol.
        :param depth: maximum depth for recursive traversal (default 1 = direct callers only).
            Use 2-3 for impact analysis to see the full blast radius.
        :param max_answer_chars: if the result is longer than this number of characters,
            no content will be returned. -1 means the default value from the config will be used.
        :return: JSON with the call hierarchy tree. Each node has name, detail, file, line, depth,
            and children (if depth > 1).
        """
        symbol_retriever = self.create_language_server_symbol_retriever()
        symbol = symbol_retriever.find_unique(name_path, within_relative_path=relative_path)
        location = symbol.location

        if not location.has_position_in_file():
            return f"Symbol '{name_path}' has no file position (may be external)."

        lang_server = symbol_retriever.get_language_server(location.relative_path)
        abs_path = os.path.join(lang_server.repository_root_path, location.relative_path)
        uri = PathUtils.path_to_uri(abs_path)

        # Step 1: prepare call hierarchy at the symbol's position
        with lang_server.open_file(location.relative_path):
            items = lang_server.server.send.prepare_call_hierarchy({
                "textDocument": {"uri": uri},
                "position": {"line": location.line, "character": location.column},
            })

        if not items:
            return json.dumps({
                "target": name_path,
                "file": location.relative_path,
                "incoming_calls": [],
                "note": "No call hierarchy available for this symbol. The language server may not support it.",
            })

        # Step 2: recursively traverse incoming calls
        visited: set[str] = set()
        nodes = self._traverse_incoming(lang_server, items[0], depth, 1, visited)

        result = {
            "target": {
                "name": items[0]["name"],
                "detail": items[0].get("detail", ""),
                "file": location.relative_path,
                "line": location.line,
            },
            "direction": "incoming",
            "depth_requested": depth,
            "total_callers": self._count_nodes(nodes),
            "callers": nodes,
        }

        result_json = json.dumps(result, indent=2)
        return self._limit_length(result_json, max_answer_chars)

    def _traverse_incoming(
        self,
        lang_server: Any,
        item: lsp_types.CallHierarchyItem,
        max_depth: int,
        current_depth: int,
        visited: set[str],
    ) -> list[dict]:
        """Recursively traverse incoming calls with cycle detection."""
        if current_depth > max_depth:
            return []

        # Open file for the item being queried
        item_path = PathUtils.uri_to_path(item["uri"])
        item_rel_path = os.path.relpath(item_path, lang_server.repository_root_path)

        with lang_server.open_file(item_rel_path):
            calls = lang_server.server.send.incoming_calls({"item": item})

        if not calls:
            return []

        results = []
        for call in calls:
            caller = call["from"]
            key = f"{caller['uri']}::{caller['name']}"
            if key in visited:
                continue
            visited.add(key)

            caller_path = PathUtils.uri_to_path(caller["uri"])
            caller_rel_path = os.path.relpath(caller_path, lang_server.repository_root_path)

            node: dict[str, Any] = {
                "name": caller["name"],
                "detail": caller.get("detail", ""),
                "file": caller_rel_path,
                "line": caller["selectionRange"]["start"]["line"],
                "depth": current_depth,
            }

            if current_depth < max_depth:
                children = self._traverse_incoming(
                    lang_server, caller, max_depth, current_depth + 1, visited,
                )
                if children:
                    node["children"] = children

            results.append(node)

        return results

    @staticmethod
    def _count_nodes(nodes: list[dict]) -> int:
        count = len(nodes)
        for node in nodes:
            count += GetIncomingCallsTool._count_nodes(node.get("children", []))
        return count


class GetOutgoingCallsTool(Tool, ToolMarkerSymbolicRead):
    """
    Finds all functions/methods called by a symbol by traversing the outgoing call hierarchy.
    Useful for understanding execution flow: what happens when a function runs.
    With depth > 1, recursively traces the full call tree.
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        depth: int = 1,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Traces outgoing calls (callees) for the symbol identified by ``name_path``.

        Returns a tree of callees grouped by depth. Depth 1 = direct calls,
        depth 2 = calls made by those callees, etc.

        :param name_path: the name path of the symbol to find callees for, same logic as in the ``find_symbol`` tool.
            Examples: ``"handle_login"``, ``"AuthService/validate"``.
        :param relative_path: the relative path to the file containing the symbol.
        :param depth: maximum depth for recursive traversal (default 1 = direct callees only).
            Use 2-4 to see the full execution tree from an entry point.
        :param max_answer_chars: if the result is longer than this number of characters,
            no content will be returned. -1 means the default value from the config will be used.
        :return: JSON with the call hierarchy tree. Each node has name, detail, file, line, depth,
            and children (if depth > 1).
        """
        symbol_retriever = self.create_language_server_symbol_retriever()
        symbol = symbol_retriever.find_unique(name_path, within_relative_path=relative_path)
        location = symbol.location

        if not location.has_position_in_file():
            return f"Symbol '{name_path}' has no file position (may be external)."

        lang_server = symbol_retriever.get_language_server(location.relative_path)
        abs_path = os.path.join(lang_server.repository_root_path, location.relative_path)
        uri = PathUtils.path_to_uri(abs_path)

        # Step 1: prepare call hierarchy at the symbol's position
        with lang_server.open_file(location.relative_path):
            items = lang_server.server.send.prepare_call_hierarchy({
                "textDocument": {"uri": uri},
                "position": {"line": location.line, "character": location.column},
            })

        if not items:
            return json.dumps({
                "target": name_path,
                "file": location.relative_path,
                "outgoing_calls": [],
                "note": "No call hierarchy available for this symbol. The language server may not support it.",
            })

        # Step 2: recursively traverse outgoing calls
        visited: set[str] = set()
        nodes = self._traverse_outgoing(lang_server, items[0], depth, 1, visited)

        result = {
            "target": {
                "name": items[0]["name"],
                "detail": items[0].get("detail", ""),
                "file": location.relative_path,
                "line": location.line,
            },
            "direction": "outgoing",
            "depth_requested": depth,
            "total_callees": self._count_nodes(nodes),
            "callees": nodes,
        }

        result_json = json.dumps(result, indent=2)
        return self._limit_length(result_json, max_answer_chars)

    def _traverse_outgoing(
        self,
        lang_server: Any,
        item: lsp_types.CallHierarchyItem,
        max_depth: int,
        current_depth: int,
        visited: set[str],
    ) -> list[dict]:
        """Recursively traverse outgoing calls with cycle detection."""
        if current_depth > max_depth:
            return []

        # Open file for the item being queried
        item_path = PathUtils.uri_to_path(item["uri"])
        item_rel_path = os.path.relpath(item_path, lang_server.repository_root_path)

        with lang_server.open_file(item_rel_path):
            calls = lang_server.server.send.outgoing_calls({"item": item})

        if not calls:
            return []

        results = []
        for call in calls:
            callee = call["to"]
            key = f"{callee['uri']}::{callee['name']}"
            if key in visited:
                continue
            visited.add(key)

            callee_path = PathUtils.uri_to_path(callee["uri"])
            callee_rel_path = os.path.relpath(callee_path, lang_server.repository_root_path)

            node: dict[str, Any] = {
                "name": callee["name"],
                "detail": callee.get("detail", ""),
                "file": callee_rel_path,
                "line": callee["selectionRange"]["start"]["line"],
                "depth": current_depth,
            }

            if current_depth < max_depth:
                children = self._traverse_outgoing(
                    lang_server, callee, max_depth, current_depth + 1, visited,
                )
                if children:
                    node["children"] = children

            results.append(node)

        return results

    @staticmethod
    def _count_nodes(nodes: list[dict]) -> int:
        count = len(nodes)
        for node in nodes:
            count += GetOutgoingCallsTool._count_nodes(node.get("children", []))
        return count
