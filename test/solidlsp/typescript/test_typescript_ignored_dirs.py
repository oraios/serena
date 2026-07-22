"""
Tests for TypeScript language server directory-ignoring behavior.

Regression test for the case where a *source* directory named `coverage`
(e.g. `src/routes/coverage/`) was hard-ignored by `is_ignored_dirname`,
hiding it from symbol tools. Only generated coverage-report dirs should be
excluded, and those are handled by gitignore.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId

pytestmark = pytest.mark.typescript


@pytest.mark.parametrize("language_server", [LanguageServerId.TYPESCRIPT], indirect=True)
class TestTypescriptIgnoredDirectories:
    """TypeScript-specific directory ignoring behavior."""

    def test_generated_dirs_still_ignored(self, language_server: SolidLanguageServer) -> None:
        assert language_server.is_ignored_dirname("node_modules"), "node_modules should be ignored"
        assert language_server.is_ignored_dirname("dist"), "dist should be ignored"
        assert language_server.is_ignored_dirname("build"), "build should be ignored"
        # VCS dir handled by the base class
        assert language_server.is_ignored_dirname(".git"), ".git should be ignored"

    def test_source_dirs_not_ignored(self, language_server: SolidLanguageServer) -> None:
        # `coverage` is a legitimate source/module name; only generated
        # coverage-report dirs (which are gitignored) should be excluded.
        assert not language_server.is_ignored_dirname("coverage"), "coverage source dir should not be ignored"
        assert not language_server.is_ignored_dirname("src"), "src should not be ignored"
        assert not language_server.is_ignored_dirname("lib"), "lib should not be ignored"
        assert not language_server.is_ignored_dirname("routes"), "routes should not be ignored"
