"""
Basic integration tests for the Dexter language server (alternative Elixir LSP).

These tests validate the functionality of the language server APIs
like request_document_symbols and request_references using the Elixir test repository.
They require the ``dexter`` binary to be available on PATH and are skipped otherwise.
"""

import os
from typing import Any

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language

from . import DEXTER_UNAVAILABLE, DEXTER_UNAVAILABLE_REASON

# These marks will be applied to all tests in this module
pytestmark = [
    pytest.mark.elixir_dexter,
    pytest.mark.skipif(DEXTER_UNAVAILABLE, reason=f"Dexter not available: {DEXTER_UNAVAILABLE_REASON}"),
]


def _iter_symbols(symbols: list[dict[str, Any]]):
    for symbol in symbols:
        yield symbol
        yield from _iter_symbols(symbol.get("children", []))


def _find_function_symbol(symbols: list[dict[str, Any]], module_name: str, function_name: str) -> dict[str, Any] | None:
    """Find a function symbol within a (possibly nested) module.

    Matches plain names ("create_user") as well as Dexter's arity-style names ("create_user/5").
    """
    for symbol in _iter_symbols(symbols):
        if symbol.get("name") == module_name:
            for child in symbol.get("children", []):
                child_name = child.get("name", "")
                if child_name == function_name or child_name.rpartition("/")[0] == function_name:
                    return child
    return None


class TestElixirDexterBasic:
    """Basic Dexter language server functionality tests."""

    @pytest.mark.parametrize("language_server", [Language.ELIXIR_DEXTER], indirect=True)
    def test_request_document_symbols(self, language_server: SolidLanguageServer):
        """Test finding document symbols (modules and functions) in an Elixir file."""
        file_path = os.path.join("lib", "models.ex")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        root_symbols = symbols[0]
        assert root_symbols, "Should find symbols in models.ex"
        symbol_names = [s.get("name") for s in root_symbols]

        # The User, Item and Order modules must be discovered
        for module_name in ["User", "Item", "Order"]:
            assert module_name in symbol_names, f"Should find module '{module_name}' in {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.ELIXIR_DEXTER], indirect=True)
    def test_request_references_within_file(self, language_server: SolidLanguageServer):
        """Test finding references to a function defined and used in the same file."""
        file_path = os.path.join("lib", "models.ex")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        calculate_total_symbol = _find_function_symbol(symbols[0], "Order", "calculate_total")
        assert calculate_total_symbol is not None, "Should find Order.calculate_total in models.ex"
        assert "selectionRange" in calculate_total_symbol

        sel_start = calculate_total_symbol["selectionRange"]["start"]
        references = language_server.request_references(file_path, sel_start["line"], sel_start["character"])

        assert references, "Should find references to Order.calculate_total"
        assert any(ref["uri"].endswith("models.ex") for ref in references), "Should find a reference to calculate_total within models.ex"

    @pytest.mark.parametrize("language_server", [Language.ELIXIR_DEXTER], indirect=True)
    def test_request_references_cross_file(self, language_server: SolidLanguageServer):
        """Test finding cross-file references to UserService.create_user (used in examples.ex)."""
        file_path = os.path.join("lib", "services.ex")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        create_user_symbol = _find_function_symbol(symbols[0], "UserService", "create_user")
        assert create_user_symbol is not None, "Should find UserService.create_user in services.ex"
        assert "selectionRange" in create_user_symbol

        sel_start = create_user_symbol["selectionRange"]["start"]
        references = language_server.request_references(file_path, sel_start["line"], sel_start["character"])

        assert references, "Should find references to UserService.create_user"
        assert any(ref["uri"].endswith("examples.ex") for ref in references), (
            "Should find cross-file references to create_user in examples.ex"
        )
