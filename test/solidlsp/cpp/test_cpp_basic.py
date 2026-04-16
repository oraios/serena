"""
Basic tests for C/C++ language server integration (clangd and ccls).

This module tests both Language.CPP (clangd) and Language.CPP_CCLS (ccls)
using the same test repository. Tests are skipped if the respective language
server is not available.
"""

import os
import pathlib
import shutil
from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from test.conftest import get_repo_path, start_ls_context
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols


def _ccls_available() -> bool:
    return shutil.which("ccls") is not None


_cpp_servers: list[Language] = [Language.CPP]
if _ccls_available():
    _cpp_servers.append(Language.CPP_CCLS)


@pytest.mark.cpp
@pytest.mark.skipif(not _cpp_servers, reason="No C++ language server (clangd or ccls) available")
class TestCppLanguageServer:
    """Tests for C/C++ language servers (clangd and ccls)."""

    @pytest.mark.parametrize("language_server", _cpp_servers, indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        """Test that symbol tree contains expected functions."""
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "add"), "Function 'add' not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "main"), "Function 'main' not found in symbol tree"

    @pytest.mark.parametrize("language_server", _cpp_servers, indirect=True)
    def test_get_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test document symbols for a.cpp."""
        file_path = os.path.join("a.cpp")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        # Flatten nested structure if needed
        symbol_list = symbols[0] if symbols and isinstance(symbols[0], list) else symbols
        names = [s.get("name") for s in symbol_list]
        assert "main" in names, f"Expected 'main' in document symbols, got: {names}"

    @pytest.mark.parametrize("language_server", _cpp_servers, indirect=True)
    def test_find_referencing_symbols_across_files(self, language_server: SolidLanguageServer) -> None:
        """Test finding references to 'add' function across files."""
        # Locate 'add' in b.cpp
        file_path = os.path.join("b.cpp")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        symbol_list = symbols[0] if symbols and isinstance(symbols[0], list) else symbols
        add_symbol = None
        for sym in symbol_list:
            if sym.get("name") == "add":
                add_symbol = sym
                break
        assert add_symbol is not None, "Could not find 'add' function symbol in b.cpp"

        sel_start = add_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        ref_files = [ref.get("relativePath", "") for ref in refs]
        assert any("a.cpp" in ref_file for ref_file in ref_files), f"Should find reference in a.cpp, {refs=}"

        # Verify second call returns same results (stability check)
        def _ref_key(ref: dict) -> tuple:
            rp = ref.get("relativePath", "")
            rng = ref.get("range") or {}
            s = rng.get("start") or {}
            e = rng.get("end") or {}
            return (
                rp,
                s.get("line", -1),
                s.get("character", -1),
                e.get("line", -1),
                e.get("character", -1),
            )

        refs2 = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert sorted(map(_ref_key, refs2)) == sorted(map(_ref_key, refs)), "Reference results should be stable across calls"

    @pytest.mark.parametrize("language_server", _cpp_servers, indirect=True)
    @pytest.mark.xfail(
        strict=True,
        reason=("Both clangd and ccls do not support cross-file references for newly created files that were never opened by the LS."),
    )
    def test_find_references_in_newly_written_file(self, language_server: SolidLanguageServer) -> None:
        # Create a new file that references the 'add' function from b.cpp
        new_file_path = os.path.join("temp_new_file.cpp")
        new_file_abs_path = os.path.join(language_server.repository_root_path, new_file_path)

        try:
            # Write the new file with a reference to add()
            with open(new_file_abs_path, "w", encoding="utf-8") as f:
                f.write(
                    """
#include "b.hpp"

int use_add() {
    int result = add(5, 3);
    return result;
}
"""
                )

            # Open the new file so clangd knows about it
            with language_server.open_file(new_file_path):
                # Request document symbols to ensure the file is fully loaded by clangd
                new_file_symbols = language_server.request_document_symbols(new_file_path).get_all_symbols_and_roots()
                assert new_file_symbols, "New file should have symbols"

            # Verify the file stays in open_file_buffers after the context exits
            uri = pathlib.Path(new_file_abs_path).as_uri()
            assert uri in language_server.open_file_buffers, "File should remain in open_file_buffers"

            # Find the 'add' symbol in b.cpp
            b_file_path = os.path.join("b.cpp")
            symbols = language_server.request_document_symbols(b_file_path).get_all_symbols_and_roots()
            symbol_list = symbols[0] if symbols and isinstance(symbols[0], list) else symbols
            add_symbol = None
            for sym in symbol_list:
                if sym.get("name") == "add":
                    add_symbol = sym
                    break
            assert add_symbol is not None, "Could not find 'add' function symbol in b.cpp"

            # Request references for 'add'
            sel_start = add_symbol["selectionRange"]["start"]
            refs = language_server.request_references(b_file_path, sel_start["line"], sel_start["character"])
            ref_files = [ref.get("relativePath", "") for ref in refs]

            # Should find reference in the newly written file
            assert any("temp_new_file.cpp" in ref_file for ref_file in ref_files), (
                f"Should find reference in newly written temp_new_file.cpp, {ref_files=}"
            )
        finally:
            # Clean up the new file
            if os.path.exists(new_file_abs_path):
                os.remove(new_file_abs_path)

    @pytest.mark.parametrize("language_server", _cpp_servers, indirect=True)
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


@pytest.mark.cpp
class TestCppDocumentSymbolCache:
    def _copy_cpp_fixture(self, tmp_path: Path) -> Path:
        fixture_path = get_repo_path(Language.CPP)
        target_path = tmp_path / "test_repo"
        shutil.copytree(fixture_path, target_path)
        return target_path

    def test_cache_invalidates_when_clangd_context_changes(self, tmp_path: Path) -> None:
        repo_path = self._copy_cpp_fixture(tmp_path)
        ls_settings_alt = {
            Language.CPP: {
                "compile_commands_dir": ".serena-alt",
            }
        }

        main_cpp = os.path.join("a.cpp")

        def _assert_caches_loaded_and_clean(ls: SolidLanguageServer) -> None:
            assert ls._raw_document_symbols_cache, "Expected raw document-symbol cache to load from disk"
            assert ls._document_symbols_cache, "Expected document-symbol cache to load from disk"
            assert not ls._raw_document_symbols_cache_is_modified
            assert not ls._document_symbols_cache_is_modified

        def _assert_caches_empty(ls: SolidLanguageServer) -> None:
            assert ls._raw_document_symbols_cache == {}
            assert ls._document_symbols_cache == {}

        def _assert_caches_modified(ls: SolidLanguageServer) -> None:
            assert ls._raw_document_symbols_cache_is_modified
            assert ls._document_symbols_cache_is_modified

        with start_ls_context(Language.CPP, repo_path=str(repo_path), solidlsp_dir=tmp_path) as ls_default:
            _ = ls_default.request_document_symbols(main_cpp)

            default_raw_cache_version = ls_default._raw_document_symbols_cache_version()
            default_doc_cache_version = ls_default._document_symbols_cache_version()

            ls_default.save_cache()
            cache_dir = ls_default.cache_dir
            cache_files = [p for p in cache_dir.rglob("*") if p.is_file()]
            assert cache_files, f"Expected SolidLSP to create cache artifacts under {cache_dir}"

        with start_ls_context(Language.CPP, repo_path=str(repo_path), solidlsp_dir=tmp_path) as ls_default_again:
            assert ls_default_again.cache_dir == cache_dir
            _assert_caches_loaded_and_clean(ls_default_again)
            _ = ls_default_again.request_document_symbols(main_cpp)
            assert not ls_default_again._raw_document_symbols_cache_is_modified
            assert not ls_default_again._document_symbols_cache_is_modified

        with start_ls_context(
            Language.CPP,
            repo_path=str(repo_path),
            ls_specific_settings=ls_settings_alt,
            solidlsp_dir=tmp_path,
        ) as ls_alt:
            assert ls_alt.cache_dir == cache_dir
            alt_raw_cache_version = ls_alt._raw_document_symbols_cache_version()
            alt_doc_cache_version = ls_alt._document_symbols_cache_version()

            assert alt_raw_cache_version != default_raw_cache_version
            assert alt_doc_cache_version != default_doc_cache_version

            _assert_caches_empty(ls_alt)

            _ = ls_alt.request_document_symbols(main_cpp)
            _assert_caches_modified(ls_alt)
