"""
Basic integration tests for the mSL (mIRC Scripting Language) language server.

Tests validate document symbols for aliases, events, raw events, menus,
dialogs, and CTCP handlers using the mSL test repository.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols

pytestmark = [pytest.mark.msl]


class TestMslDocumentSymbols:
    """Test document symbol retrieval for mSL constructs."""

    @pytest.mark.parametrize("language_server", [Language.MSL], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer) -> None:
        """Test that the language server starts successfully."""
        assert language_server.is_running()

    @pytest.mark.parametrize("language_server", [Language.MSL], indirect=True)
    def test_document_symbols_main(self, language_server: SolidLanguageServer) -> None:
        """Test that document symbols are returned for the main file."""
        doc_symbols = language_server.request_document_symbols("main.mrc")
        all_symbols, root_symbols = doc_symbols.get_all_symbols_and_roots()

        symbol_names = [s.get("name") for s in all_symbols if s.get("name")]
        assert "greet" in symbol_names, f"greet alias not found. Found: {symbol_names}"
        assert "calculate.doubloons" in symbol_names, f"calculate.doubloons alias not found. Found: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.MSL], indirect=True)
    def test_document_symbols_events(self, language_server: SolidLanguageServer) -> None:
        """Test that event handlers, raw events, and menus are detected in the main file."""
        doc_symbols = language_server.request_document_symbols("main.mrc")
        all_symbols, root_symbols = doc_symbols.get_all_symbols_and_roots()

        symbol_names = [s.get("name") for s in all_symbols if s.get("name")]
        # Check for on *:TEXT and on *:JOIN events
        on_events = [n for n in symbol_names if n.startswith("on ")]
        assert len(on_events) >= 2, f"Expected at least 2 event handlers. Found: {on_events}"
        # Check for raw event
        raw_events = [n for n in symbol_names if n.startswith("raw ")]
        assert len(raw_events) >= 1, f"Expected at least 1 raw event handler. Found: {raw_events}"
        # Check for menu
        menus = [n for n in symbol_names if n.startswith("menu ")]
        assert len(menus) >= 1, f"Expected at least 1 menu. Found: {menus}"

    @pytest.mark.parametrize("language_server", [Language.MSL], indirect=True)
    def test_document_symbols_utils(self, language_server: SolidLanguageServer) -> None:
        """Test that document symbols are returned for the utils file."""
        doc_symbols = language_server.request_document_symbols("utils.mrc")
        all_symbols, root_symbols = doc_symbols.get_all_symbols_and_roots()

        symbol_names = [s.get("name") for s in all_symbols if s.get("name")]
        assert "format.coins" in symbol_names, f"format.coins alias not found. Found: {symbol_names}"
        assert "is.admin" in symbol_names, f"is.admin alias not found. Found: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.MSL], indirect=True)
    def test_document_symbols_dialog_and_ctcp(self, language_server: SolidLanguageServer) -> None:
        """Test that dialog and CTCP handler definitions are detected."""
        doc_symbols = language_server.request_document_symbols("utils.mrc")
        all_symbols, root_symbols = doc_symbols.get_all_symbols_and_roots()

        symbol_names = [s.get("name") for s in all_symbols if s.get("name")]
        assert "dialog settings" in symbol_names, f"dialog settings not found. Found: {symbol_names}"
        # Check for CTCP handler
        ctcp_events = [n for n in symbol_names if n.startswith("ctcp ")]
        assert len(ctcp_events) >= 1, f"Expected at least 1 ctcp handler. Found: {ctcp_events}"

    @pytest.mark.parametrize("language_server", [Language.MSL], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        """Test that the full symbol tree contains expected symbols from both files."""
        from solidlsp.ls_utils import SymbolUtils

        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "greet"), "greet not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "format.coins"), "format.coins not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.MSL], indirect=True)
    def test_bare_symbol_names(self, language_server: SolidLanguageServer) -> None:
        """Test that symbol names do not contain unexpected formatting characters."""
        all_symbols = request_all_symbols(language_server)
        malformed_symbols = []
        for s in all_symbols:
            # mSL symbols can contain periods (e.g., calculate.doubloons) and
            # colons/spaces in event names (e.g., "on *:TEXT"), so allow those
            if has_malformed_name(s, period_allowed=True, colon_allowed=True, whitespace_allowed=True):
                malformed_symbols.append(s)
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )
