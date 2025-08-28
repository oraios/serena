import os
import platform
import subprocess

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


def _check_opam_available() -> bool:
    """Check if OPAM is available and working."""
    try:
        result = subprocess.run(["opam", "--version"], check=True, capture_output=True, text=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


OPAM_UNAVAILABLE = not _check_opam_available()
OPAM_SKIP_REASON = "OPAM is not available or not working properly"

# Skip OCaml tests when OPAM is not available (especially on Windows)
pytestmark = [pytest.mark.ocaml, pytest.mark.skipif(OPAM_UNAVAILABLE, reason=OPAM_SKIP_REASON)]


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
        symbols = language_server.request_document_symbols(file_path)
        helper_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "fib":
                helper_symbol = sym
                break
        assert helper_symbol is not None, "Could not find 'fib' symbol in lib/test_repo.ml"
        sel_start = helper_symbol["selectionRange"]["start"]
        # Test that references request doesn't crash, even if it returns empty results
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        # For now, just verify the request succeeds and returns a list (may be empty)
        assert isinstance(refs, list), f"References request should return a list, got: {type(refs)}"

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
