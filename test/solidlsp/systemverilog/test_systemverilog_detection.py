"""
Tests for verible-verilog-ls detection logic.

These tests describe the expected behavior of SystemVerilogLanguageServer.DependencyProvider._get_or_install_core_dependency():

1. System PATH should be checked FIRST (prefers user-installed verible)
2. Runtime download should be fallback when not in PATH
3. Version information should be logged when available
4. Version check failures should be handled gracefully
5. Helpful error messages when verible is not available on unsupported platforms

WHY these tests matter:
- Users install verible via conda, Homebrew, system packages, or GitHub releases
- Detection failing means Serena is unusable for SystemVerilog, even when verible is correctly installed
- Without these tests, the detection logic can silently break for users with system installations
- Version logging helps debug compatibility issues
"""

import os
import subprocess
import sys
import tempfile
from unittest.mock import MagicMock, Mock, patch

import pytest

# Platform detection for skipping platform-specific tests
IS_WINDOWS = sys.platform == "win32"
IS_UNIX = sys.platform != "win32"


class TestVeribleVerilogLsDetection:
    """Unit tests for verible-verilog-ls binary detection logic."""

    @pytest.mark.systemverilog
    def test_detect_from_path_returns_system_verible(self):
        """
        GIVEN verible-verilog-ls is in system PATH
        WHEN _get_or_install_core_dependency is called
        THEN it returns the system path without downloading

        WHY: Users with system-installed verible (via conda, Homebrew, apt)
        should use that version instead of downloading. This is faster and
        respects user's environment management.
        """
        from solidlsp.language_servers.systemverilog_server import SystemVerilogLanguageServer
        from solidlsp.settings import SolidLSPSettings

        with tempfile.TemporaryDirectory() as temp_dir:
            custom_settings = SolidLSPSettings.CustomLSSettings({})
            provider = SystemVerilogLanguageServer.DependencyProvider(custom_settings, temp_dir)

            with patch("shutil.which") as mock_which:
                mock_which.return_value = "/usr/local/bin/verible-verilog-ls"
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        returncode=0,
                        stdout="Verible v0.0-4051-g9fdb4057 (2024-01-01)\nCommit: 9fdb4057",
                        stderr="",
                    )
                    result = provider._get_or_install_core_dependency()

        assert result == "/usr/local/bin/verible-verilog-ls"
        mock_which.assert_called_once_with("verible-verilog-ls")
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["/usr/local/bin/verible-verilog-ls", "--version"]

    @pytest.mark.systemverilog
    def test_detect_from_path_logs_version(self):
        """
        GIVEN verible-verilog-ls is in PATH with version output
        WHEN detected
        THEN version info is logged

        WHY: Version information helps debug compatibility issues.
        Users and developers need to know which verible version is being used.
        """
        from solidlsp.language_servers.systemverilog_server import SystemVerilogLanguageServer
        from solidlsp.settings import SolidLSPSettings

        with tempfile.TemporaryDirectory() as temp_dir:
            custom_settings = SolidLSPSettings.CustomLSSettings({})
            provider = SystemVerilogLanguageServer.DependencyProvider(custom_settings, temp_dir)

            with patch("shutil.which", return_value="/usr/bin/verible-verilog-ls"):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout="Verible v0.0-4051-g9fdb4057", stderr="")
                    with patch("solidlsp.language_servers.systemverilog_server.log") as mock_log:
                        result = provider._get_or_install_core_dependency()

            # Verify version check was called
            assert mock_run.call_args[0][0] == ["/usr/bin/verible-verilog-ls", "--version"]
            # Verify version was logged
            assert mock_log.info.called
            log_message = mock_log.info.call_args[0][0]
            assert "Verible v0.0-4051" in log_message
            assert result == "/usr/bin/verible-verilog-ls"

    @pytest.mark.systemverilog
    def test_detect_from_path_handles_version_failure_gracefully(self):
        """
        GIVEN verible-verilog-ls is in PATH but --version fails (returncode=1)
        WHEN detected
        THEN it still returns the system path (graceful degradation)

        WHY: Some verible builds might not support --version or have different flags.
        Detection should not fail just because version check fails - the binary
        might still work fine for LSP operations.
        """
        from solidlsp.language_servers.systemverilog_server import SystemVerilogLanguageServer
        from solidlsp.settings import SolidLSPSettings

        with tempfile.TemporaryDirectory() as temp_dir:
            custom_settings = SolidLSPSettings.CustomLSSettings({})
            provider = SystemVerilogLanguageServer.DependencyProvider(custom_settings, temp_dir)

            with patch("shutil.which", return_value="/custom/bin/verible-verilog-ls"):
                with patch("subprocess.run") as mock_run:
                    # Version check fails
                    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Unknown option: --version")
                    result = provider._get_or_install_core_dependency()

        # Should still return the path despite version check failure
        assert result == "/custom/bin/verible-verilog-ls"

    @pytest.mark.systemverilog
    def test_detect_from_path_handles_version_timeout_gracefully(self):
        """
        GIVEN verible-verilog-ls is in PATH but --version times out
        WHEN detected
        THEN it still returns the system path (graceful degradation)

        WHY: Version check has a timeout to avoid hanging. If it times out,
        we should still use the detected binary.
        """
        from solidlsp.language_servers.systemverilog_server import SystemVerilogLanguageServer
        from solidlsp.settings import SolidLSPSettings

        with tempfile.TemporaryDirectory() as temp_dir:
            custom_settings = SolidLSPSettings.CustomLSSettings({})
            provider = SystemVerilogLanguageServer.DependencyProvider(custom_settings, temp_dir)

            with patch("shutil.which", return_value="/opt/verible/bin/verible-verilog-ls"):
                with patch("subprocess.run") as mock_run:
                    # Version check times out
                    mock_run.side_effect = subprocess.TimeoutExpired(cmd=["verible-verilog-ls", "--version"], timeout=5)
                    result = provider._get_or_install_core_dependency()

        # Should still return the path despite timeout
        assert result == "/opt/verible/bin/verible-verilog-ls"

    @pytest.mark.systemverilog
    def test_error_message_when_not_found_anywhere(self):
        """
        GIVEN verible is NOT in PATH AND platform is unsupported
        WHEN _get_or_install_core_dependency is called
        THEN raises FileNotFoundError with helpful installation instructions

        WHY: Users need clear guidance on how to install verible when it's missing.
        Error message should mention conda, Homebrew, and GitHub releases.
        """
        from solidlsp.language_servers.systemverilog_server import SystemVerilogLanguageServer
        from solidlsp.settings import SolidLSPSettings

        with tempfile.TemporaryDirectory() as temp_dir:
            custom_settings = SolidLSPSettings.CustomLSSettings({})
            provider = SystemVerilogLanguageServer.DependencyProvider(custom_settings, temp_dir)

            with patch("shutil.which", return_value=None):
                # Mock RuntimeDependencyCollection to raise RuntimeError for unsupported platform
                with patch("solidlsp.language_servers.systemverilog_server.RuntimeDependencyCollection") as mock_deps_class:
                    mock_deps = Mock()
                    mock_deps.get_single_dep_for_current_platform.side_effect = RuntimeError("Unsupported platform")
                    mock_deps_class.return_value = mock_deps

                    with pytest.raises(FileNotFoundError) as exc_info:
                        provider._get_or_install_core_dependency()

        error_message = str(exc_info.value)
        # Error should mention installation methods
        assert "conda" in error_message.lower()
        assert "Homebrew" in error_message or "brew" in error_message.lower()
        assert "GitHub" in error_message or "github.com" in error_message.lower()
        assert "verible" in error_message.lower()

    @pytest.mark.systemverilog
    def test_downloads_when_not_in_path(self):
        """
        GIVEN verible is NOT in PATH AND platform IS supported AND binary exists after download
        WHEN _get_or_install_core_dependency is called
        THEN returns the downloaded executable path

        WHY: When verible is not installed system-wide and platform is supported,
        Serena should auto-download it. This enables zero-setup experience.
        """
        from solidlsp.language_servers.systemverilog_server import SystemVerilogLanguageServer
        from solidlsp.settings import SolidLSPSettings

        with tempfile.TemporaryDirectory() as temp_dir:
            custom_settings = SolidLSPSettings.CustomLSSettings({})
            provider = SystemVerilogLanguageServer.DependencyProvider(custom_settings, temp_dir)

            expected_path = os.path.join(temp_dir, "verible-ls", "verible-v0.0-4051-g9fdb4057", "bin", "verible-verilog-ls")

            with patch("shutil.which", return_value=None):
                with patch("solidlsp.language_servers.systemverilog_server.RuntimeDependencyCollection") as mock_deps_class:
                    # Create mock dependency and collection
                    mock_dep = Mock()
                    mock_dep.url = "https://github.com/chipsalliance/verible/releases/download/v0.0-4051/verible.tar.gz"

                    mock_deps = Mock()
                    mock_deps.get_single_dep_for_current_platform.return_value = mock_dep
                    mock_deps.binary_path.return_value = expected_path
                    mock_deps.install.return_value = expected_path

                    mock_deps_class.return_value = mock_deps

                    with patch("os.path.exists") as mock_exists:
                        # First call (line 121 check) returns False, second call (line 125 check) returns True
                        mock_exists.side_effect = [False, True]

                        with patch("os.chmod"):
                            result = provider._get_or_install_core_dependency()

            assert result == expected_path
            mock_deps.install.assert_called_once()

    @pytest.mark.systemverilog
    def test_detection_prefers_path_over_download(self):
        """
        GIVEN verible is in PATH AND download would also work
        WHEN _get_or_install_core_dependency is called
        THEN PATH version is used (download never attempted)

        WHY: System-installed verible should always take precedence.
        This respects user's environment and avoids unnecessary downloads.
        """
        from solidlsp.language_servers.systemverilog_server import SystemVerilogLanguageServer
        from solidlsp.settings import SolidLSPSettings

        with tempfile.TemporaryDirectory() as temp_dir:
            custom_settings = SolidLSPSettings.CustomLSSettings({})
            provider = SystemVerilogLanguageServer.DependencyProvider(custom_settings, temp_dir)

            with patch("shutil.which", return_value="/usr/bin/verible-verilog-ls"):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout="Verible v0.0-4051", stderr="")

                    with patch("solidlsp.language_servers.systemverilog_server.RuntimeDependencyCollection") as mock_deps_class:
                        result = provider._get_or_install_core_dependency()

                        # RuntimeDependencyCollection should never be instantiated
                        mock_deps_class.assert_not_called()

            assert result == "/usr/bin/verible-verilog-ls"

    @pytest.mark.systemverilog
    def test_download_fails_if_binary_not_found_after_install(self):
        """
        GIVEN verible is NOT in PATH AND platform IS supported
        WHEN download completes BUT binary still doesn't exist at expected path
        THEN raises FileNotFoundError

        WHY: If download/extraction fails silently, we should catch it and report clearly.
        """
        from solidlsp.language_servers.systemverilog_server import SystemVerilogLanguageServer
        from solidlsp.settings import SolidLSPSettings

        with tempfile.TemporaryDirectory() as temp_dir:
            custom_settings = SolidLSPSettings.CustomLSSettings({})
            provider = SystemVerilogLanguageServer.DependencyProvider(custom_settings, temp_dir)

            expected_path = os.path.join(temp_dir, "verible-ls", "verible-v0.0-4051-g9fdb4057", "bin", "verible-verilog-ls")

            with patch("shutil.which", return_value=None):
                with patch("solidlsp.language_servers.systemverilog_server.RuntimeDependencyCollection") as mock_deps_class:
                    mock_dep = Mock()
                    mock_deps = Mock()
                    mock_deps.get_single_dep_for_current_platform.return_value = mock_dep
                    mock_deps.binary_path.return_value = expected_path
                    mock_deps.install.return_value = expected_path
                    mock_deps_class.return_value = mock_deps

                    # Binary never appears after install
                    with patch("os.path.exists", return_value=False):
                        with pytest.raises(FileNotFoundError) as exc_info:
                            provider._get_or_install_core_dependency()

            error_message = str(exc_info.value)
            assert "verible-verilog-ls not found" in error_message
            assert expected_path in error_message

    @pytest.mark.systemverilog
    def test_uses_already_downloaded_binary_without_reinstalling(self):
        """
        GIVEN verible is NOT in PATH AND platform IS supported
        AND binary already exists at download location
        WHEN _get_or_install_core_dependency is called
        THEN returns existing path without downloading again

        WHY: Avoid redundant downloads if verible was already downloaded in previous session.
        This speeds up subsequent runs.
        """
        from solidlsp.language_servers.systemverilog_server import SystemVerilogLanguageServer
        from solidlsp.settings import SolidLSPSettings

        with tempfile.TemporaryDirectory() as temp_dir:
            custom_settings = SolidLSPSettings.CustomLSSettings({})
            provider = SystemVerilogLanguageServer.DependencyProvider(custom_settings, temp_dir)

            expected_path = os.path.join(temp_dir, "verible-ls", "verible-v0.0-4051-g9fdb4057", "bin", "verible-verilog-ls")

            with patch("shutil.which", return_value=None):
                with patch("solidlsp.language_servers.systemverilog_server.RuntimeDependencyCollection") as mock_deps_class:
                    mock_dep = Mock()
                    mock_deps = Mock()
                    mock_deps.get_single_dep_for_current_platform.return_value = mock_dep
                    mock_deps.binary_path.return_value = expected_path
                    mock_deps_class.return_value = mock_deps

                    # Binary already exists
                    with patch("os.path.exists", return_value=True):
                        with patch("os.chmod"):
                            result = provider._get_or_install_core_dependency()

            # Should NOT call install since binary already exists
            mock_deps.install.assert_not_called()
            assert result == expected_path


class TestVeribleVerilogLsDetectionIntegration:
    """
    Integration tests that verify detection works on the current system.
    These tests are skipped if verible-verilog-ls is not installed.
    """

    @pytest.mark.systemverilog
    def test_integration_finds_installed_verible(self):
        """
        GIVEN verible-verilog-ls is installed on this system (via any method)
        WHEN _get_or_install_core_dependency is called
        THEN it returns a valid executable path

        This test verifies the detection logic works end-to-end on the current system.
        """
        import shutil

        from solidlsp.language_servers.systemverilog_server import SystemVerilogLanguageServer
        from solidlsp.settings import SolidLSPSettings

        # Skip if verible-verilog-ls is not installed
        if not shutil.which("verible-verilog-ls"):
            pytest.skip("verible-verilog-ls not installed on this system")

        with tempfile.TemporaryDirectory() as temp_dir:
            custom_settings = SolidLSPSettings.CustomLSSettings({})
            provider = SystemVerilogLanguageServer.DependencyProvider(custom_settings, temp_dir)

            result = provider._get_or_install_core_dependency()

        assert result is not None
        assert os.path.isfile(result)
        assert os.access(result, os.X_OK)
