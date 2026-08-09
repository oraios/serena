"""
Tests for Wolfram language server directory ignoring functionality.

These validate that Mathematica-installation-specific directories are ignored,
while common, generic directory names that real Wolfram projects legitimately
use for their own content (e.g. a paclet's own Documentation/ folder) are not
silently excluded from indexing. See the discussion on PR #1108.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.conftest import language_server_tests_enabled

pytestmark = [
    pytest.mark.wolfram,
    pytest.mark.skipif(
        not language_server_tests_enabled(LanguageServerId.WOLFRAM), reason="Wolfram tests disabled (WolframKernel not available)"
    ),
]


@pytest.mark.parametrize("language_server", [LanguageServerId.WOLFRAM], indirect=True)
class TestWolframIgnoredDirectories:
    def test_mathematica_specific_directories_are_ignored(self, language_server: SolidLanguageServer) -> None:
        """Directories that are specific to a Mathematica/Wolfram installation layout should be ignored."""
        assert language_server.is_ignored_dirname(".Wolfram"), ".Wolfram should be ignored"
        assert language_server.is_ignored_dirname("SystemFiles"), "SystemFiles should be ignored"

    def test_generic_project_directories_are_not_ignored(self, language_server: SolidLanguageServer) -> None:
        """
        Generic directory names must not be excluded just because they also happen to
        appear in a Mathematica installation. Real Wolfram projects (e.g. paclets) use
        these names for their own real content -- WolframResearch/LSPServer itself ships
        an actual Documentation/ folder with reference pages that must remain indexable.
        """
        assert not language_server.is_ignored_dirname("Documentation"), "Documentation should not be ignored"
        assert not language_server.is_ignored_dirname("FrontEnd"), "FrontEnd should not be ignored"

    def test_common_directories_not_ignored(self, language_server: SolidLanguageServer) -> None:
        assert not language_server.is_ignored_dirname("src"), "src should not be ignored"
        assert not language_server.is_ignored_dirname("lib"), "lib should not be ignored"
        assert not language_server.is_ignored_dirname("Kernel"), "Kernel should not be ignored"
