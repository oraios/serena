import os
from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.go
class TestGoLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.GO], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "main"), "main function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Helper"), "Helper function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "DemoStruct"), "DemoStruct not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.GO], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("main.go")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        helper_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "Helper":
                helper_symbol = sym
                break
        assert helper_symbol is not None, "Could not find 'Helper' function symbol in main.go"
        sel_start = helper_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert any("main.go" in ref.get("uri", "") for ref in refs), "Expected at least one reference result to point at main.go"


def _filter_symbols_by_name_in_repo(symbols: list | None, target_name: str, repo_name: str = "test_repo") -> list:
    """Filter workspace symbols to exact name matches in the test repo."""
    if symbols is None:
        return []
    return [s for s in symbols if s.get("name") == target_name and repo_name in s.get("location", {}).get("uri", "")]


@pytest.mark.go
class TestGoBuildTags:
    """Tests for Go build tag/constraint support."""

    def _copy_go_fixture(self, tmp_path: Path) -> Path:
        """Copy Go fixture repo into tmp_path."""
        import shutil

        from test.conftest import get_repo_path

        fixture_path = get_repo_path(Language.GO)
        target_path = tmp_path / "test_repo"

        shutil.copytree(fixture_path, target_path)
        return target_path

    def test_default_context_contains_xnotfoo(self, tmp_path: Path) -> None:
        """Default build context should contain XNotFoo and not XFoo."""
        from test.conftest import start_ls_context

        repo_path = self._copy_go_fixture(tmp_path)

        with start_ls_context(Language.GO, repo_path=str(repo_path), solidlsp_dir=tmp_path) as ls:
            xnotfoo_symbols = ls.request_workspace_symbol("XNotFoo")
            xfoo_symbols = ls.request_workspace_symbol("XFoo")

            xnotfoo_matches = _filter_symbols_by_name_in_repo(xnotfoo_symbols, "XNotFoo")
            xfoo_matches = _filter_symbols_by_name_in_repo(xfoo_symbols, "XFoo")

            assert len(xnotfoo_matches) > 0, "Default context should contain XNotFoo"
            assert len(xfoo_matches) == 0, "Default context should NOT contain XFoo"

    def test_foo_context_contains_xfoo(self, tmp_path: Path) -> None:
        """Build context with -tags=foo should contain XFoo and not XNotFoo."""
        from test.conftest import start_ls_context

        repo_path = self._copy_go_fixture(tmp_path)

        ls_settings = {
            Language.GO: {
                "gopls_settings": {
                    "buildFlags": ["-tags=foo"],
                },
            },
        }

        with start_ls_context(Language.GO, repo_path=str(repo_path), ls_specific_settings=ls_settings, solidlsp_dir=tmp_path) as ls:
            xfoo_symbols = ls.request_workspace_symbol("XFoo")
            xnotfoo_symbols = ls.request_workspace_symbol("XNotFoo")

            xfoo_matches = _filter_symbols_by_name_in_repo(xfoo_symbols, "XFoo")
            xnotfoo_matches = _filter_symbols_by_name_in_repo(xnotfoo_symbols, "XNotFoo")

            assert len(xfoo_matches) > 0, "Foo context should contain XFoo"
            assert len(xnotfoo_matches) == 0, "Foo context should NOT contain XNotFoo"

    def test_disk_cache_is_invalidated_on_build_context_switch(self, tmp_path: Path) -> None:
        """Go build context switches must not reuse persisted SolidLSP document-symbol caches."""
        import pickle

        from test.conftest import start_ls_context

        repo_path = self._copy_go_fixture(tmp_path)

        ls_settings_foo = {
            Language.GO: {
                "gopls_settings": {
                    "buildFlags": ["-tags=foo"],
                },
            },
        }

        main_go = os.path.join("main.go")

        def _assert_caches_loaded_and_clean(ls: SolidLanguageServer) -> None:
            # White-box assertions: SolidLanguageServer currently has no public API to verify that
            # caches were loaded from disk vs created lazily on first request.
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

        # Run 1 (default context): populate caches and persist them to disk.
        with start_ls_context(Language.GO, repo_path=str(repo_path), solidlsp_dir=tmp_path) as ls_default:
            _ = ls_default.request_document_symbols(main_go)

            default_raw_cache_version = ls_default._raw_document_symbols_cache_version()
            default_doc_cache_version = ls_default._document_symbols_cache_version()

            ls_default.save_cache()
            cache_dir = ls_default.cache_dir

            cache_files = [p for p in cache_dir.rglob("*") if p.is_file()]
            assert cache_files, f"Expected SolidLSP to create cache artifacts under {cache_dir}"

            versioned_cache_files: list[tuple[Path, object]] = []
            for p in cache_files:
                try:
                    with p.open("rb") as f:
                        data = pickle.load(f)
                except Exception:
                    continue
                if isinstance(data, dict) and "__cache_version" in data:
                    versioned_cache_files.append((p, data["__cache_version"]))

            assert versioned_cache_files, f"Expected at least one SolidLSP cache file with a __cache_version under {cache_dir}"
            saved_versions = {v for _, v in versioned_cache_files}
            assert (
                default_raw_cache_version in saved_versions or default_doc_cache_version in saved_versions
            ), "Expected at least one persisted cache to match the default-context cache version"

        # Run 2 (default context again): prove that persisted caches are actually loaded and used.
        with start_ls_context(Language.GO, repo_path=str(repo_path), solidlsp_dir=tmp_path) as ls_default_again:
            assert ls_default_again.cache_dir == cache_dir

            _assert_caches_loaded_and_clean(ls_default_again)

            _ = ls_default_again.request_document_symbols(main_go)

            # A cache hit should not mark caches as modified.
            assert not ls_default_again._raw_document_symbols_cache_is_modified
            assert not ls_default_again._document_symbols_cache_is_modified

        # Run 3 (foo context): the same on-disk cache directory exists, but MUST be treated as stale.
        with start_ls_context(
            Language.GO,
            repo_path=str(repo_path),
            ls_specific_settings=ls_settings_foo,
            solidlsp_dir=tmp_path,
        ) as ls_foo:
            assert ls_foo.cache_dir == cache_dir

            foo_raw_cache_version = ls_foo._raw_document_symbols_cache_version()
            foo_doc_cache_version = ls_foo._document_symbols_cache_version()

            assert foo_raw_cache_version != default_raw_cache_version
            assert foo_doc_cache_version != default_doc_cache_version

            # Different build context => persisted caches must not be loaded.
            _assert_caches_empty(ls_foo)

            _ = ls_foo.request_document_symbols(main_go)

            # A cache miss should repopulate and mark caches modified.
            _assert_caches_modified(ls_foo)
