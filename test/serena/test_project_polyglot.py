"""
Tests for Project class polyglot support - Phase 1.3 integration.

Following TDD approach: Tests written FIRST before implementation.
Issue: #221 - Enable Multi-Language (Polyglot) Support in Serena
"""

import shutil
import tempfile
from pathlib import Path

import pytest
from serena.config.serena_config import ProjectConfig
from serena.project import Project
from solidlsp.ls_config import Language


class TestProjectPolyglotIntegration:
    """Test Project class integration with LSPManager."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

        # Create a simple polyglot project config
        self.config = ProjectConfig(
            project_name="test_polyglot_project",
            languages=[Language.PYTHON, Language.RUST, Language.HASKELL],
        )

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_project_has_create_lsp_manager_method(self):
        """Test that Project class has create_lsp_manager method."""
        project = Project(
            project_root=str(self.project_path),
            project_config=self.config,
        )

        assert hasattr(project, "create_lsp_manager")
        assert callable(getattr(project, "create_lsp_manager"))

    def test_create_lsp_manager_returns_lsp_manager(self):
        """Test that create_lsp_manager returns an LSPManager instance."""
        from serena.lsp_manager import LSPManager

        project = Project(
            project_root=str(self.project_path),
            project_config=self.config,
        )

        lsp_manager = project.create_lsp_manager()

        assert isinstance(lsp_manager, LSPManager)
        assert lsp_manager.languages == [Language.PYTHON, Language.RUST, Language.HASKELL]
        assert lsp_manager.project_root == str(self.project_path)

    def test_create_lsp_manager_with_single_language(self):
        """Test that create_lsp_manager works with single language (backward compat)."""
        from serena.lsp_manager import LSPManager

        single_lang_config = ProjectConfig(
            project_name="test_single_lang",
            languages=[Language.PYTHON],
        )

        project = Project(
            project_root=str(self.project_path),
            project_config=single_lang_config,
        )

        lsp_manager = project.create_lsp_manager()

        assert isinstance(lsp_manager, LSPManager)
        assert lsp_manager.languages == [Language.PYTHON]

    def test_create_language_server_still_works(self):
        """Test that create_language_server still works for backward compatibility."""
        from solidlsp import SolidLanguageServer

        project = Project(
            project_root=str(self.project_path),
            project_config=self.config,
        )

        # Should create LSP for first language (backward compat)
        lsp = project.create_language_server()

        assert isinstance(lsp, SolidLanguageServer)
        # Should use first language from config
        assert lsp.language == Language.PYTHON

    def test_project_language_property_returns_first_language(self):
        """Test that language property returns first language (backward compat)."""
        project = Project(
            project_root=str(self.project_path),
            project_config=self.config,
        )

        # Should return first language for backward compatibility
        assert project.language == Language.PYTHON

    def test_project_languages_property_returns_all_languages(self):
        """Test that languages property returns all languages."""
        project = Project(
            project_root=str(self.project_path),
            project_config=self.config,
        )

        assert hasattr(project, "languages")
        assert project.languages == [Language.PYTHON, Language.RUST, Language.HASKELL]

