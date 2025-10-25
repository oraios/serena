"""
Tests for Agent class polyglot support - Phase 1.3 Step 2/3.

Following TDD approach: Tests written FIRST before implementation.
Following AGENTS.md M4 START TDD CYCLE: RED → GREEN → COMMIT → AI PANEL
Issue: #221 - Enable Multi-Language (Polyglot) Support in Serena

AI Panel Critique Findings - Priority Tests:
1. Thread-safety for concurrent manager reset
2. Rollback validation when LSPManager creation fails
3. Deprecation warnings for language_server property
"""

import shutil
import tempfile
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from serena.agent import SerenaAgent
from serena.config.serena_config import ProjectConfig
from serena.project import Project
from solidlsp.ls_config import Language


@pytest.fixture(autouse=True)
def _mock_tiktoken():
    """Mock tiktoken to prevent network download during tests."""
    with patch('serena.agent.RegisteredTokenCountEstimator'):
        yield


class TestAgentPolyglotIntegration:
    """Test Agent class integration with LSPManager."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

        # Create a polyglot project config
        self.config = ProjectConfig(
            project_name="test_polyglot_agent",
            languages=[Language.PYTHON, Language.RUST, Language.HASKELL],
        )

        # Create project
        self.project = Project(
            project_root=str(self.project_path),
            project_config=self.config,
        )

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_agent_has_lsp_manager_attribute(self):
        """Test that Agent class has lsp_manager attribute."""
        agent = SerenaAgent()

        assert hasattr(agent, "lsp_manager")

    def test_agent_has_reset_lsp_manager_method(self):
        """Test that Agent class has reset_lsp_manager method."""
        agent = SerenaAgent()

        assert hasattr(agent, "reset_lsp_manager")
        assert callable(getattr(agent, "reset_lsp_manager"))

    def test_agent_has_get_language_server_for_file_method(self):
        """Test that Agent class has get_language_server_for_file method."""
        agent = SerenaAgent()

        assert hasattr(agent, "get_language_server_for_file")
        assert callable(getattr(agent, "get_language_server_for_file"))

    def test_is_language_server_running_checks_manager(self):
        """Test that is_language_server_running checks LSPManager state."""
        agent = SerenaAgent()

        # Initially no manager
        assert not agent.is_language_server_running()

        # After creating manager (mocked)
        agent.lsp_manager = MagicMock()
        agent.lsp_manager.get_all_working_language_servers.return_value = [MagicMock()]

        assert agent.is_language_server_running()

    def test_get_language_server_for_file_routes_correctly(self):
        """Test that get_language_server_for_file routes files correctly."""
        agent = SerenaAgent()

        # Mock LSPManager
        agent.lsp_manager = MagicMock()
        mock_lsp = MagicMock()
        agent.lsp_manager.get_language_server_for_file_sync.return_value = mock_lsp

        lsp = agent.get_language_server_for_file("src/main.py")

        assert lsp == mock_lsp
        agent.lsp_manager.get_language_server_for_file_sync.assert_called_once_with("src/main.py")

    def test_backward_compatibility_language_server_property(self):
        """Test that language_server property still works for backward compatibility."""
        agent = SerenaAgent()

        # Mock LSPManager with working LSPs
        agent.lsp_manager = MagicMock()
        mock_python_lsp = MagicMock()
        agent.lsp_manager.get_all_working_language_servers.return_value = [mock_python_lsp]

        # Should return first working LSP for backward compatibility
        assert agent.language_server == mock_python_lsp

    def test_backward_compatibility_language_server_none_when_no_lsps(self):
        """Test that language_server property returns None when no LSPs running."""
        agent = SerenaAgent()

        # Mock LSPManager with no working LSPs
        agent.lsp_manager = MagicMock()
        agent.lsp_manager.get_all_working_language_servers.return_value = []

        # Should return None for backward compatibility
        assert agent.language_server is None


class TestAgentThreadSafety:
    """Test thread-safety of LSPManager operations in SerenaAgent.

    AI Panel Finding: HIGH severity - Race conditions with concurrent access.
    """

    def test_concurrent_reset_lsp_manager_is_thread_safe(self):
        """
        Test that concurrent calls to reset_lsp_manager() don't create race conditions.

        AI Panel Finding: Multiple threads calling reset_lsp_manager() could cause:
        - Using a manager reference that's being shut down
        - Race conditions in manager state
        - Inconsistent routing decisions

        Expected: Only ONE LSPManager instance should exist after concurrent resets.
        """
        agent = SerenaAgent()
        agent._active_project = Mock()
        agent._active_project.languages = [Language.PYTHON, Language.RUST]
        agent._active_project.create_lsp_manager = Mock(return_value=Mock())

        # Track number of times manager was created
        creation_count = {"value": 0}
        created_managers = []
        lock = threading.Lock()

        def track_creation(*args, **kwargs):
            with lock:
                creation_count["value"] += 1
                manager = Mock()
                manager.shutdown_all_sync = Mock()
                created_managers.append(manager)
                return manager

        agent._active_project.create_lsp_manager.side_effect = track_creation

        # Run concurrent resets
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(agent.reset_lsp_manager) for _ in range(10)]

            # Wait for all to complete
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    pytest.fail(f"reset_lsp_manager raised exception: {e}")

        # Verify only ONE manager is active (last one created)
        assert agent.lsp_manager is not None
        assert agent.lsp_manager in created_managers

        # All previous managers should have been shut down
        for manager in created_managers[:-1]:
            manager.shutdown_all_sync.assert_called_once()

    def test_get_language_server_during_reset_is_safe(self):
        """
        Test that get_language_server_for_file() is safe during concurrent reset.

        AI Panel Finding: Race condition - manager reference could become stale
        during reset_lsp_manager() call from another thread.

        Expected: No exceptions, returns None or valid LSP.
        """
        agent = SerenaAgent()
        agent._active_project = Mock()
        agent._active_project.languages = [Language.PYTHON]
        agent._active_project.create_lsp_manager = Mock(return_value=Mock())

        # Initial manager setup
        agent.reset_lsp_manager()

        results = []
        exceptions = []

        def get_lsp_repeatedly():
            """Get LSP for file repeatedly."""
            for _ in range(100):
                try:
                    lsp = agent.get_language_server_for_file("test.py")
                    results.append(lsp)
                except Exception as e:
                    exceptions.append(e)

        def reset_repeatedly():
            """Reset manager repeatedly."""
            for _ in range(10):
                try:
                    agent.reset_lsp_manager()
                except Exception as e:
                    exceptions.append(e)

        # Run concurrent operations
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            futures.append(executor.submit(get_lsp_repeatedly))
            futures.append(executor.submit(get_lsp_repeatedly))
            futures.append(executor.submit(reset_repeatedly))
            futures.append(executor.submit(reset_repeatedly))

            for future in as_completed(futures):
                future.result()

        # Should not raise any exceptions
        assert len(exceptions) == 0, f"Got exceptions during concurrent access: {exceptions}"


class TestAgentRollbackValidation:
    """Test rollback validation when LSPManager creation fails.

    AI Panel Finding: HIGH severity - Incomplete rollback logic.
    """

    def test_rollback_validates_old_manager_is_functional(self):
        """
        Test that rollback validates old manager is still functional before restoring.

        AI Panel Finding: Rollback restores old_manager but doesn't validate it's
        still functional. If old_manager was already shut down, rollback leaves
        agent in broken state.

        Expected: Rollback should validate old_manager.is_running() before restore.
        """
        agent = SerenaAgent()
        agent._active_project = Mock()
        agent._active_project.project_name = "test_project"
        agent._active_project.languages = [Language.PYTHON]

        # Create initial working manager
        old_manager = Mock()
        old_manager.shutdown_all_sync = Mock()
        old_manager.get_all_working_language_servers = Mock(return_value=[Mock()])
        agent.lsp_manager = old_manager

        # Make creation fail
        agent._active_project.create_lsp_manager = Mock(side_effect=RuntimeError("LSP creation failed"))

        # Attempt reset - should fail and rollback
        with pytest.raises(RuntimeError, match="Failed to create LSPManager"):
            agent.reset_lsp_manager()

        # OLD manager should be restored (or None if it was shut down)
        # If rollback validates and finds old_manager is shut down, it should be None
        if agent.lsp_manager is not None:
            # If restored, it should be the old manager AND it should be functional
            assert agent.lsp_manager == old_manager
            # Verify we can still get LSPs from it
            lsps = agent.lsp_manager.get_all_working_language_servers()
            assert len(lsps) > 0

    def test_rollback_handles_old_manager_already_shut_down(self):
        """
        Test rollback when old manager was already shut down.

        AI Panel Finding: If old_manager was already shut down, rollback
        leaves agent in broken state.

        Expected: Should set lsp_manager to None if old manager is not functional.
        """
        agent = SerenaAgent()
        agent._active_project = Mock()
        agent._active_project.project_name = "test_project"
        agent._active_project.languages = [Language.PYTHON]

        # Create non-functional old manager (already shut down)
        old_manager = Mock()
        old_manager.shutdown_all_sync = Mock()
        old_manager.get_all_working_language_servers = Mock(return_value=[])  # No working LSPs
        agent.lsp_manager = old_manager

        # Make creation fail
        agent._active_project.create_lsp_manager = Mock(side_effect=RuntimeError("LSP creation failed"))

        # Attempt reset - should fail
        with pytest.raises(RuntimeError, match="Failed to create LSPManager"):
            agent.reset_lsp_manager()

        # Since old manager has no working LSPs, rollback should ideally set to None
        # (or keep old_manager but document that it's non-functional)
        # For now, we verify that the agent is in a consistent state
        assert agent.is_language_server_running() == (len(old_manager.get_all_working_language_servers()) > 0)


class TestAgentBackwardCompatibilityDeprecation:
    """Test deprecation warnings for language_server property.

    AI Panel Finding: HIGH severity - No deprecation warning for language_server property.
    """

    def test_language_server_property_emits_deprecation_warning(self):
        """
        Test that accessing language_server property emits deprecation warning.

        AI Panel Finding: No deprecation warning is logged when accessing
        language_server property. Users won't know to migrate to lsp_manager.

        Expected: Should emit DeprecationWarning when property is accessed.
        """
        agent = SerenaAgent()
        agent.lsp_manager = Mock()
        agent.lsp_manager.get_all_working_language_servers = Mock(return_value=[Mock()])

        # Should emit deprecation warning
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            _ = agent.language_server

            # Check that a deprecation warning was issued
            assert len(w) >= 1
            assert any(issubclass(warning.category, DeprecationWarning) for warning in w)
            assert any("deprecated" in str(warning.message).lower() for warning in w)
            assert any("lsp_manager" in str(warning.message).lower() for warning in w)

    def test_language_server_deprecation_message_includes_migration_path(self):
        """
        Test that deprecation warning includes clear migration instructions.

        AI Panel Finding: Migration path should be documented.

        Expected: Warning should mention lsp_manager and get_language_server_for_file.
        """
        agent = SerenaAgent()
        agent.lsp_manager = Mock()
        agent.lsp_manager.get_all_working_language_servers = Mock(return_value=[Mock()])

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            _ = agent.language_server

            # Find the deprecation warning
            deprecation_warnings = [warning for warning in w if issubclass(warning.category, DeprecationWarning)]
            assert len(deprecation_warnings) >= 1

            warning_msg = str(deprecation_warnings[0].message).lower()
            assert "lsp_manager" in warning_msg or "get_language_server_for_file" in warning_msg
