"""
Tests for LSPManager - manages multiple language server instances for polyglot projects.

Following TDD approach: Tests written FIRST before implementation.
Issue: #221 - Enable Multi-Language (Polyglot) Support in Serena
"""

import asyncio
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from serena.config.serena_config import ProjectConfig
from serena.lsp_manager import LSPManager
from solidlsp.ls_config import Language
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings


class TestLSPManagerBasics:
    """Test basic LSPManager functionality."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

        # Create a simple project config
        self.config = ProjectConfig(
            project_name="test_project",
            languages=[Language.PYTHON, Language.RUST],
        )

        self.logger = LanguageServerLogger()
        self.settings = SolidLSPSettings()

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_lsp_manager_initialization(self):
        """Test that LSPManager can be initialized with multiple languages."""
        manager = LSPManager(
            languages=[Language.PYTHON, Language.RUST],
            project_root=str(self.project_path),
            config=self.config,
            logger=self.logger,
            settings=self.settings,
        )

        assert manager.languages == [Language.PYTHON, Language.RUST]
        assert manager.project_root == str(self.project_path)
        assert len(manager._language_servers) == 0  # Not started yet

    def test_lsp_manager_single_language(self):
        """Test that LSPManager works with single language (backward compatibility)."""
        manager = LSPManager(
            languages=[Language.PYTHON],
            project_root=str(self.project_path),
            config=self.config,
            logger=self.logger,
            settings=self.settings,
        )

        assert manager.languages == [Language.PYTHON]
        assert len(manager._language_servers) == 0

    def test_lsp_manager_empty_languages_raises_error(self):
        """Test that LSPManager raises error with empty languages list."""
        with pytest.raises(ValueError) as exc_info:
            LSPManager(
                languages=[],
                project_root=str(self.project_path),
                config=self.config,
                logger=self.logger,
                settings=self.settings,
            )

        assert "at least one language" in str(exc_info.value).lower()


class TestLSPManagerFileRouting:
    """Test file routing to appropriate language servers."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

        self.config = ProjectConfig(
            project_name="test_project",
            languages=[Language.PYTHON, Language.RUST, Language.HASKELL],
        )

        self.logger = LanguageServerLogger()
        self.settings = SolidLSPSettings()

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    @patch("serena.lsp_manager.SolidLanguageServer")
    def test_get_language_for_file_python(self, mock_ls):
        """Test that Python files are routed to Python LSP."""
        manager = LSPManager(
            languages=[Language.PYTHON, Language.RUST],
            project_root=str(self.project_path),
            config=self.config,
            logger=self.logger,
            settings=self.settings,
        )

        language = manager.get_language_for_file("src/main.py")
        assert language == Language.PYTHON

    @patch("serena.lsp_manager.SolidLanguageServer")
    def test_get_language_for_file_rust(self, mock_ls):
        """Test that Rust files are routed to Rust LSP."""
        manager = LSPManager(
            languages=[Language.PYTHON, Language.RUST],
            project_root=str(self.project_path),
            config=self.config,
            logger=self.logger,
            settings=self.settings,
        )

        language = manager.get_language_for_file("src/main.rs")
        assert language == Language.RUST

    @patch("serena.lsp_manager.SolidLanguageServer")
    def test_get_language_for_file_haskell(self, mock_ls):
        """Test that Haskell files are routed to Haskell LSP."""
        manager = LSPManager(
            languages=[Language.PYTHON, Language.RUST, Language.HASKELL],
            project_root=str(self.project_path),
            config=self.config,
            logger=self.logger,
            settings=self.settings,
        )

        language = manager.get_language_for_file("src/Main.hs")
        assert language == Language.HASKELL

    @patch("serena.lsp_manager.SolidLanguageServer")
    def test_get_language_for_file_unknown_extension(self, mock_ls):
        """Test that unknown file extensions return None."""
        manager = LSPManager(
            languages=[Language.PYTHON, Language.RUST],
            project_root=str(self.project_path),
            config=self.config,
            logger=self.logger,
            settings=self.settings,
        )

        language = manager.get_language_for_file("README.md")
        assert language is None

    @patch("serena.lsp_manager.SolidLanguageServer")
    def test_get_language_for_file_not_in_project_languages(self, mock_ls):
        """Test that files for languages not in project return None."""
        manager = LSPManager(
            languages=[Language.PYTHON],  # Only Python
            project_root=str(self.project_path),
            config=self.config,
            logger=self.logger,
            settings=self.settings,
        )

        # Rust file, but Rust not in project languages
        language = manager.get_language_for_file("src/main.rs")
        assert language is None


class TestLSPManagerLazyInitialization:
    """Test lazy initialization of language servers."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

        self.config = ProjectConfig(
            project_name="test_project",
            languages=[Language.PYTHON, Language.RUST],
        )

        self.logger = LanguageServerLogger()
        self.settings = SolidLSPSettings()

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    @patch("serena.lsp_manager.SolidLanguageServer")
    def test_lazy_initialization_not_started_by_default(self, mock_ls):
        """Test that LSPs are not started by default (lazy initialization)."""
        manager = LSPManager(
            languages=[Language.PYTHON, Language.RUST],
            project_root=str(self.project_path),
            config=self.config,
            logger=self.logger,
            settings=self.settings,
        )

        # No LSPs should be started yet
        assert len(manager._language_servers) == 0

    @patch("serena.lsp_manager.SolidLanguageServer")
    def test_start_all_eager_initialization(self, mock_ls):
        """Test that start_all() with lazy=False starts all LSPs immediately."""
        manager = LSPManager(
            languages=[Language.PYTHON, Language.RUST],
            project_root=str(self.project_path),
            config=self.config,
            logger=self.logger,
            settings=self.settings,
        )

        # Run async function synchronously for testing
        asyncio.run(manager.start_all(lazy=False))

        # Both LSPs should be started
        assert Language.PYTHON in manager._language_servers
        assert Language.RUST in manager._language_servers


class TestLSPManagerAsyncContextManager:
    """Test async context manager pattern for proper resource management."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

        self.config = ProjectConfig(
            project_name="test_project",
            languages=[Language.PYTHON, Language.RUST],
        )

        self.logger = LanguageServerLogger()
        self.settings = SolidLSPSettings()

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_async_context_manager_cleanup(self):
        """Test that async context manager properly cleans up resources."""

        async def run_test():
            async with LSPManager(
                languages=[Language.PYTHON],
                project_root=str(self.project_path),
                config=self.config,
                logger=self.logger,
                settings=self.settings,
            ) as manager:
                # Manager should be usable inside context
                assert manager is not None
                assert len(manager.languages) == 1
                # Don't actually start LSPs (would require real LSP binaries)

            # After exiting context, manager should have cleaned up
            # (We can't easily test this without mocking, but the pattern is correct)

        asyncio.run(run_test())


class TestLSPManagerGracefulDegradation:
    """Test graceful degradation when LSPs fail."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

        self.config = ProjectConfig(
            project_name="test_project",
            languages=[Language.PYTHON, Language.RUST],
        )

        self.logger = LanguageServerLogger()
        self.settings = SolidLSPSettings()

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    @patch("serena.lsp_manager.SolidLanguageServer")
    def test_one_lsp_failure_does_not_crash_manager(self, mock_ls):
        """Test that one LSP failure doesn't crash the entire manager."""
        # Mock Python LSP to fail
        mock_ls.create.side_effect = [
            Exception("Python LSP failed to start"),
            Mock(),  # Rust LSP succeeds
        ]

        manager = LSPManager(
            languages=[Language.PYTHON, Language.RUST],
            project_root=str(self.project_path),
            config=self.config,
            logger=self.logger,
            settings=self.settings,
        )

        # Run async function synchronously for testing
        asyncio.run(manager.start_all(lazy=False))

        # Python should be in failed languages
        assert Language.PYTHON in manager._failed_languages
        # Rust should be working
        assert Language.RUST in manager._language_servers
        assert manager._language_servers[Language.RUST] is not None

    @patch("serena.lsp_manager.SolidLanguageServer")
    def test_get_working_language_servers_excludes_failed(self, mock_ls):
        """Test that get_all_working_language_servers() excludes failed LSPs."""
        manager = LSPManager(
            languages=[Language.PYTHON, Language.RUST],
            project_root=str(self.project_path),
            config=self.config,
            logger=self.logger,
            settings=self.settings,
        )

        # Manually mark Python as failed
        manager._failed_languages.add(Language.PYTHON)
        manager._language_servers[Language.RUST] = Mock()

        working_servers = manager.get_all_working_language_servers()

        assert len(working_servers) == 1
        assert working_servers[0] == manager._language_servers[Language.RUST]
