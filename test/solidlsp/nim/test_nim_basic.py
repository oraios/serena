"""
Basic integration tests for the Nim language server (nimlangserver) functionality.

These validate document symbols, the full symbol tree, within-file references and
cross-file go-to-definition using the Nim test repository.

nimlangserver drives nimsuggest, which compiles the project lazily, so the first
requests of a session can be slow. nimsuggest's find-references does not resolve
cross-file usages reliably, so cross-file navigation is covered via go-to-definition
(which does work) rather than textDocument/references.
"""

import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_utils import SymbolUtils
from test.conftest import language_server_tests_enabled
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols

pytestmark = [
    pytest.mark.nim,
    pytest.mark.skipif(
        not language_server_tests_enabled(LanguageServerId.NIM),
        reason="Nim tests are disabled (nimlangserver not available)",
    ),
]


class TestNimDocumentSymbols:
    """Document symbol retrieval, which nimsuggest supports reliably."""

    @pytest.mark.parametrize("language_server", [LanguageServerId.NIM], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer) -> None:
        assert language_server.is_running()

    @pytest.mark.parametrize("language_server", [LanguageServerId.NIM], indirect=True)
    def test_document_symbols_main(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "main.nim")
        all_symbols, _roots = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        symbol_names = {s.get("name") for s in all_symbols if s.get("name")}
        for expected in ("Calculator", "User", "add", "multiply", "greet", "isAdult"):
            assert expected in symbol_names, f"{expected} not found in main.nim symbols. Found: {sorted(symbol_names)}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.NIM], indirect=True)
    def test_document_symbols_utils(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "utils.nim")
        all_symbols, _roots = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        symbol_names = {s.get("name") for s in all_symbols if s.get("name")}
        assert "calculateArea" in symbol_names, f"calculateArea not found. Found: {sorted(symbol_names)}"
        assert "formatGreeting" in symbol_names, f"formatGreeting not found. Found: {sorted(symbol_names)}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.NIM], indirect=True)
    def test_full_symbol_tree(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        for name in ("Calculator", "User", "add", "calculateArea", "formatGreeting"):
            assert SymbolUtils.symbol_tree_contains_name(symbols, name), f"{name} not found in symbol tree"

    @pytest.mark.parametrize("language_server", [LanguageServerId.NIM], indirect=True)
    def test_bare_symbol_names(self, language_server: SolidLanguageServer) -> None:
        all_symbols = request_all_symbols(language_server)
        malformed_symbols = [s for s in all_symbols if has_malformed_name(s)]
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )


class TestNimReferences:
    """Reference finding and go-to-definition."""

    @staticmethod
    def _symbol_selection_start(language_server: SolidLanguageServer, file_path: str, name: str) -> dict:
        all_symbols, _roots = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        symbol = next((s for s in all_symbols if s.get("name") == name), None)
        assert symbol is not None, f"{name} not found in {file_path}"
        sel_range = symbol.get("selectionRange", symbol.get("range"))
        assert sel_range is not None, f"{name} has no range information"
        return sel_range["start"]

    @pytest.mark.parametrize("language_server", [LanguageServerId.NIM], indirect=True)
    def test_references_within_file(self, language_server: SolidLanguageServer) -> None:
        """Calculator is used by both proc receivers and the instantiation in main.nim."""
        file_path = os.path.join("src", "main.nim")
        start = self._symbol_selection_start(language_server, file_path, "Calculator")

        refs = language_server.request_references(file_path, start["line"], start["character"])
        assert isinstance(refs, list)

        ref_files = {os.path.basename(ref.get("relativePath") or ref.get("uri", "")) for ref in refs}
        assert ref_files == {"main.nim"}, f"Within-file Calculator references should all be in main.nim, got {ref_files}"
        # Two proc receivers (add/multiply) plus the Calculator() instantiation.
        assert len(refs) >= 3, f"Expected at least 3 Calculator references in main.nim, found {len(refs)}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.NIM], indirect=True)
    def test_goto_definition_cross_file(self, language_server: SolidLanguageServer) -> None:
        """Proc greet in main.nim calls formatGreeting, which is defined in utils.nim."""
        main_path = os.path.join("src", "main.nim")

        with language_server.open_file(main_path), language_server.open_file(os.path.join("src", "utils.nim")):
            call_line, call_col = self._find_identifier(main_path, "formatGreeting")
            definitions = language_server.request_definition(main_path, call_line, call_col)

            assert isinstance(definitions, list) and len(definitions) > 0, "Should find a definition for formatGreeting"
            target = definitions[0]
            assert target.get("uri", "").endswith("utils.nim"), "formatGreeting should be defined in utils.nim"
            assert target["range"]["start"]["line"] == 5, "formatGreeting should be defined on line 6 (0-indexed: 5)"

    @staticmethod
    def _find_identifier(rel_path: str, identifier: str) -> tuple[int, int]:
        repo_root = os.path.join(os.path.dirname(__file__), "..", "..", "resources", "repos", "nim", "test_repo")
        with open(os.path.join(repo_root, rel_path), encoding="utf-8") as f:
            for line_idx, line in enumerate(f):
                col = line.find(identifier)
                if col != -1:
                    # Point a couple of characters into the identifier so nimsuggest resolves it.
                    return line_idx, col + 2
        raise AssertionError(f"{identifier} not found in {rel_path}")
