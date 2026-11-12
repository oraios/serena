import shutil
from pathlib import Path

import pytest

from solidlsp.ls_config import LanguageServerId
from test.conftest import get_repo_path, language_server_tests_enabled, start_ls_context


@pytest.mark.php
@pytest.mark.skipif(
    not language_server_tests_enabled(LanguageServerId.PHP_PHPACTOR),
    reason=f"{LanguageServerId.PHP_PHPACTOR.value} tests are disabled in this environment",
)
class TestPhpactorIndexPath:
    def test_references_in_project_path_with_percent_signs(self, tmp_path: Path) -> None:
        """Phpactor must remain usable for projects whose path looks like one of its own placeholders.

        Phpactor expands ``%token%`` pairs in path settings and terminates during ``initialize`` on
        tokens it does not know, so Serena must not hand it such a path as ``indexer.index_path``.
        """
        repo_path = tmp_path / "pct%weird%dir" / "test_repo"
        shutil.copytree(get_repo_path(LanguageServerId.PHP_PHPACTOR), repo_path)

        with start_ls_context(LanguageServerId.PHP_PHPACTOR, repo_path=str(repo_path)) as ls:
            references = ls.request_references(str(repo_path / "helper.php"), 2, len("function "))
            assert any(ref["uri"].endswith("index.php") for ref in references), (
                f"helperFunction calls in index.php not found in references: {references}"
            )
