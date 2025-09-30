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
        "file_path,expected_symbols_and_kinds,context",
        [
            (
                os.path.join("src", "Lib.hs"),
                [
                    ("add", SymbolKind.Function.value),
                    ("hello", SymbolKind.Function.value),
                    ("safeDiv", SymbolKind.Function.value),
                    ("Calculator", SymbolKind.Struct.value),
                    ("User", SymbolKind.Struct.value),
                    ("validateUser", SymbolKind.Function.value),
                ],
                "Lib.hs document symbols",
            ),
            (
                os.path.join("app", "Main.hs"),
                [("main", SymbolKind.Function.value)],
                "Main.hs document symbols",
            ),
        ],
    )
    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_document_symbols_expected_content(
        self,
        language_server: SolidLanguageServer,
        file_path: str,
        expected_symbols_and_kinds: Sequence[tuple[str, int]],
        context: str,
    ) -> None:
        """Ensure each file presents the expected set of document symbols with correct kinds.

        Note: For Haskell, top-level symbols are children of the module symbol,
        not in the flat symbols list which only contains the module itself.
        """
        expected_symbols = [name for name, _ in expected_symbols_and_kinds]

        hierarchical_symbols = document_symbol_tree(language_server, file_path)
        symbol_names = collect_symbol_names(hierarchical_symbols)
        expect_presence(symbol_names, expected_symbols, context)

        # For Haskell, top-level declarations are children of the module symbol
        top_level_symbols = hierarchical_symbols[0].get("children", [])

        # Verify specific symbol kinds
        symbol_kinds = {sym["name"]: sym["kind"] for sym in top_level_symbols}
        for name, expected_kind in expected_symbols_and_kinds:
            assert symbol_kinds.get(name) == expected_kind, f"Expected {name} to have kind {expected_kind}, got {symbol_kinds.get(name)}"

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

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_request_hover_function(self, language_server: SolidLanguageServer) -> None:
        """Test request_hover returns type signature for functions."""
        file_path = os.path.join("src", "Lib.hs")
        hierarchical_symbols = document_symbol_tree(language_server, file_path)

        # Test hover on 'add' function
        sel_start = selection_start_for_symbol(hierarchical_symbols, "add")
        hover_info = language_server.request_hover(file_path, sel_start["line"], sel_start["character"])

        hover_contents = str(hover_info["contents"])
        assert "Int" in hover_contents, f"Expected 'Int' in hover contents, got: {hover_contents}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_request_hover_data_type(self, language_server: SolidLanguageServer) -> None:
        """Test hover information on data types - hover on constructor name."""
        file_path = os.path.join("src", "Lib.hs")
        hierarchical_symbols = document_symbol_tree(language_server, file_path)

        # Find Calculator and get its constructor child (nested within)
        calc_symbol = require_symbol(hierarchical_symbols, "Calculator")
        # The constructor is nested inside the struct, get its selectionRange
        calc_constructor = calc_symbol.get("children", [{}])[0]
        sel_start = calc_constructor.get("selectionRange", {}).get("start", {})

        hover_info = language_server.request_hover(file_path, sel_start["line"], sel_start["character"])

        hover_contents = str(hover_info["contents"])
        assert "Calculator" in hover_contents, f"Expected 'Calculator' in hover, got: {hover_contents}"

    @pytest.mark.parametrize(
        "source_file,line,column,expected_file,description",
        [
            ("app/Main.hs", 8, 10, "src/Lib.hs", "function usage - 'add' in Main.hs"),  # Line 9: print (add 2 3)
            ("app/Main.hs", 15, 14, "src/Lib.hs", "data type usage - 'Calculator' in Main.hs"),  # Line 16: let calc = Calculator "calc-1" 2
        ],
    )
    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_request_definition_usage(
        self,
        language_server: SolidLanguageServer,
        source_file: str,
        line: int,
        column: int,
        expected_file: str,
        description: str,
    ) -> None:
        """Test request_definition jumps from usage to definition for functions and data types."""
        definitions = language_server.request_definition(source_file, line, column)
        assert any(
            defn["relativePath"] == expected_file for defn in definitions
        ), f"Expected definition in {expected_file} for {description}, got: {definitions}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_request_references_cross_file(self, language_server: SolidLanguageServer) -> None:
        """Test request_references finds both definition and usage locations."""
        file_path = os.path.join("src", "Lib.hs")
        hierarchical_symbols = document_symbol_tree(language_server, file_path)

        # Get position of 'add' function definition
        sel_start = selection_start_for_symbol(hierarchical_symbols, "add")
        references = language_server.request_references(file_path, sel_start["line"], sel_start["character"])

        reference_uris = [ref.get("uri", "") for ref in references]

        assert any("Lib.hs" in uri for uri in reference_uris), f"Expected references in Lib.hs, found URIs: {reference_uris}"
        assert any("Main.hs" in uri for uri in reference_uris), f"Expected references in Main.hs, found URIs: {reference_uris}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_request_workspace_symbol(self, language_server: SolidLanguageServer) -> None:
        """Test request_workspace_symbol searches symbols across workspace."""
        # Search for 'User' which appears in both data type and usage
        results = language_server.request_workspace_symbol("User")

        # Filter User's symbols in Lib.hs and get their kinds
        symbol_kinds = {sym["kind"] for sym in results if "Lib.hs" in sym["location"]["uri"]}

        assert SymbolKind.Constructor.value in symbol_kinds, f"Expected Constructor in symbol kinds, found: {symbol_kinds}"
        assert SymbolKind.Struct.value in symbol_kinds, f"Expected Struct in symbol kinds, found: {symbol_kinds}"
