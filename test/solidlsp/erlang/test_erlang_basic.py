"""
Basic integration tests for the Erlang language server functionality.

These tests validate the functionality of the language server APIs
like request_references using the test repository.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language

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
            symbols_tuple = language_server.request_document_symbols(file_path)
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
