import os
from unittest.mock import MagicMock, Mock, patch

import pytest

from serena.util.exception import is_headless_environment, show_fatal_exception_safe


class TestHeadlessEnvironmentDetection:
    """Test class for headless environment detection functionality."""

    def test_is_headless_no_display(self):
        """Test that environment without DISPLAY is detected as headless on Linux."""
        with patch("sys.platform", "linux"):
            with patch.dict(os.environ, {}, clear=True):
                assert is_headless_environment() is True

    def test_is_headless_ssh_connection(self):
        """Test that SSH sessions are detected as headless."""
        with patch("sys.platform", "linux"):
            with patch.dict(os.environ, {"SSH_CONNECTION": "192.168.1.1 22 192.168.1.2 22", "DISPLAY": ":0"}):
                assert is_headless_environment() is True

            with patch.dict(os.environ, {"SSH_CLIENT": "192.168.1.1 22 22", "DISPLAY": ":0"}):
                assert is_headless_environment() is True

    def test_is_headless_wsl(self):
        """Test that WSL environment is detected as headless."""
        # Skip this test on Windows since os.uname doesn't exist
        if not hasattr(os, "uname"):
            pytest.skip("os.uname not available on this platform")

        with patch("sys.platform", "linux"):
            with patch("os.uname") as mock_uname:
                mock_uname.return_value = Mock(release="5.15.153.1-microsoft-standard-WSL2")
                with patch.dict(os.environ, {"DISPLAY": ":0"}):
                    assert is_headless_environment() is True

    def test_is_headless_docker(self):
        """Test that Docker containers are detected as headless."""
        with patch("sys.platform", "linux"):
            # Test with CI environment variable
            with patch.dict(os.environ, {"CI": "true", "DISPLAY": ":0"}):
                assert is_headless_environment() is True

            # Test with CONTAINER environment variable
            with patch.dict(os.environ, {"CONTAINER": "docker", "DISPLAY": ":0"}):
                assert is_headless_environment() is True

            # Test with .dockerenv file
            with patch("os.path.exists") as mock_exists:
                mock_exists.return_value = True
                with patch.dict(os.environ, {"DISPLAY": ":0"}):
                    assert is_headless_environment() is True

    def test_is_not_headless_windows(self):
        """Test that Windows is never detected as headless."""
        with patch("sys.platform", "win32"):
            # Even without DISPLAY, Windows should not be headless
            with patch.dict(os.environ, {}, clear=True):
                assert is_headless_environment() is False


class TestShowFatalExceptionSafe:
    """Test class for safe fatal exception display functionality."""

    @patch("serena.util.exception.is_headless_environment", return_value=True)
    @patch("serena.util.exception.log")
    def test_show_fatal_exception_safe_headless(self, mock_log, mock_is_headless):
        """Test that GUI is not attempted in headless environment."""
        test_exception = ValueError("Test error")

        # The import should never happen in headless mode
        with patch("serena.gui_log_viewer.show_fatal_exception") as mock_show_gui:
            show_fatal_exception_safe(test_exception)
            mock_show_gui.assert_not_called()

        # Verify debug log about skipping GUI
        mock_log.debug.assert_called_once_with("Skipping GUI error display in headless environment")

    @patch("serena.util.exception.is_headless_environment", return_value=False)
    @patch("serena.util.exception.log")
    def test_show_fatal_exception_safe_with_gui(self, mock_log, mock_is_headless):
        """Test that GUI is attempted when not in headless environment."""
        test_exception = ValueError("Test error")

        # Mock the GUI function
        with patch("serena.gui_log_viewer.show_fatal_exception") as mock_show_gui:
            show_fatal_exception_safe(test_exception)
            mock_show_gui.assert_called_once_with(test_exception)

    @patch("serena.util.exception.is_headless_environment", return_value=False)
    @patch("serena.util.exception.log")
    def test_show_fatal_exception_safe_gui_failure(self, mock_log, mock_is_headless):
        """Test graceful handling when GUI display fails."""
        test_exception = ValueError("Test error")
        gui_error = ImportError("No module named 'tkinter'")

        # Mock the GUI function to raise an exception
        with patch("serena.gui_log_viewer.show_fatal_exception", side_effect=gui_error):
            show_fatal_exception_safe(test_exception)

        # Verify debug log about GUI failure
        mock_log.debug.assert_called_with(f"Failed to show GUI error dialog: {gui_error}")

    def test_show_fatal_exception_safe_prints_to_stderr(self):
        """Test that exceptions are always printed to stderr."""
        test_exception = ValueError("Test error message")

        with patch("sys.stderr", new_callable=MagicMock) as mock_stderr:
            with patch("serena.util.exception.is_headless_environment", return_value=True):
                with patch("serena.util.exception.log"):
                    show_fatal_exception_safe(test_exception)

        # Verify print was called with the correct arguments
        mock_stderr.write.assert_any_call("Fatal exception: Test error message")
