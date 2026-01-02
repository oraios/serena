"""
Basic Vue language server tests.

Tests core functionality including symbol tree parsing, cross-file references,
and TypeScript coordination through the dual LSP architecture.
"""

import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.vue
class TestVueLanguageServer:
    """Tests for basic Vue language server operations."""

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_vue_files_in_symbol_tree(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "App"), "App not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorButton"), "CalculatorButton not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorInput"), "CalculatorInput not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorDisplay"), "CalculatorDisplay not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        store_file = os.path.join("src", "stores", "calculator.ts")
        symbols = language_server.request_document_symbols(store_file).get_all_symbols_and_roots()

        # Find useCalculatorStore function
        store_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "useCalculatorStore":
                store_symbol = sym
                break

        assert store_symbol is not None, "useCalculatorStore function not found"

        # Get references
        sel_start = store_symbol["selectionRange"]["start"]
        refs = language_server.request_references(store_file, sel_start["line"], sel_start["character"])

        # Should have multiple references: definition + usage in App.vue, CalculatorInput.vue, CalculatorDisplay.vue
        assert len(refs) >= 4, f"useCalculatorStore should have at least 4 references (definition + 3 usages), got {len(refs)}"

        # Verify we have references from .vue files
        vue_refs = [ref for ref in refs if ".vue" in ref.get("relativePath", "")]
        assert len(vue_refs) >= 3, f"Should have at least 3 Vue component references, got {len(vue_refs)}"


@pytest.mark.vue
class TestVueDualLspArchitecture:
    """Tests for Vue + TypeScript dual language server coordination."""

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_typescript_server_coordination(self, language_server: SolidLanguageServer) -> None:
        ts_file = os.path.join("src", "stores", "calculator.ts")
        ts_symbols = language_server.request_document_symbols(ts_file).get_all_symbols_and_roots()
        ts_symbol_names = [s.get("name") for s in ts_symbols[0]]

        assert len(ts_symbols[0]) >= 5, f"TypeScript server should return multiple symbols for calculator.ts, got {len(ts_symbols[0])}"
        assert "useCalculatorStore" in ts_symbol_names, "TypeScript server should extract store function"

        # Verify Vue server can parse .vue files
        vue_file = os.path.join("src", "App.vue")
        vue_symbols = language_server.request_document_symbols(vue_file).get_all_symbols_and_roots()
        vue_symbol_names = [s.get("name") for s in vue_symbols[0]]

        assert len(vue_symbols[0]) >= 15, f"Vue server should return at least 15 symbols for App.vue, got {len(vue_symbols[0])}"
        assert "appTitle" in vue_symbol_names, "Vue server should extract ref declarations from script setup"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_cross_file_references_vue_to_typescript(self, language_server: SolidLanguageServer) -> None:
        store_file = os.path.join("src", "stores", "calculator.ts")
        store_symbols = language_server.request_document_symbols(store_file).get_all_symbols_and_roots()

        store_symbol = None
        for sym in store_symbols[0]:
            if sym.get("name") == "useCalculatorStore":
                store_symbol = sym
                break

        if not store_symbol or "selectionRange" not in store_symbol:
            pytest.skip("useCalculatorStore symbol not found - test fixture may need updating")

        # Request references for this symbol
        sel_start = store_symbol["selectionRange"]["start"]
        refs = language_server.request_references(store_file, sel_start["line"], sel_start["character"])

        # Verify we found references: definition + usage in App.vue, CalculatorInput.vue, CalculatorDisplay.vue
        assert len(refs) >= 4, f"useCalculatorStore should have at least 4 references (definition + 3 usages), found {len(refs)} references"

        # Verify references include .vue files (components that import the store)
        vue_refs = [ref for ref in refs if ".vue" in ref.get("uri", "")]
        assert (
            len(vue_refs) >= 3
        ), f"Should find at least 3 references in Vue components, found {len(vue_refs)}: {[ref.get('uri', '') for ref in vue_refs]}"

        # Verify specific components that use the store
        expected_vue_files = ["App.vue", "CalculatorInput.vue", "CalculatorDisplay.vue"]
        found_components = []
        for expected_file in expected_vue_files:
            matching_refs = [ref for ref in vue_refs if expected_file in ref.get("uri", "")]
            if matching_refs:
                found_components.append(expected_file)

        assert len(found_components) > 0, (
            f"Should find references in at least one component that uses the store. "
            f"Expected any of {expected_vue_files}, found references in: {[ref.get('uri', '') for ref in vue_refs]}"
        )

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_cross_file_references_typescript_to_vue(self, language_server: SolidLanguageServer) -> None:
        types_file = os.path.join("src", "types", "index.ts")
        types_symbols = language_server.request_document_symbols(types_file).get_all_symbols_and_roots()
        types_symbol_names = [s.get("name") for s in types_symbols[0]]

        # Operation type is used in calculator.ts and CalculatorInput.vue
        assert "Operation" in types_symbol_names, "Operation type should exist in types file"

        operation_symbol = None
        for sym in types_symbols[0]:
            if sym.get("name") == "Operation":
                operation_symbol = sym
                break

        if not operation_symbol or "selectionRange" not in operation_symbol:
            pytest.skip("Operation type symbol not found - test fixture may need updating")

        # Request references for the Operation type
        sel_start = operation_symbol["selectionRange"]["start"]
        refs = language_server.request_references(types_file, sel_start["line"], sel_start["character"])

        # Verify we found references: definition + usage in calculator.ts and Vue files
        assert len(refs) >= 2, f"Operation type should have at least 2 references (definition + usages), found {len(refs)} references"

        # The Operation type should be referenced in both .ts files (calculator.ts) and potentially .vue files
        all_ref_uris = [ref.get("uri", "") for ref in refs]
        has_ts_refs = any(".ts" in uri and "types" not in uri for uri in all_ref_uris)

        assert (
            has_ts_refs
        ), f"Operation type should be referenced in TypeScript files like calculator.ts. Found references in: {all_ref_uris}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_reference_deduplication(self, language_server: SolidLanguageServer) -> None:
        store_file = os.path.join("src", "stores", "calculator.ts")
        store_symbols = language_server.request_document_symbols(store_file).get_all_symbols_and_roots()

        # Find a commonly-used symbol (useCalculatorStore)
        store_symbol = None
        for sym in store_symbols[0]:
            if sym.get("name") == "useCalculatorStore":
                store_symbol = sym
                break

        if not store_symbol or "selectionRange" not in store_symbol:
            pytest.skip("useCalculatorStore symbol not found - test fixture may need updating")

        # Request references
        sel_start = store_symbol["selectionRange"]["start"]
        refs = language_server.request_references(store_file, sel_start["line"], sel_start["character"])

        # Check for duplicate references (same file, line, and character)
        seen_locations = set()
        duplicates = []

        for ref in refs:
            # Create a unique key for this reference location
            uri = ref.get("uri", "")
            if "range" in ref:
                line = ref["range"]["start"]["line"]
                character = ref["range"]["start"]["character"]
                location_key = (uri, line, character)

                if location_key in seen_locations:
                    duplicates.append(location_key)
                else:
                    seen_locations.add(location_key)

        assert len(duplicates) == 0, (
            f"Found {len(duplicates)} duplicate reference locations. "
            f"The dual-LSP architecture should deduplicate references from both servers. "
            f"Duplicates: {duplicates}"
        )


@pytest.mark.vue
class TestVueEdgeCases:
    """Tests for edge cases in Vue symbol handling."""

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_symbol_tree_structure(self, language_server: SolidLanguageServer) -> None:
        full_tree = language_server.request_full_symbol_tree()

        # Helper to extract all file paths from symbol tree
        def extract_paths_from_tree(symbols, paths=None):
            """Recursively extract file paths from symbol tree."""
            if paths is None:
                paths = []

            if isinstance(symbols, list):
                for symbol in symbols:
                    extract_paths_from_tree(symbol, paths)
            elif isinstance(symbols, dict):
                # Check if this symbol has a location
                if "location" in symbols and "uri" in symbols["location"]:
                    uri = symbols["location"]["uri"]
                    # Extract the path after file://
                    if uri.startswith("file://"):
                        file_path = uri[7:]  # Remove "file://"
                        paths.append(file_path)

                # Recurse into children
                if "children" in symbols:
                    extract_paths_from_tree(symbols["children"], paths)

            return paths

        all_paths = extract_paths_from_tree(full_tree)

        # Verify we have files from expected directories
        # Note: Symbol tree may include duplicate paths (one per symbol in file)
        components_files = list({p for p in all_paths if "components" in p and ".vue" in p})
        stores_files = list({p for p in all_paths if "stores" in p and ".ts" in p})
        composables_files = list({p for p in all_paths if "composables" in p and ".ts" in p})

        assert len(components_files) == 3, (
            f"Symbol tree should include exactly 3 unique Vue components (CalculatorButton, CalculatorInput, CalculatorDisplay). "
            f"Found {len(components_files)} unique component files: {[p.split('/')[-1] for p in sorted(components_files)]}"
        )

        assert len(stores_files) == 1, (
            f"Symbol tree should include exactly 1 unique store file (calculator.ts). "
            f"Found {len(stores_files)} unique store files: {[p.split('/')[-1] for p in sorted(stores_files)]}"
        )

        assert len(composables_files) == 2, (
            f"Symbol tree should include exactly 2 unique composable files (useFormatter.ts, useTheme.ts). "
            f"Found {len(composables_files)} unique composable files: {[p.split('/')[-1] for p in sorted(composables_files)]}"
        )

        # Verify specific expected files exist in the tree
        expected_files = [
            "CalculatorButton.vue",
            "CalculatorInput.vue",
            "CalculatorDisplay.vue",
            "App.vue",
            "calculator.ts",
            "useFormatter.ts",
            "useTheme.ts",
        ]

        for expected_file in expected_files:
            matching_files = [p for p in all_paths if expected_file in p]
            assert len(matching_files) > 0, f"Expected file '{expected_file}' should be in symbol tree. All paths: {all_paths}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_document_overview(self, language_server: SolidLanguageServer) -> None:
        app_file = os.path.join("src", "App.vue")
        overview = language_server.request_document_overview(app_file)

        # Overview should return a list of top-level symbols
        assert isinstance(overview, list), f"Overview should be a list, got: {type(overview)}"
        assert len(overview) >= 1, f"App.vue should have at least 1 top-level symbol in overview, got {len(overview)}"

        # Extract symbol names from overview
        symbol_names = [s.get("name") for s in overview if isinstance(s, dict)]

        # Vue LSP returns SFC structure (template/script/style sections) for .vue files
        # This is expected behavior - overview shows the file's high-level structure
        assert (
            len(symbol_names) >= 1
        ), f"Should have at least 1 symbol name in overview (e.g., 'App' or SFC section), got {len(symbol_names)}: {symbol_names}"

        # Test overview for a TypeScript file
        store_file = os.path.join("src", "stores", "calculator.ts")
        store_overview = language_server.request_document_overview(store_file)

        assert isinstance(store_overview, list), f"Store overview should be a list, got: {type(store_overview)}"
        assert len(store_overview) >= 1, f"calculator.ts should have at least 1 top-level symbol in overview, got {len(store_overview)}"

        store_symbol_names = [s.get("name") for s in store_overview if isinstance(s, dict)]
        assert (
            "useCalculatorStore" in store_symbol_names
        ), f"useCalculatorStore should be in store file overview. Found {len(store_symbol_names)} symbols: {store_symbol_names}"

        # Test overview for another Vue component
        button_file = os.path.join("src", "components", "CalculatorButton.vue")
        button_overview = language_server.request_document_overview(button_file)

        assert isinstance(button_overview, list), f"Button overview should be a list, got: {type(button_overview)}"
        assert (
            len(button_overview) >= 1
        ), f"CalculatorButton.vue should have at least 1 top-level symbol in overview, got {len(button_overview)}"

        # For Vue files, overview provides SFC structure which is useful for navigation
        # The detailed symbols are available via request_document_symbols
        button_symbol_names = [s.get("name") for s in button_overview if isinstance(s, dict)]
        assert len(button_symbol_names) >= 1, (
            f"CalculatorButton.vue should have at least 1 symbol in overview (e.g., 'CalculatorButton' or SFC section). "
            f"Found {len(button_symbol_names)} symbols: {button_symbol_names}"
        )

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_directory_overview(self, language_server: SolidLanguageServer) -> None:
        components_dir = os.path.join("src", "components")
        dir_overview = language_server.request_dir_overview(components_dir)

        # Directory overview should be a dict mapping file paths to symbol lists
        assert isinstance(dir_overview, dict), f"Directory overview should be a dict, got: {type(dir_overview)}"
        assert len(dir_overview) == 3, f"src/components directory should have exactly 3 files in overview, got {len(dir_overview)}"

        # Verify all component files are included
        expected_components = ["CalculatorButton.vue", "CalculatorInput.vue", "CalculatorDisplay.vue"]

        for expected_component in expected_components:
            # Find files that match this component name
            matching_files = [path for path in dir_overview.keys() if expected_component in path]
            assert len(matching_files) == 1, (
                f"Component '{expected_component}' should appear exactly once in directory overview. "
                f"Found {len(matching_files)} matches. All files: {list(dir_overview.keys())}"
            )

            # Verify the matched file has symbols
            file_path = matching_files[0]
            symbols = dir_overview[file_path]
            assert isinstance(symbols, list), f"Symbols for {file_path} should be a list, got {type(symbols)}"
            assert len(symbols) >= 1, f"Component {expected_component} should have at least 1 symbol in overview, got {len(symbols)}"

        # Test overview for stores directory
        stores_dir = os.path.join("src", "stores")
        stores_overview = language_server.request_dir_overview(stores_dir)

        assert isinstance(stores_overview, dict), f"Stores overview should be a dict, got: {type(stores_overview)}"
        assert (
            len(stores_overview) == 1
        ), f"src/stores directory should have exactly 1 file (calculator.ts) in overview, got {len(stores_overview)}"

        # Verify calculator.ts is included
        calculator_files = [path for path in stores_overview.keys() if "calculator.ts" in path]
        assert len(calculator_files) == 1, (
            f"calculator.ts should appear exactly once in stores directory overview. "
            f"Found {len(calculator_files)} matches. All files: {list(stores_overview.keys())}"
        )

        # Verify the store file has symbols
        store_path = calculator_files[0]
        store_symbols = stores_overview[store_path]
        store_symbol_names = [s.get("name") for s in store_symbols if isinstance(s, dict)]
        assert (
            "useCalculatorStore" in store_symbol_names
        ), f"calculator.ts should have useCalculatorStore in overview. Found {len(store_symbol_names)} symbols: {store_symbol_names}"

        # Test overview for composables directory
        composables_dir = os.path.join("src", "composables")
        composables_overview = language_server.request_dir_overview(composables_dir)

        assert isinstance(composables_overview, dict), f"Composables overview should be a dict, got: {type(composables_overview)}"
        assert (
            len(composables_overview) == 2
        ), f"src/composables directory should have exactly 2 files in overview, got {len(composables_overview)}"

        # Verify composable files are included
        expected_composables = ["useFormatter.ts", "useTheme.ts"]
        for expected_composable in expected_composables:
            matching_files = [path for path in composables_overview.keys() if expected_composable in path]
            assert len(matching_files) == 1, (
                f"Composable '{expected_composable}' should appear exactly once in directory overview. "
                f"Found {len(matching_files)} matches. All files: {list(composables_overview.keys())}"
            )
