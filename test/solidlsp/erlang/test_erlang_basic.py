"""
Basic integration tests for the Erlang language server functionality.

These tests validate the functionality of the language server APIs
like request_references using the test repository.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols
from test.solidlsp.util.diagnostics import assert_file_diagnostics

from . import ERLANG_LS_UNAVAILABLE, ERLANG_LS_UNAVAILABLE_REASON


@pytest.mark.erlang
@pytest.mark.skipif(ERLANG_LS_UNAVAILABLE, reason=f"Erlang LS not available: {ERLANG_LS_UNAVAILABLE_REASON}")
class TestErlangLanguageServerBasics:
    """Test basic functionality of the Erlang language server."""

    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_language_server_initialization(self, language_server: SolidLanguageServer) -> None:
        """Test that the Erlang language server initializes properly."""
        assert language_server is not None
        assert language_server.language == Language.ERLANG

    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test document symbols retrieval for Erlang files."""
        try:
            file_path = "hello.erl"
            symbols_tuple = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
            assert isinstance(symbols_tuple, tuple)
            assert len(symbols_tuple) == 2

            all_symbols, root_symbols = symbols_tuple
            assert isinstance(all_symbols, list)
            assert isinstance(root_symbols, list)
        except Exception as e:
            if "not fully initialized" in str(e):
                pytest.skip("Erlang language server not fully initialized")
            else:
                raise

    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_bare_symbol_names(self, language_server) -> None:
        all_symbols = request_all_symbols(language_server)
        malformed_symbols = []
        for s in all_symbols:
            if has_malformed_name(s):
                malformed_symbols.append(s)
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )

    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            "src/diagnostics_sample.erl",
            (),
            min_count=1,
        )
