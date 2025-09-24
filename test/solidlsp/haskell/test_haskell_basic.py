"""
Tests for the Haskell language server's symbol queries.

Scenarios covered:
- `request_document_symbols` for top-level and nested declarations
- `request_containing_symbol` for functions and data types
- `request_referencing_symbols` including cross-file lookups
- `request_defining_symbol` for jumping from usages to definitions
"""

import os
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind

pytestmark = pytest.mark.haskell

SymbolDict = dict[str, Any]


def iter_symbol_dicts(nodes: Iterable[Any]) -> Iterator[SymbolDict]:
    for node in nodes:
        if isinstance(node, dict):
            yield node
            yield from iter_symbol_dicts(node.get("children") or [])


def document_symbol_tree(language_server: SolidLanguageServer, file_path: str) -> list[SymbolDict]:
    hierarchical_symbols, _ = language_server.request_document_symbols(file_path)
    return hierarchical_symbols


def collect_symbol_names(hierarchical_symbols: Iterable[Any]) -> list[str]:
    return [symbol["name"] for symbol in iter_symbol_dicts(hierarchical_symbols) if "name" in symbol]


def require_symbol(hierarchical_symbols: Iterable[Any], target_name: str) -> SymbolDict:
    return next((s for s in iter_symbol_dicts(hierarchical_symbols) if s.get("name") == target_name), None)


def selection_start_for_symbol(hierarchical_symbols: Iterable[Any], target_name: str) -> dict[str, Any]:
    return require_symbol(hierarchical_symbols, target_name).get("selectionRange", {}).get("start", {})


def range_start_for_symbol(hierarchical_symbols: Iterable[Any], target_name: str) -> dict[str, Any]:
    return require_symbol(hierarchical_symbols, target_name).get("range", {}).get("start", {})


def has_symbol(ref: Any) -> bool:
    return getattr(ref, "symbol", None) is not None


def expect_presence(items: Sequence[str], expected: Sequence[str], context: str) -> None:
    items_set = set(items)
    expected_set = set(expected)
    assert items_set.issuperset(expected_set), f"Expected symbols {sorted(expected_set)} in {context}. Found: {sorted(items_set)}"


class TestHaskellLanguageServerSymbols:
    """Test the Haskell language server's symbol-related functionality."""

    @pytest.mark.parametrize(
        "file_path,expected_symbols,context",
        [
            (os.path.join("src", "Lib.hs"), ["add", "hello", "safeDiv", "Calculator", "User", "validateUser"], "Lib.hs document symbols"),
            (os.path.join("app", "Main.hs"), ["main"], "Main.hs document symbols"),
        ],
    )
    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_document_symbols_expected_content(
        self,
        language_server: SolidLanguageServer,
        file_path: str,
        expected_symbols: Sequence[str],
        context: str,
    ) -> None:
        """Ensure each file presents the expected set of document symbols."""
        hierarchical_symbols = document_symbol_tree(language_server, file_path)
        symbol_names = collect_symbol_names(hierarchical_symbols)
        expect_presence(symbol_names, expected_symbols, context)

    @pytest.mark.parametrize(
        "target_name,offset,include_body,expected_kind",
        [
            ("add", 5, True, SymbolKind.Function.value),
            ("Calculator", 5, False, SymbolKind.Struct.value),
        ],
    )
    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_request_containing_symbol_variants(
        self,
        language_server: SolidLanguageServer,
        target_name: str,
        offset: int,
        include_body: bool,
        expected_kind: int,
    ) -> None:
        """Verify containing symbol lookup finds the expected declaration for multiple symbol types."""
        file_path = os.path.join("src", "Lib.hs")
        hierarchical_symbols = document_symbol_tree(language_server, file_path)
        start = range_start_for_symbol(hierarchical_symbols, target_name)
        test_line = start["line"]
        test_char = start["character"] + offset

        containing_symbol = language_server.request_containing_symbol(file_path, test_line, test_char, include_body=include_body)
        assert containing_symbol["name"] == target_name, f"Expected '{target_name}', got '{containing_symbol.get('name')}'"
        assert containing_symbol["kind"] == expected_kind, f"Expected kind {expected_kind}, got {containing_symbol.get('kind')}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_request_referencing_symbols_data_type(self, language_server: SolidLanguageServer) -> None:
        """Test request_referencing_symbols for 'add' function which has internal references."""
        file_path = os.path.join("src", "Lib.hs")
        hierarchical_symbols = document_symbol_tree(language_server, file_path)
        sel_start = selection_start_for_symbol(hierarchical_symbols, "add")
        refs = language_server.request_referencing_symbols(file_path, sel_start["line"], sel_start["character"])

        # 'add' function has references - HLS finds the main function that uses it
        assert any(has_symbol(ref) and ref.symbol.get("name") == "main" for ref in refs), "Expected reference to main"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_request_defining_symbol_function_usage(self, language_server: SolidLanguageServer) -> None:
        """Test request_defining_symbol by looking for function usage in Main.hs."""
        main_file = os.path.join("app", "Main.hs")

        # Look for the add function call in Main.hs (line 9: print (add 2 3))
        # Position 10 should be on 'add'
        defining_symbol = language_server.request_defining_symbol(main_file, 8, 10)

        # Should find the definition of 'add' function
        assert "name" in defining_symbol, "Defining symbol should have name"
        assert defining_symbol["name"] == "add", f"Expected 'add', got '{defining_symbol.get('name')}'"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_cross_file_references(self, language_server: SolidLanguageServer) -> None:
        """Test that we can find references to 'add' function across files."""
        src_file = os.path.join("src", "Lib.hs")
        hierarchical_symbols = document_symbol_tree(language_server, src_file)
        sel_start = selection_start_for_symbol(hierarchical_symbols, "add")
        refs = language_server.request_referencing_symbols(src_file, sel_start["line"], sel_start["character"])
        refs_with_symbols = [ref.symbol for ref in refs if has_symbol(ref)]

        # Ensure all symbols have a name and kind
        assert all("name" in symbol for symbol in refs_with_symbols), "Reference symbol should have name"
        assert all("kind" in symbol for symbol in refs_with_symbols), "Reference symbol should have kind"

        # 'add' function is used in Main.hs - should find main function reference
        assert any(
            symbol.get("name") == "main" and symbol.get("location", {}).get("relativePath") == "app/Main.hs" for symbol in refs_with_symbols
        ), "Expected reference to main in app/Main.hs"
