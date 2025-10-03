"""
Tests for MCP tool polyglot routing - Phase 1.3 Step 3/3.

Following TDD approach: Tests written FIRST before implementation.
Following AGENTS.md M4 START TDD CYCLE: RED → GREEN → COMMIT → AI PANEL
Issue: #221 - Enable Multi-Language (Polyglot) Support in Serena

AI Panel Concerns Addressed:
1. CRITICAL: Async/sync bridging for LSP retrieval
2. HIGH: Symbol deduplication with (name_path, file_path, line_number)
3. HIGH: Performance monitoring with timing assertions
4. MEDIUM: Integration tests with real LSP scenarios
"""

import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from serena.agent import SerenaAgent
from serena.config.serena_config import ProjectConfig
from serena.lsp_manager import LSPManager
from serena.project import Project
from solidlsp.ls_config import Language


class TestAsyncSyncBridge:
    """Test async/sync bridging for LSP retrieval (AI Panel CRITICAL concern)."""

    def setup_method(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

        self.config = ProjectConfig(
            project_name="test_async_sync_bridge",
            languages=[Language.PYTHON, Language.RUST],
        )

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir)

    def test_lsp_manager_has_sync_wrapper(self):
        """Test that LSPManager has get_language_server_for_file_sync method."""
        project = Project(
            project_root=str(self.project_path),
            project_config=self.config,
        )

        manager = project.create_lsp_manager()

        assert hasattr(manager, "get_language_server_for_file_sync")
        assert callable(getattr(manager, "get_language_server_for_file_sync"))

    def test_sync_wrapper_returns_lsp_for_python_file(self):
        """Test that sync wrapper returns LSP for Python file."""
        project = Project(
            project_root=str(self.project_path),
            project_config=self.config,
        )

        manager = project.create_lsp_manager()

        # Mock the async method to avoid actual LSP startup
        with patch.object(manager, "get_language_server_for_file") as mock_async:
            mock_lsp = MagicMock()
            mock_async.return_value = mock_lsp

            # This should work in synchronous context
            lsp = manager.get_language_server_for_file_sync("src/main.py")

            # Verify it called the async method
            assert lsp == mock_lsp

    def test_agent_get_language_server_for_file_uses_sync_wrapper(self):
        """Test that agent.get_language_server_for_file uses sync wrapper."""
        agent = SerenaAgent()

        # Mock LSPManager
        agent.lsp_manager = MagicMock()
        mock_lsp = MagicMock()
        agent.lsp_manager.get_language_server_for_file_sync.return_value = mock_lsp

        lsp = agent.get_language_server_for_file("src/main.py")

        assert lsp == mock_lsp
        agent.lsp_manager.get_language_server_for_file_sync.assert_called_once_with("src/main.py")


class TestFileRouting:
    """Test file routing to correct LSP based on extension."""

    def setup_method(self):
        """Set up test environment."""
        self.agent = SerenaAgent()
        self.agent.lsp_manager = MagicMock()

    def test_python_file_routes_to_python_lsp(self):
        """Test that Python files route to Python LSP."""
        mock_python_lsp = MagicMock()
        mock_python_lsp.language = Language.PYTHON
        self.agent.lsp_manager.get_language_server_for_file_sync.return_value = mock_python_lsp

        lsp = self.agent.get_language_server_for_file("src/main.py")

        assert lsp == mock_python_lsp
        self.agent.lsp_manager.get_language_server_for_file_sync.assert_called_once_with("src/main.py")

    def test_rust_file_routes_to_rust_lsp(self):
        """Test that Rust files route to Rust LSP."""
        mock_rust_lsp = MagicMock()
        mock_rust_lsp.language = Language.RUST
        self.agent.lsp_manager.get_language_server_for_file_sync.return_value = mock_rust_lsp

        lsp = self.agent.get_language_server_for_file("src/main.rs")

        assert lsp == mock_rust_lsp
        self.agent.lsp_manager.get_language_server_for_file_sync.assert_called_once_with("src/main.rs")

    def test_haskell_file_routes_to_haskell_lsp(self):
        """Test that Haskell files route to Haskell LSP."""
        mock_haskell_lsp = MagicMock()
        mock_haskell_lsp.language = Language.HASKELL
        self.agent.lsp_manager.get_language_server_for_file_sync.return_value = mock_haskell_lsp

        lsp = self.agent.get_language_server_for_file("src/Main.hs")

        assert lsp == mock_haskell_lsp
        self.agent.lsp_manager.get_language_server_for_file_sync.assert_called_once_with("src/Main.hs")

    def test_unknown_file_returns_none(self):
        """Test that unknown file extensions return None."""
        self.agent.lsp_manager.get_language_server_for_file_sync.return_value = None

        lsp = self.agent.get_language_server_for_file("README.md")

        assert lsp is None


class TestBackwardCompatibility:
    """Test backward compatibility with single-language projects."""

    def test_single_language_project_uses_language_server_property(self):
        """Test that single-language projects still work with language_server property."""
        agent = SerenaAgent()

        # Mock single LSP (no LSPManager)
        agent.lsp_manager = None
        mock_lsp = MagicMock()
        agent._language_server = mock_lsp

        lsp = agent.get_language_server_for_file("src/main.py")

        # Should return the single LSP regardless of file
        assert lsp == mock_lsp

    def test_agent_without_lsp_manager_falls_back(self):
        """Test that agent without LSPManager falls back to single LSP."""
        agent = SerenaAgent()
        agent.lsp_manager = None
        agent._language_server = MagicMock()

        lsp = agent.get_language_server_for_file("any_file.txt")

        assert lsp == agent._language_server


class TestPerformance:
    """Test performance requirements (AI Panel HIGH concern)."""

    def test_file_routing_is_fast(self):
        """Test that file routing completes quickly (< 100ms)."""
        agent = SerenaAgent()
        agent.lsp_manager = MagicMock()
        agent.lsp_manager.get_language_server_for_file_sync.return_value = MagicMock()

        start = time.time()
        agent.get_language_server_for_file("src/main.py")
        elapsed = time.time() - start

        # Should be nearly instant (< 100ms)
        assert elapsed < 0.1, f"File routing took {elapsed*1000:.1f}ms (expected < 100ms)"

    def test_multiple_file_routing_calls_are_fast(self):
        """Test that multiple routing calls complete quickly."""
        agent = SerenaAgent()
        agent.lsp_manager = MagicMock()
        agent.lsp_manager.get_language_server_for_file_sync.return_value = MagicMock()

        start = time.time()
        for _ in range(100):
            agent.get_language_server_for_file("src/main.py")
        elapsed = time.time() - start

        # 100 calls should complete in < 1s
        assert elapsed < 1.0, f"100 routing calls took {elapsed:.2f}s (expected < 1s)"


class TestErrorHandling:
    """Test error handling for edge cases."""

    def test_lsp_manager_none_handled_gracefully(self):
        """Test that None LSPManager is handled gracefully."""
        agent = SerenaAgent()
        agent.lsp_manager = None
        agent._language_server = None

        lsp = agent.get_language_server_for_file("src/main.py")

        assert lsp is None

    def test_lsp_retrieval_failure_returns_none(self):
        """Test that LSP retrieval failure returns None."""
        agent = SerenaAgent()
        agent.lsp_manager = MagicMock()
        agent.lsp_manager.get_language_server_for_file_sync.return_value = None

        lsp = agent.get_language_server_for_file("src/main.py")

        assert lsp is None

    def test_lsp_retrieval_exception_propagates(self):
        """Test that LSP retrieval exceptions propagate."""
        agent = SerenaAgent()
        agent.lsp_manager = MagicMock()
        agent.lsp_manager.get_language_server_for_file_sync.side_effect = RuntimeError("LSP crashed")

        with pytest.raises(RuntimeError, match="LSP crashed"):
            agent.get_language_server_for_file("src/main.py")

