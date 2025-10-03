"""
Tests for ProjectConfig polyglot (multi-language) support.

Following TDD approach: Tests written FIRST before implementation.
Issue: #221 - Enable Multi-Language (Polyglot) Support in Serena
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from serena.config.serena_config import ProjectConfig
from solidlsp.ls_config import Language


class TestProjectConfigPolyglot:
    """Test class for ProjectConfig polyglot functionality."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    # ========================================================================
    # Backward Compatibility Tests
    # ========================================================================

    def test_single_language_still_works(self):
        """Test that existing single-language projects continue to work."""
        # Create project.yml with single language (old format)
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir()
        project_yml = serena_dir / "project.yml"
        project_yml.write_text(
            "project_name: test_project\n"
            "language: rust\n"
            "root: .\n"
        )

        # Load config
        config = ProjectConfig.load(self.project_path)

        # Should work with backward compatibility
        assert config.project_name == "test_project"
        assert config.languages == [Language.RUST]
        # Backward compatibility property
        assert config.language == Language.RUST

    def test_single_language_converted_to_list(self):
        """Test that single language is automatically converted to list."""
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir()
        project_yml = serena_dir / "project.yml"
        project_yml.write_text(
            "project_name: test_project\n"
            "language: python\n"
            "root: .\n"
        )

        config = ProjectConfig.load(self.project_path)

        # Single language should be converted to list internally
        assert isinstance(config.languages, list)
        assert len(config.languages) == 1
        assert config.languages[0] == Language.PYTHON

    # ========================================================================
    # Multi-Language Configuration Tests
    # ========================================================================

    def test_multiple_languages_list_format(self):
        """Test that multiple languages can be specified as a list."""
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir()
        project_yml = serena_dir / "project.yml"
        project_yml.write_text(
            "project_name: polyglot_project\n"
            "languages:\n"
            "  - rust\n"
            "  - haskell\n"
            "  - python\n"
            "root: .\n"
        )

        config = ProjectConfig.load(self.project_path)

        assert config.project_name == "polyglot_project"
        assert len(config.languages) == 3
        assert Language.RUST in config.languages
        assert Language.HASKELL in config.languages
        assert Language.PYTHON in config.languages

    def test_languages_order_preserved(self):
        """Test that language order is preserved from configuration."""
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir()
        project_yml = serena_dir / "project.yml"
        project_yml.write_text(
            "project_name: test_project\n"
            "languages:\n"
            "  - haskell\n"
            "  - rust\n"
            "  - python\n"
            "root: .\n"
        )

        config = ProjectConfig.load(self.project_path)

        # Order should be preserved
        assert config.languages[0] == Language.HASKELL
        assert config.languages[1] == Language.RUST
        assert config.languages[2] == Language.PYTHON

    def test_invalid_language_in_list_raises_error(self):
        """Test that invalid language in list raises ValueError."""
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir()
        project_yml = serena_dir / "project.yml"
        project_yml.write_text(
            "project_name: test_project\n"
            "languages:\n"
            "  - rust\n"
            "  - invalid_language\n"
            "  - python\n"
            "root: .\n"
        )

        with pytest.raises(ValueError) as exc_info:
            ProjectConfig.load(self.project_path)

        error_message = str(exc_info.value)
        assert "Invalid language" in error_message
        assert "invalid_language" in error_message

    def test_empty_languages_list_raises_error(self):
        """Test that empty languages list raises ValueError."""
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir()
        project_yml = serena_dir / "project.yml"
        project_yml.write_text(
            "project_name: test_project\n"
            "languages: []\n"
            "root: .\n"
        )

        with pytest.raises(ValueError) as exc_info:
            ProjectConfig.load(self.project_path)

        error_message = str(exc_info.value)
        assert "at least one language" in error_message.lower()

    def test_duplicate_languages_removed(self):
        """Test that duplicate languages are removed from list."""
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir()
        project_yml = serena_dir / "project.yml"
        project_yml.write_text(
            "project_name: test_project\n"
            "languages:\n"
            "  - rust\n"
            "  - python\n"
            "  - rust\n"  # Duplicate
            "  - python\n"  # Duplicate
            "root: .\n"
        )

        config = ProjectConfig.load(self.project_path)

        # Duplicates should be removed, order of first occurrence preserved
        assert len(config.languages) == 2
        assert config.languages[0] == Language.RUST
        assert config.languages[1] == Language.PYTHON

    # ========================================================================
    # Backward Compatibility Property Tests
    # ========================================================================

    def test_language_property_returns_first_language(self):
        """Test that .language property returns first language for backward compatibility."""
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir()
        project_yml = serena_dir / "project.yml"
        project_yml.write_text(
            "project_name: test_project\n"
            "languages:\n"
            "  - rust\n"
            "  - haskell\n"
            "  - python\n"
            "root: .\n"
        )

        config = ProjectConfig.load(self.project_path)

        # Backward compatibility: .language returns first language
        assert config.language == Language.RUST
        assert config.language == config.languages[0]

    def test_language_property_with_single_language(self):
        """Test that .language property works with single language."""
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir()
        project_yml = serena_dir / "project.yml"
        project_yml.write_text(
            "project_name: test_project\n"
            "language: python\n"
            "root: .\n"
        )

        config = ProjectConfig.load(self.project_path)

        assert config.language == Language.PYTHON
        assert config.languages == [Language.PYTHON]

    # ========================================================================
    # Autogeneration Tests (Future Phase 2)
    # ========================================================================

    @pytest.mark.skip(reason="Phase 2: Auto-detection of multiple languages not yet implemented")
    def test_autogenerate_detects_multiple_languages(self):
        """Test that autogenerate can detect multiple languages in a project."""
        # Create files in multiple languages
        (self.project_path / "main.rs").write_text("fn main() {}")
        (self.project_path / "script.py").write_text("print('hello')")
        (self.project_path / "Main.hs").write_text("main = putStrLn \"hello\"")

        config = ProjectConfig.autogenerate(self.project_path, save_to_disk=False)

        # Should detect all three languages
        assert len(config.languages) >= 2  # At least detect multiple
        # Dominant language should be first
        assert config.language in [Language.RUST, Language.PYTHON, Language.HASKELL]

    # ========================================================================
    # Configuration Validation Tests
    # ========================================================================

    def test_both_language_and_languages_specified_raises_error(self):
        """Test that specifying both 'language' and 'languages' raises error."""
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir()
        project_yml = serena_dir / "project.yml"
        project_yml.write_text(
            "project_name: test_project\n"
            "language: rust\n"
            "languages:\n"
            "  - python\n"
            "  - haskell\n"
            "root: .\n"
        )

        with pytest.raises(ValueError) as exc_info:
            ProjectConfig.load(self.project_path)

        error_message = str(exc_info.value)
        assert "both 'language' and 'languages'" in error_message.lower()

    def test_neither_language_nor_languages_specified_raises_error(self):
        """Test that specifying neither 'language' nor 'languages' raises error."""
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir()
        project_yml = serena_dir / "project.yml"
        project_yml.write_text(
            "project_name: test_project\n"
            "root: .\n"
        )

        with pytest.raises(ValueError) as exc_info:
            ProjectConfig.load(self.project_path)

        error_message = str(exc_info.value)
        assert "must specify either 'language' or 'languages'" in error_message.lower()

