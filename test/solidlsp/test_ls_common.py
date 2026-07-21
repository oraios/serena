import os
from collections.abc import Sequence

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from test.conftest import PYTHON_LANGUAGE_BACKENDS, start_ls_context


class TestLanguageServerCommonFunctionality:
    """Test common functionality of SolidLanguageServer base implementation (not language-specific behaviour)."""

    @pytest.mark.parametrize("language_server", PYTHON_LANGUAGE_BACKENDS, indirect=True)
    def test_open_file_cache_invalidate(self, language_server: SolidLanguageServer) -> None:
        """
        Tests that the file buffer cache is invalidated when the file is changed on disk.
        """
        file_path = os.path.join(language_server.repository_root_path, "test_open_file.py")
        test_string1 = "# foo"
        test_string2 = "# bar"

        with open(file_path, "w") as f:
            f.write(test_string1)

        try:
            with language_server.open_file(file_path) as fb:
                assert fb.contents == test_string1

                # apply external change to file
                with open(file_path, "w") as f:
                    f.write(test_string2)

                # Explicitly bump mtime into the future so the cache sees a change.
                # Relying on natural mtime advancement is flaky because many filesystems
                # (ext4, tmpfs) have only 1-second mtime granularity, and both writes
                # can land in the same second.
                stat = os.stat(file_path)
                os.utime(file_path, (stat.st_atime, stat.st_mtime + 2))

                # check that the file buffer has been invalidated and reloaded
                assert fb.contents == test_string2

        finally:
            os.remove(file_path)

    def test_workspace_folders_affect_full_symbol_tree(self):
        """
        Tests that workspace folder configurations are respected when requesting the full symbol tree.
        """

        def check(langsrv: SolidLanguageServer, present: Sequence[str] = (), absent: Sequence[str] = ()) -> None:
            symbols = langsrv.request_full_symbol_tree()
            for name in present:
                assert SymbolUtils.symbol_tree_contains_name(symbols, name)
            for name in absent:
                assert not SymbolUtils.symbol_tree_contains_name(symbols, name)

        symbols_in_subfolder_test_repo = ["OuterClass", "UserService"]
        symbols_in_subfolder_scripts = ["parse_args", "create_sample_users"]
        all_symbols = symbols_in_subfolder_test_repo + symbols_in_subfolder_scripts

        with start_ls_context(language=Language.PYTHON, workspace_folders=["."]) as ls:
            ls.request_full_symbol_tree()
            check(ls, present=all_symbols)

        with start_ls_context(language=Language.PYTHON, workspace_folders=["./test_repo"]) as ls:
            ls.request_full_symbol_tree()
            check(ls, present=symbols_in_subfolder_test_repo, absent=symbols_in_subfolder_scripts)

        with start_ls_context(language=Language.PYTHON, workspace_folders=["./scripts"]) as ls:
            ls.request_full_symbol_tree()
            check(ls, present=symbols_in_subfolder_scripts, absent=symbols_in_subfolder_test_repo)

            # test that explicit requests for symbols in other workspace folders are rejected
            with pytest.raises(ValueError, match="outside"):
                ls.request_full_symbol_tree(within_relative_path="./test_repo")
