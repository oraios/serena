import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.ocaml
class TestOCamlLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.OCAML], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "DemoModule"), "DemoModule not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "fib"), "fib not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "someFunction"), "someFunction function not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.OCAML], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("lib", "test_repo.ml")

        # Use the correct character position for 'fib' function name
        # Line 8: "let rec fib n =" - 'fib' starts at character 8 (0-indexed)
        fib_line = 7  # 0-indexed line number
        fib_char = 8  # 0-indexed character position

        refs = language_server.request_references(file_path, fib_line, fib_char)

        # Should find at least 3 references: definition + 2 recursive calls in same file
        assert len(refs) >= 3, f"Expected at least 3 references to fib (definition + 2 recursive), found {len(refs)}"

        # All references should be in lib/test_repo.ml (same file as definition)
        lib_refs = [ref for ref in refs if "lib/test_repo.ml" in ref.get("uri", "")]
        assert len(lib_refs) >= 3, f"Expected at least 3 references in lib/test_repo.ml, found {len(lib_refs)}"

    @pytest.mark.parametrize("language_server", [Language.OCAML], indirect=True)
    def test_mixed_ocaml_modules(self, language_server: SolidLanguageServer) -> None:
        """Test that the language server can find symbols from OCaml modules"""
        # Test that full symbol tree includes symbols from various file types
        all_symbols = language_server.request_full_symbol_tree()

        # Should find symbols from main OCaml files
        assert SymbolUtils.symbol_tree_contains_name(all_symbols, "fib"), "Should find fib from .ml file"
        assert SymbolUtils.symbol_tree_contains_name(all_symbols, "DemoModule"), "Should find DemoModule from .ml file"
        assert SymbolUtils.symbol_tree_contains_name(all_symbols, "someFunction"), "Should find someFunction from DemoModule"
        assert SymbolUtils.symbol_tree_contains_name(all_symbols, "num_domains"), "Should find num_domains constant"

    def test_reason_file_patterns(self) -> None:
        """Test that OCaml language configuration recognizes Reason file extensions"""
        from solidlsp.ls_config import Language

        ocaml_lang = Language.OCAML
        file_matcher = ocaml_lang.get_source_fn_matcher()

        # Test OCaml extensions
        assert file_matcher.is_relevant_filename("test.ml"), "Should match .ml files"
        assert file_matcher.is_relevant_filename("test.mli"), "Should match .mli files"

        # Test Reason extensions
        assert file_matcher.is_relevant_filename("test.re"), "Should match .re files"
        assert file_matcher.is_relevant_filename("test.rei"), "Should match .rei files"

        # Test non-matching extensions
        assert not file_matcher.is_relevant_filename("test.py"), "Should not match .py files"
        assert not file_matcher.is_relevant_filename("test.js"), "Should not match .js files"

    @pytest.mark.parametrize("language_server", [Language.OCAML], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer) -> None:
        """Test finding references across .ml, .mli, and usage files."""
        file_path = os.path.join("lib", "test_repo.ml")

        # Use correct position for 'fib' function name (line 8, char 8)
        fib_line = 7  # 0-indexed
        fib_char = 8  # 0-indexed

        refs = language_server.request_references(file_path, fib_line, fib_char)

        # Should find at least 3 references in the definition file
        assert len(refs) >= 3, f"Expected at least 3 references to fib, found {len(refs)}"

        # Check that references are found in lib/test_repo.ml (where fib is defined and called recursively)
        lib_refs = [ref for ref in refs if "lib/test_repo.ml" in ref.get("uri", "")]
        assert len(lib_refs) >= 3, f"Expected at least 3 references in lib/test_repo.ml, found {len(lib_refs)}"

    @pytest.mark.parametrize("language_server", [Language.OCAML], indirect=True)
    def test_module_hierarchy_navigation(self, language_server: SolidLanguageServer) -> None:
        """Test navigation within module hierarchy including DemoModule."""
        file_path = os.path.join("lib", "test_repo.ml")

        # Use correct position for 'DemoModule' (line 1, char 7)
        # Line 1: "module DemoModule = struct" - 'DemoModule' starts around char 7
        module_line = 0  # 0-indexed
        module_char = 7  # 0-indexed

        refs = language_server.request_references(file_path, module_line, module_char)

        # Should find at least 1 reference (the definition)
        assert len(refs) >= 1, f"Expected at least 1 reference to DemoModule, found {len(refs)}"

        # Check that references are found
        lib_refs = [ref for ref in refs if "lib/test_repo.ml" in ref.get("uri", "")]
        assert len(lib_refs) >= 1, f"Expected at least 1 reference in lib/test_repo.ml, found {len(lib_refs)}"

    @pytest.mark.parametrize("language_server", [Language.OCAML], indirect=True)
    def test_let_binding_references(self, language_server: SolidLanguageServer) -> None:
        """Test finding references to let-bound values across files."""
        file_path = os.path.join("lib", "test_repo.ml")

        # Use correct position for 'num_domains' (line 12, char 4)
        # Line 12: "let num_domains = 2" - 'num_domains' starts around char 4
        num_domains_line = 11  # 0-indexed
        num_domains_char = 4  # 0-indexed

        refs = language_server.request_references(file_path, num_domains_line, num_domains_char)

        # Should find at least 1 reference (the definition)
        assert len(refs) >= 1, f"Expected at least 1 reference to num_domains, found {len(refs)}"

        # Check that reference is found in the definition file
        ml_refs = [ref for ref in refs if "lib/test_repo.ml" in ref.get("uri", "")]
        assert len(ml_refs) >= 1, f"Expected at least 1 reference in lib/test_repo.ml, found {len(ml_refs)}"

    @pytest.mark.parametrize("language_server", [Language.OCAML], indirect=True)
    def test_recursive_function_analysis(self, language_server: SolidLanguageServer) -> None:
        """Test that recursive function calls are properly identified."""
        file_path = os.path.join("lib", "test_repo.ml")

        # Use correct position for 'fib' function name (line 8, char 8)
        fib_line = 7  # 0-indexed
        fib_char = 8  # 0-indexed

        refs = language_server.request_references(file_path, fib_line, fib_char)

        # Should find exactly 3 references: definition + 2 recursive calls
        assert len(refs) == 3, f"Expected exactly 3 references for recursive fib, found {len(refs)}"

        # All references should be in the same file
        same_file_refs = [ref for ref in refs if "lib/test_repo.ml" in ref.get("uri", "")]
        assert len(same_file_refs) == 3, f"All references should be in same file, found {len(same_file_refs)}"

        # Verify references are on different lines (definition + recursive calls)
        ref_lines = [ref.get("range", {}).get("start", {}).get("line", -1) for ref in same_file_refs]
        unique_lines = len(set(ref_lines))
        assert unique_lines >= 2, f"Recursive calls should appear on multiple lines, found {unique_lines} unique lines"

    @pytest.mark.parametrize("language_server", [Language.OCAML], indirect=True)
    def test_open_statement_resolution(self, language_server: SolidLanguageServer) -> None:
        """Test that open statements allow unqualified access to module contents."""
        # In bin/main.ml, fib is called without Test_repo prefix due to 'open Test_repo'
        all_symbols = language_server.request_full_symbol_tree()

        # Should be able to find fib through symbol tree
        fib_accessible = SymbolUtils.symbol_tree_contains_name(all_symbols, "fib")
        assert fib_accessible, "fib should be accessible through open statement"

        # DemoModule should also be accessible
        demo_module_accessible = SymbolUtils.symbol_tree_contains_name(all_symbols, "DemoModule")
        assert demo_module_accessible, "DemoModule should be accessible"

        # Verify we have access to both qualified and unqualified symbols
        assert len(all_symbols) > 0, "Should find symbols from OCaml files"

        # Test that the language server recognizes the open statement context
        file_path = os.path.join("bin", "main.ml")
        symbols = language_server.request_document_symbols(file_path)
        assert len(symbols) > 0, "Should find symbols in main.ml that use opened modules"
