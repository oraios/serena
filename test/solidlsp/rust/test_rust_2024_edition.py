import os
from pathlib import Path

import pytest

from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from test.conftest import create_ls


@pytest.mark.rust
class TestRust2024EditionLanguageServer:
    @classmethod
    def setup_class(cls):
        """Set up the test class with the Rust 2024 edition test repository."""
        cls.test_repo_2024_path = Path(__file__).parent.parent.parent / "resources" / "repos" / "rust" / "test_repo_2024"

        if not cls.test_repo_2024_path.exists():
            pytest.skip("Rust 2024 edition test repository not found")

        # Create and start the language server for the 2024 edition repo
        cls.language_server = create_ls(Language.RUST, str(cls.test_repo_2024_path))
        cls.language_server.start()

    @classmethod
    def teardown_class(cls):
        """Clean up the language server."""
        if hasattr(cls, "language_server"):
            cls.language_server.stop()

    def test_find_references_raw(self) -> None:
        # Test finding references to the 'add' function defined in main.rs
        file_path = os.path.join("src", "main.rs")
        symbols = self.language_server.request_document_symbols(file_path)
        add_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "add":
                add_symbol = sym
                break
        assert add_symbol is not None, "Could not find 'add' function symbol in main.rs"
        sel_start = add_symbol["selectionRange"]["start"]
        refs = self.language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        # The add function should be referenced within main.rs itself (in the main function)
        assert any("main.rs" in ref.get("relativePath", "") for ref in refs), "main.rs should reference add function"

    def test_find_symbol(self) -> None:
        symbols = self.language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "main"), "main function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "add"), "add function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "multiply"), "multiply function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Calculator"), "Calculator struct not found in symbol tree"

    def test_find_referencing_symbols_multiply(self) -> None:
        # Find references to 'multiply' function defined in lib.rs
        file_path = os.path.join("src", "lib.rs")
        symbols = self.language_server.request_document_symbols(file_path)
        multiply_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "multiply":
                multiply_symbol = sym
                break
        assert multiply_symbol is not None, "Could not find 'multiply' function symbol in lib.rs"
        sel_start = multiply_symbol["selectionRange"]["start"]
        refs = self.language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        # The multiply function exists but may not be referenced anywhere, which is fine
        # This test just verifies we can find the symbol and request references without error
        assert isinstance(refs, list), "Should return a list of references (even if empty)"

    def test_find_calculator_struct_and_impl(self) -> None:
        # Test finding the Calculator struct and its impl block
        file_path = os.path.join("src", "lib.rs")
        symbols = self.language_server.request_document_symbols(file_path)

        # Find the Calculator struct
        calculator_struct = None
        calculator_impl = None
        for sym in symbols[0]:
            if sym.get("name") == "Calculator" and sym.get("kind") == 23:  # Struct kind
                calculator_struct = sym
            elif sym.get("name") == "Calculator" and sym.get("kind") == 11:  # Interface/Impl kind
                calculator_impl = sym

        assert calculator_struct is not None, "Could not find 'Calculator' struct symbol in lib.rs"

        # The struct should have the 'result' field
        struct_children = calculator_struct.get("children", [])
        field_names = [child.get("name") for child in struct_children]
        assert "result" in field_names, "Calculator struct should have 'result' field"

        # Find the impl block and check its methods
        if calculator_impl is not None:
            impl_children = calculator_impl.get("children", [])
            method_names = [child.get("name") for child in impl_children]
            assert "new" in method_names, "Calculator impl should have 'new' method"
            assert "add" in method_names, "Calculator impl should have 'add' method"
            assert "get_result" in method_names, "Calculator impl should have 'get_result' method"

    def test_overview_methods(self) -> None:
        symbols = self.language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "main"), "main missing from overview"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "add"), "add missing from overview"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "multiply"), "multiply missing from overview"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Calculator"), "Calculator missing from overview"

    def test_rust_2024_edition_specific(self) -> None:
        # Verify we're actually working with the 2024 edition repository
        cargo_toml_path = self.test_repo_2024_path / "Cargo.toml"
        assert cargo_toml_path.exists(), "Cargo.toml should exist in test repository"

        with open(cargo_toml_path) as f:
            content = f.read()
            assert 'edition = "2024"' in content, "Should be using Rust 2024 edition"
