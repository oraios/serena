"""
Tests for TOML language server directory ignoring functionality.

These tests validate that the Taplo language server correctly ignores
TOML-specific directories like target, .cargo, and node_modules.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language

pytestmark = pytest.mark.toml


@pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
class TestTomlIgnoredDirectories:
    """Test TOML-specific directory ignoring behavior."""

    def test_default_ignored_directories(self, language_server: SolidLanguageServer) -> None:
        """Test that default TOML directories are ignored."""
        # Test that TOML/Rust/Node-specific directories are ignored by default
        assert language_server.is_ignored_dirname("target"), "target should be ignored"
        assert language_server.is_ignored_dirname(".cargo"), ".cargo should be ignored"
        assert language_server.is_ignored_dirname("node_modules"), "node_modules should be ignored"

        # Directories starting with . are ignored by base class
        assert language_server.is_ignored_dirname(".git"), ".git should be ignored"
        assert language_server.is_ignored_dirname(".venv"), ".venv should be ignored"

    def test_important_directories_not_ignored(self, language_server: SolidLanguageServer) -> None:
        """Test that important directories are not ignored."""
        # Common project directories should not be ignored
        assert not language_server.is_ignored_dirname("src"), "src should not be ignored"
        assert not language_server.is_ignored_dirname("crates"), "crates should not be ignored"
        assert not language_server.is_ignored_dirname("lib"), "lib should not be ignored"
        assert not language_server.is_ignored_dirname("tests"), "tests should not be ignored"
        assert not language_server.is_ignored_dirname("config"), "config should not be ignored"

    def test_cargo_related_directories(self, language_server: SolidLanguageServer) -> None:
        """Test Cargo/Rust-related directory handling."""
        # Rust build directories should be ignored
        assert language_server.is_ignored_dirname("target"), "target (Rust build) should be ignored"
        assert language_server.is_ignored_dirname(".cargo"), ".cargo should be ignored"

        # But important Rust directories should not be ignored
        assert not language_server.is_ignored_dirname("benches"), "benches should not be ignored"
        assert not language_server.is_ignored_dirname("examples"), "examples should not be ignored"

    def test_various_cache_directories(self, language_server: SolidLanguageServer) -> None:
        """Test various cache and temporary directories are ignored."""
        # Directories starting with . are ignored by base class
        assert language_server.is_ignored_dirname(".cache"), ".cache should be ignored"

        # IDE directories (start with .)
        assert language_server.is_ignored_dirname(".idea"), ".idea should be ignored"
        assert language_server.is_ignored_dirname(".vscode"), ".vscode should be ignored"

        # Note: __pycache__ is NOT ignored by TOML server (only Python servers ignore it)
        assert not language_server.is_ignored_dirname("__pycache__"), "__pycache__ is not TOML-specific"
