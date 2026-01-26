"""Tests for lazy project initialization on first tool call.

This module tests the automatic project configuration generation when Claude Code
works in a directory without .murena/project.yml.
"""

import tempfile
import threading
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from murena.lazy_init import LazyProjectInitializer


class TestLazyProjectInitializer:
    """Test suite for LazyProjectInitializer class."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create temporary directory with Python file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a Python file so language detection succeeds
            Path(tmpdir, "main.py").write_text("def foo(): pass\n")
            yield tmpdir

    @pytest.fixture
    def temp_empty_dir(self):
        """Create empty temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def mock_agent(self, temp_project_dir):
        """Create a mock MurenaAgent."""
        agent = Mock()
        agent.get_active_project = Mock(return_value=None)
        agent._activate_project = Mock()
        return agent

    def test_initialization_creates_project_yml(self, temp_project_dir, mock_agent):
        """Test that lazy init creates .murena/project.yml on first call."""
        initializer = LazyProjectInitializer(mock_agent)
        initializer.set_project_root(temp_project_dir)

        # Verify file doesn't exist yet
        project_yml = Path(temp_project_dir) / ".murena" / "project.yml"
        assert not project_yml.exists()

        # Trigger initialization
        msg = initializer.ensure_initialized()

        # Verify file was created
        assert project_yml.exists()
        assert msg is not None
        assert "Auto-initialized" in msg
        assert "Python" in msg or "python" in msg.lower()

    def test_initialization_only_happens_once(self, temp_project_dir, mock_agent):
        """Test that initialization only happens once (idempotent)."""
        initializer = LazyProjectInitializer(mock_agent)
        initializer.set_project_root(temp_project_dir)

        # First call
        initializer.ensure_initialized()
        call_count_1 = mock_agent._activate_project.call_count

        # Second call
        initializer.ensure_initialized()
        call_count_2 = mock_agent._activate_project.call_count

        # _activate_project should only be called once
        assert call_count_1 == 1
        assert call_count_2 == 1  # No additional calls

    def test_initialization_skipped_if_project_active(self, temp_project_dir, mock_agent):
        """Test that initialization is skipped if project is already active."""
        mock_project = Mock()
        mock_agent.get_active_project = Mock(return_value=mock_project)

        initializer = LazyProjectInitializer(mock_agent)
        initializer.set_project_root(temp_project_dir)

        msg = initializer.ensure_initialized()

        # Should return None without triggering initialization
        assert msg is None
        mock_agent._activate_project.assert_not_called()

    def test_handles_empty_directory(self, temp_empty_dir, mock_agent):
        """Test graceful handling when no source files found."""
        initializer = LazyProjectInitializer(mock_agent)
        initializer.set_project_root(temp_empty_dir)

        msg = initializer.ensure_initialized()

        # Should return helpful error message
        assert msg is not None
        assert "Could not auto-initialize" in msg
        assert "No source files found" in msg or "no source files" in msg.lower()

    def test_thread_safety(self, temp_project_dir, mock_agent):
        """Test that concurrent calls don't cause race conditions."""
        initializer = LazyProjectInitializer(mock_agent)
        initializer.set_project_root(temp_project_dir)

        messages = []
        errors = []

        def call_ensure_initialized():
            try:
                msg = initializer.ensure_initialized()
                messages.append(msg)
            except Exception as e:
                errors.append(e)

        # Launch 5 concurrent threads
        threads = [threading.Thread(target=call_ensure_initialized) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify no errors occurred
        assert len(errors) == 0

        # Verify _activate_project was called exactly once
        assert mock_agent._activate_project.call_count == 1

        # Verify exactly one thread got the initialization message (the one that did the work)
        # The others get None since initialization was already done
        messages_with_content = [m for m in messages if m is not None]
        assert len(messages_with_content) == 1
        assert "Auto-initialized" in messages_with_content[0]

        # Verify all other messages are None
        assert len([m for m in messages if m is None]) == 4

    def test_detects_multiple_languages(self, temp_project_dir, mock_agent):
        """Test that multiple languages are detected in non-interactive mode."""
        # Add files for multiple languages
        Path(temp_project_dir, "script.ts").write_text("function foo() {}\n")
        Path(temp_project_dir, "main.go").write_text("package main\n")

        initializer = LazyProjectInitializer(mock_agent)
        initializer.set_project_root(temp_project_dir)

        msg = initializer.ensure_initialized()

        # Verify initialization succeeded
        assert msg is not None
        assert "Auto-initialized" in msg

        # Verify project.yml was created
        project_yml = Path(temp_project_dir) / ".murena" / "project.yml"
        assert project_yml.exists()

        # Verify multiple languages are in the config
        content = project_yml.read_text()
        assert "languages:" in content.lower()

    def test_format_activation_message(self, temp_project_dir, mock_agent):
        """Test that activation message is properly formatted."""
        initializer = LazyProjectInitializer(mock_agent)
        initializer.set_project_root(temp_project_dir)

        msg = initializer.ensure_initialized()

        # Verify message format
        assert msg is not None
        assert "✓" in msg or "Auto-initialized" in msg
        assert temp_project_dir in msg
        assert "project.yml" in msg

    def test_error_message_for_permission_denied(self, mock_agent):
        """Test error message when permission is denied."""
        initializer = LazyProjectInitializer(mock_agent)
        initializer.set_project_root("/tmp/test_project")

        # Mock autogenerate to raise PermissionError
        with patch("murena.config.murena_config.ProjectConfig.autogenerate") as mock_autogen:
            mock_autogen.side_effect = PermissionError("Permission denied")
            msg = initializer.ensure_initialized()

            assert msg is not None
            assert "permission" in msg.lower()

    def test_initialization_with_missing_project_root(self, mock_agent):
        """Test that initialization is skipped if project root is not set."""
        initializer = LazyProjectInitializer(mock_agent)
        # Don't call set_project_root

        msg = initializer.ensure_initialized()

        # Should return None without error
        assert msg is None
        mock_agent._activate_project.assert_not_called()

    def test_lazy_init_configuration(self):
        """Test LazyInitConfig dataclass."""
        from murena.config.murena_config import LazyInitConfig

        config = LazyInitConfig()

        # Verify defaults
        assert config.enabled is True
        assert config.max_languages_to_enable == 3
        assert config.language_detection_timeout_seconds == 30

    def test_lazy_init_in_murena_config(self):
        """Test that MurenaConfig includes lazy_init field."""
        from murena.config.murena_config import MurenaConfig

        config = MurenaConfig()

        # Verify lazy_init field exists and has correct type
        assert hasattr(config, "lazy_init")
        assert config.lazy_init.enabled is True
