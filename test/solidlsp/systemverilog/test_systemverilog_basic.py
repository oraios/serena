"""
Basic tests for SystemVerilog language server integration (verible-verilog-ls).

This module tests Language.SYSTEMVERILOG using verible-verilog-ls.
Tests are skipped if the language server is not available.
"""

from typing import Any

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


def _find_symbol_by_name(language_server: SolidLanguageServer, file_path: str, name: str) -> dict[str, Any] | None:
    """Find a top-level symbol by name in a file's document symbols."""
    symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
    return next((s for s in symbols[0] if s.get("name") == name), None)


def _get_symbol_selection_start(language_server: SolidLanguageServer, file_path: str, name: str) -> tuple[int, int]:
    """Get the (line, character) of a symbol's selectionRange start."""
    symbol = _find_symbol_by_name(language_server, file_path, name)
    assert symbol is not None, f"Could not find symbol '{name}' in {file_path}"
    assert "selectionRange" in symbol, f"Symbol '{name}' has no selectionRange in {file_path}"
    sel_start = symbol["selectionRange"]["start"]
    return sel_start["line"], sel_start["character"]


@pytest.mark.systemverilog
class TestSystemVerilogSymbols:
    """Tests for document symbol extraction."""

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        """Test that symbol tree contains expected modules."""
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "counter"), "Module 'counter' not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_get_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test document symbols for counter.sv."""
        symbol = _find_symbol_by_name(language_server, "counter.sv", "counter")
        assert symbol is not None, "Expected 'counter' in document symbols"

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_find_top_module(self, language_server: SolidLanguageServer) -> None:
        """Test that top module is found (cross-file instantiation test)."""
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "top"), "Module 'top' not found in symbol tree"


@pytest.mark.systemverilog
class TestSystemVerilogDefinition:
    """Tests for go-to-definition functionality."""

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_goto_definition(self, language_server: SolidLanguageServer) -> None:
        """Test go to definition from signal usage to its declaration.

        Navigating from 'count' usage in always_ff (line 13) should jump
        to the output port declaration (line 7, char 29).
        """
        # counter.sv line 13 (0-indexed): "            count <= '0;"
        # 'count' at char 12
        definitions = language_server.request_definition("counter.sv", 13, 12)
        assert len(definitions) >= 1, f"Expected at least 1 definition, got {len(definitions)}"
        def_in_counter = [d for d in definitions if "counter.sv" in (d.get("relativePath") or "")]
        assert len(def_in_counter) >= 1, f"Expected definition in counter.sv, got: {[d.get('relativePath') for d in definitions]}"
        assert (
            def_in_counter[0]["range"]["start"]["line"] == 7
        ), f"Expected definition at line 7 (output port count), got line {def_in_counter[0]['range']['start']['line']}"

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_goto_definition_cross_file(self, language_server: SolidLanguageServer) -> None:
        """Test go to definition from module instantiation in top.sv to counter.sv.

        This is the key cross-file test: navigating from an instantiation
        (counter in top.sv) to its definition (counter.sv).
        """
        # top.sv line 17 (0-indexed: 16): "    counter #(.WIDTH(8)) u_counter ("
        # "counter" starts at column 4
        definitions = language_server.request_definition("top.sv", 16, 4)
        assert len(definitions) >= 1, f"Expected at least 1 definition, got {len(definitions)}"
        def_paths = [d.get("relativePath", "") for d in definitions]
        assert any("counter.sv" in p for p in def_paths), f"Expected definition in counter.sv, got: {def_paths}"
        counter_defs = [d for d in definitions if "counter.sv" in (d.get("relativePath") or "")]
        assert (
            counter_defs[0]["range"]["start"]["line"] == 1
        ), f"Expected definition at line 1 (module counter), got line {counter_defs[0]['range']['start']['line']}"


@pytest.mark.systemverilog
class TestSystemVerilogReferences:
    """Tests for find-references functionality."""

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_find_references(self, language_server: SolidLanguageServer) -> None:
        """Test finding within-file references to a port signal.

        The 'count' output port is declared on line 7 and used in the
        always_ff block on lines 13 and 15 (twice), giving 3 within-file
        references — all inside counter.sv.
        """
        # counter.sv line 8 (0-indexed: 7): "    output logic [WIDTH-1:0] count"
        # 'count' starts at char 29
        references = language_server.request_references("counter.sv", 7, 29)
        assert len(references) >= 1, f"Expected at least 1 reference, got {len(references)}"
        ref_paths = [r.get("relativePath", "") for r in references]
        refs_in_counter = [r for r in references if "counter.sv" in (r.get("relativePath") or "")]
        assert len(refs_in_counter) >= 1, f"Expected within-file references in counter.sv, got paths: {ref_paths}"
        ref_lines = sorted(r["range"]["start"]["line"] for r in refs_in_counter)
        # Line 13: count <= '0;  Line 15: count <= count + 1'b1; (two refs)
        assert 13 in ref_lines, f"Expected reference at line 13 (count <= '0), got lines: {ref_lines}"
        assert 15 in ref_lines, f"Expected reference at line 15 (count <= count + 1'b1), got lines: {ref_lines}"

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_find_references_cross_file(self, language_server: SolidLanguageServer) -> None:
        """Test that references to counter include its instantiation in top.sv.

        Similar to Rust (lib.rs → main.rs) and C# (Program.cs → Models/Person.cs),
        this verifies that cross-file references are found.
        """
        line, char = _get_symbol_selection_start(language_server, "counter.sv", "counter")
        references = language_server.request_references("counter.sv", line, char)
        ref_paths = [ref.get("relativePath", "") for ref in references]
        assert any("top.sv" in p for p in ref_paths), f"Expected reference from top.sv, got: {ref_paths}"
        refs_in_top = [r for r in references if "top.sv" in (r.get("relativePath") or "")]
        # top.sv line 17 (0-indexed: 16): "    counter #(.WIDTH(8)) u_counter ("
        assert (
            refs_in_top[0]["range"]["start"]["line"] == 16
        ), f"Expected cross-file reference at line 16 (counter instantiation), got line {refs_in_top[0]['range']['start']['line']}"


def _extract_hover_text(hover_info: dict[str, Any]) -> str:
    """Extract the text content from an LSP hover response."""
    contents = hover_info["contents"]
    if isinstance(contents, dict):
        return contents.get("value", "")
    elif isinstance(contents, str):
        return contents
    return str(contents)


@pytest.mark.systemverilog
class TestSystemVerilogHover:
    """Tests for hover information."""

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_hover(self, language_server: SolidLanguageServer) -> None:
        """Test hover information (experimental in verible, requires --lsp_enable_hover)."""
        line, char = _get_symbol_selection_start(language_server, "counter.sv", "counter")
        hover_info = language_server.request_hover("counter.sv", line, char)
        assert hover_info is not None, "Hover should return information for counter module"
        assert "contents" in hover_info, "Hover should have contents"
        hover_text = _extract_hover_text(hover_info)
        assert len(hover_text) > 0, "Hover text should not be empty"
        assert "counter" in hover_text.lower(), f"Hover should mention 'counter', got: {hover_text}"
        assert "module" in hover_text.lower(), f"Hover should identify 'counter' as a module, got: {hover_text}"

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_hover_includes_type_information(self, language_server: SolidLanguageServer) -> None:
        """Test that hover includes type information for a port signal.

        Hovering on 'count' output port should return its name and type
        (logic [WIDTH-1:0]), distinct from module-level hover.
        """
        # counter.sv line 8 (0-indexed: 7): "    output logic [WIDTH-1:0] count"
        # 'count' starts at char 29
        hover_info = language_server.request_hover("counter.sv", 7, 29)
        assert hover_info is not None, "Hover should return information for 'count' port"
        assert "contents" in hover_info, "Hover should have contents"
        hover_text = _extract_hover_text(hover_info)
        assert "count" in hover_text.lower(), f"Hover should mention 'count', got: {hover_text}"
        assert "logic" in hover_text.lower(), f"Hover should include type 'logic', got: {hover_text}"


def _extract_changes(workspace_edit: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Extract file URI → edits mapping from a WorkspaceEdit, handling both formats."""
    changes = workspace_edit.get("changes", {})
    if not changes:
        doc_changes = workspace_edit.get("documentChanges", [])
        assert len(doc_changes) > 0, "WorkspaceEdit should have 'changes' or 'documentChanges'"
        changes = {dc["textDocument"]["uri"]: dc["edits"] for dc in doc_changes if "textDocument" in dc and "edits" in dc}
    return changes


@pytest.mark.systemverilog
class TestSystemVerilogRename:
    """Tests for rename functionality."""

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_rename_signal_within_file(self, language_server: SolidLanguageServer) -> None:
        """Test renaming a port signal from its declaration updates within-file occurrences.

        The 'count' output port (line 7, char 29) is used in the always_ff
        block on lines 13 and 15. Renaming from the declaration site produces
        edits for all occurrences within counter.sv.
        """
        workspace_edit = language_server.request_rename_symbol_edit("counter.sv", 7, 29, "cnt")
        assert workspace_edit is not None, "Rename should be supported for port signal 'count'"

        changes = _extract_changes(workspace_edit)
        counter_edits = [edits for uri, edits in changes.items() if "counter.sv" in uri]
        assert len(counter_edits) >= 1, f"Should have edits for counter.sv, got: {list(changes.keys())}"

        edits = counter_edits[0]
        assert len(edits) >= 2, f"Expected at least 2 edits (declaration + usage), got {len(edits)}"
        edit_lines = sorted(e["range"]["start"]["line"] for e in edits)
        assert 7 in edit_lines, f"Expected edit at line 7 (port declaration), got lines: {edit_lines}"
        assert 13 in edit_lines, f"Expected edit at line 13 (count <= '0), got lines: {edit_lines}"
        assert 15 in edit_lines, f"Expected edit at line 15 (count <= count + 1'b1), got lines: {edit_lines}"
        for edit in edits:
            assert edit["newText"] == "cnt", f"Expected newText 'cnt', got {edit['newText']}"

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_rename_signal_cross_file(self, language_server: SolidLanguageServer) -> None:
        """Test renaming a port signal from a usage site includes cross-file edits.

        Renaming 'count' from usage in always_ff (line 13, char 12) should
        produce edits in counter.sv (declaration + usages) and also in top.sv
        where the port is connected (.count(count) at line 20).
        """
        workspace_edit = language_server.request_rename_symbol_edit("counter.sv", 13, 12, "cnt")
        assert workspace_edit is not None, "Rename should be supported for signal 'count' from usage site"

        changes = _extract_changes(workspace_edit)
        counter_uris = [uri for uri in changes if "counter.sv" in uri]
        top_uris = [uri for uri in changes if "top.sv" in uri]
        assert len(counter_uris) >= 1, f"Expected edits in counter.sv, got: {list(changes.keys())}"
        assert len(top_uris) >= 1, f"Expected cross-file edits in top.sv, got: {list(changes.keys())}"

        for uri, edits in changes.items():
            for edit in edits:
                assert edit["newText"] == "cnt", f"Expected 'cnt' in {uri}, got {edit['newText']}"

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_rename_module_name(self, language_server: SolidLanguageServer) -> None:
        """Test renaming a module name at its declaration.

        The 'counter' module declaration (line 1, char 7) is renamed to
        'my_counter'. Verible renames the identifier at the definition site.
        """
        line, char = _get_symbol_selection_start(language_server, "counter.sv", "counter")
        workspace_edit = language_server.request_rename_symbol_edit("counter.sv", line, char, "my_counter")
        assert workspace_edit is not None, "Rename should be supported for module 'counter'"

        changes = _extract_changes(workspace_edit)
        assert len(changes) > 0, "WorkspaceEdit should have changes"
        counter_edits = [edits for uri, edits in changes.items() if "counter.sv" in uri]
        assert len(counter_edits) >= 1, f"Should have edits for counter.sv, got: {list(changes.keys())}"

        edits = counter_edits[0]
        edit_lines = sorted(e["range"]["start"]["line"] for e in edits)
        assert 1 in edit_lines, f"Expected edit at line 1 (module declaration), got lines: {edit_lines}"
        decl_edits = [e for e in edits if e["range"]["start"]["line"] == 1]
        assert (
            decl_edits[0]["range"]["start"]["character"] == 7
        ), f"Expected edit at char 7, got char {decl_edits[0]['range']['start']['character']}"
        for uri, file_edits in changes.items():
            for edit in file_edits:
                assert edit["newText"] == "my_counter", f"Expected 'my_counter', got {edit['newText']}"
