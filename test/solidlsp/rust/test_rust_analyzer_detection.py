"""
Tests for rust-analyzer detection logic.

These tests describe the expected behavior of RustAnalyzer._ensure_rust_analyzer_installed():

1. Detection should check multiple locations in priority order
2. shutil.which (PATH) should be checked first
3. Common installation locations (Homebrew, cargo, Scoop) should be checked before rustup
4. Rustup should be the fallback, not the only option
5. Error messages should list all searched locations
6. Windows-specific paths should be checked on Windows

WHY these tests matter:
- Users install rust-analyzer via Homebrew, cargo, Scoop, or system packages - not just rustup
- macOS Homebrew installs to /opt/homebrew/bin (Apple Silicon) or /usr/local/bin (Intel)
- Windows users install via Scoop, Chocolatey, or cargo
- Detection failing means Serena is unusable for Rust, even when rust-analyzer is correctly installed
- Without these tests, the detection logic can silently break for non-rustup users
"""

import os
import pathlib
import sys
from unittest.mock import MagicMock, patch

import pytest

# Platform detection for skipping platform-specific tests
IS_WINDOWS = sys.platform == "win32"
IS_UNIX = sys.platform != "win32"


class TestRustAnalyzerDetection:
    """Unit tests for rust-analyzer binary detection logic."""

    @pytest.mark.rust
    def test_detect_from_shutil_which_when_in_path(self):
        """
        GIVEN rust-analyzer is in system PATH
        WHEN _ensure_rust_analyzer_installed is called
        THEN it should return the path from shutil.which

        WHY: Users who install via `brew install rust-analyzer` or system package managers
        will have rust-analyzer in PATH. This should be detected first.
        """
        from solidlsp.language_servers.rust_analyzer import RustAnalyzer

        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/local/bin/rust-analyzer"
            with patch("os.path.isfile", return_value=True):
                with patch("os.access", return_value=True):
                    result = RustAnalyzer._ensure_rust_analyzer_installed()

        assert result == "/usr/local/bin/rust-analyzer"
        mock_which.assert_called_with("rust-analyzer")

    @pytest.mark.rust
    @pytest.mark.skipif(IS_WINDOWS, reason="Homebrew paths only apply to macOS/Linux")
    def test_detect_from_homebrew_apple_silicon_path(self):
        """
        GIVEN rust-analyzer is installed via Homebrew on Apple Silicon Mac
        AND it is NOT in PATH (shutil.which returns None)
        WHEN _ensure_rust_analyzer_installed is called
        THEN it should find /opt/homebrew/bin/rust-analyzer

        WHY: Apple Silicon Macs use /opt/homebrew/bin for Homebrew.
        This path should be checked even if it's not in PATH.
        """
        from solidlsp.language_servers.rust_analyzer import RustAnalyzer

        def mock_isfile(path):
            return path == "/opt/homebrew/bin/rust-analyzer"

        def mock_access(path, mode):
            return path == "/opt/homebrew/bin/rust-analyzer"

        with patch("shutil.which", return_value=None):
            with patch("os.path.isfile", side_effect=mock_isfile):
                with patch("os.access", side_effect=mock_access):
                    result = RustAnalyzer._ensure_rust_analyzer_installed()

        assert result == "/opt/homebrew/bin/rust-analyzer"

    @pytest.mark.rust
    @pytest.mark.skipif(IS_WINDOWS, reason="Homebrew paths only apply to macOS/Linux")
    def test_detect_from_homebrew_intel_path(self):
        """
        GIVEN rust-analyzer is installed via Homebrew on Intel Mac
        AND it is NOT in PATH
        WHEN _ensure_rust_analyzer_installed is called
        THEN it should find /usr/local/bin/rust-analyzer

        WHY: Intel Macs use /usr/local/bin for Homebrew.
        Linux systems may also install to this location.
        """
        from solidlsp.language_servers.rust_analyzer import RustAnalyzer

        def mock_isfile(path):
            return path == "/usr/local/bin/rust-analyzer"

        def mock_access(path, mode):
            return path == "/usr/local/bin/rust-analyzer"

        with patch("shutil.which", return_value=None):
            with patch("os.path.isfile", side_effect=mock_isfile):
                with patch("os.access", side_effect=mock_access):
                    result = RustAnalyzer._ensure_rust_analyzer_installed()

        assert result == "/usr/local/bin/rust-analyzer"

    @pytest.mark.rust
    @pytest.mark.skipif(IS_WINDOWS, reason="Unix cargo path - Windows has separate test")
    def test_detect_from_cargo_install_path(self):
        """
        GIVEN rust-analyzer is installed via `cargo install rust-analyzer`
        AND it is NOT in PATH or Homebrew locations
        WHEN _ensure_rust_analyzer_installed is called
        THEN it should find ~/.cargo/bin/rust-analyzer

        WHY: `cargo install rust-analyzer` is a common installation method.
        The binary lands in ~/.cargo/bin which may not be in PATH.
        """
        from solidlsp.language_servers.rust_analyzer import RustAnalyzer

        cargo_path = os.path.expanduser("~/.cargo/bin/rust-analyzer")

        def mock_isfile(path):
            return path == cargo_path

        def mock_access(path, mode):
            return path == cargo_path

        with patch("shutil.which", return_value=None):
            with patch("os.path.isfile", side_effect=mock_isfile):
                with patch("os.access", side_effect=mock_access):
                    result = RustAnalyzer._ensure_rust_analyzer_installed()

        assert result == cargo_path

    @pytest.mark.rust
    def test_falls_back_to_rustup_when_not_in_common_locations(self):
        """
        GIVEN rust-analyzer is NOT in PATH or common locations
        AND rustup has rust-analyzer installed
        WHEN _ensure_rust_analyzer_installed is called
        THEN it should fall back to rustup which rust-analyzer

        WHY: Rustup users should still work. Rustup is the fallback, not the only option.
        """
        from solidlsp.language_servers.rust_analyzer import RustAnalyzer

        with patch("shutil.which", return_value=None):
            with patch("os.path.isfile", return_value=False):
                with patch.object(
                    RustAnalyzer,
                    "_get_rust_analyzer_via_rustup",
                    return_value="/home/user/.rustup/toolchains/stable-x86_64-unknown-linux-gnu/bin/rust-analyzer",
                ):
                    result = RustAnalyzer._ensure_rust_analyzer_installed()

        assert "rustup" in result or ".rustup" in result

    @pytest.mark.rust
    @pytest.mark.skipif(IS_WINDOWS, reason="Unix error messages - Windows has separate test")
    def test_error_message_lists_searched_locations_when_not_found(self):
        """
        GIVEN rust-analyzer is NOT installed anywhere
        AND rustup is NOT installed
        WHEN _ensure_rust_analyzer_installed is called
        THEN it should raise RuntimeError with helpful message listing searched locations

        WHY: Users need to know WHERE Serena looked so they can fix their installation.
        The old error "Neither rust-analyzer nor rustup is installed" was unhelpful.
        """
        from solidlsp.language_servers.rust_analyzer import RustAnalyzer

        with patch("shutil.which", return_value=None):
            with patch("os.path.isfile", return_value=False):
                with patch.object(RustAnalyzer, "_get_rust_analyzer_via_rustup", return_value=None):
                    with patch.object(RustAnalyzer, "_get_rustup_version", return_value=None):
                        with pytest.raises(RuntimeError) as exc_info:
                            RustAnalyzer._ensure_rust_analyzer_installed()

        error_message = str(exc_info.value)
        # Error should list the locations that were searched (Unix paths)
        assert "/opt/homebrew/bin/rust-analyzer" in error_message or "Homebrew" in error_message
        assert "cargo" in error_message.lower() or ".cargo/bin" in error_message
        # Error should suggest installation methods
        assert "rustup" in error_message.lower() or "Rustup" in error_message

    @pytest.mark.rust
    def test_detection_priority_prefers_path_over_hardcoded_locations(self):
        """
        GIVEN rust-analyzer exists in BOTH PATH and a hardcoded location
        WHEN _ensure_rust_analyzer_installed is called
        THEN it should return the PATH version (shutil.which result)

        WHY: If user has rust-analyzer in PATH, that's their preferred version.
        We shouldn't override their PATH with hardcoded locations.
        """
        from solidlsp.language_servers.rust_analyzer import RustAnalyzer

        # Both PATH and Homebrew have rust-analyzer
        with patch("shutil.which", return_value="/custom/path/rust-analyzer"):
            with patch("os.path.isfile", return_value=True):
                with patch("os.access", return_value=True):
                    result = RustAnalyzer._ensure_rust_analyzer_installed()

        # Should use the PATH version, not hardcoded
        assert result == "/custom/path/rust-analyzer"

    @pytest.mark.rust
    @pytest.mark.skipif(IS_WINDOWS, reason="Uses Unix paths - Windows has different behavior")
    def test_skips_nonexecutable_files(self):
        """
        GIVEN a file exists at a detection path but is NOT executable
        WHEN _ensure_rust_analyzer_installed is called
        THEN it should skip that path and continue checking others

        WHY: A non-executable file (e.g., broken symlink, wrong permissions)
        should not be returned as a valid rust-analyzer path.
        """
        from solidlsp.language_servers.rust_analyzer import RustAnalyzer

        def mock_isfile(path):
            # File exists at Homebrew location but not executable
            return path == "/opt/homebrew/bin/rust-analyzer"

        def mock_access(path, mode):
            # Homebrew location exists but not executable
            if path == "/opt/homebrew/bin/rust-analyzer":
                return False
            # Cargo location is executable
            if path == os.path.expanduser("~/.cargo/bin/rust-analyzer"):
                return True
            return False

        def mock_isfile_for_cargo(path):
            return path in ["/opt/homebrew/bin/rust-analyzer", os.path.expanduser("~/.cargo/bin/rust-analyzer")]

        with patch("shutil.which", return_value=None):
            with patch("os.path.isfile", side_effect=mock_isfile_for_cargo):
                with patch("os.access", side_effect=mock_access):
                    result = RustAnalyzer._ensure_rust_analyzer_installed()

        # Should skip non-executable Homebrew and use cargo
        assert result == os.path.expanduser("~/.cargo/bin/rust-analyzer")

    @pytest.mark.rust
    def test_detect_from_scoop_shims_path_on_windows(self):
        """
        GIVEN rust-analyzer is installed via Scoop on Windows
        AND it is NOT in PATH
        WHEN _ensure_rust_analyzer_installed is called
        THEN it should find ~/scoop/shims/rust-analyzer.exe

        WHY: Scoop is a popular package manager for Windows.
        The binary lands in ~/scoop/shims which may not be in PATH.
        """
        from solidlsp.language_servers.rust_analyzer import RustAnalyzer

        home = pathlib.Path.home()
        scoop_path = str(home / "scoop" / "shims" / "rust-analyzer.exe")

        def mock_isfile(path):
            return path == scoop_path

        def mock_access(path, mode):
            return path == scoop_path

        with patch("platform.system", return_value="Windows"):
            with patch("shutil.which", return_value=None):
                with patch("os.path.isfile", side_effect=mock_isfile):
                    with patch("os.access", side_effect=mock_access):
                        result = RustAnalyzer._ensure_rust_analyzer_installed()

        assert result == scoop_path

    @pytest.mark.rust
    def test_detect_from_cargo_path_on_windows(self):
        """
        GIVEN rust-analyzer is installed via cargo on Windows
        AND it is NOT in PATH or Scoop locations
        WHEN _ensure_rust_analyzer_installed is called
        THEN it should find ~/.cargo/bin/rust-analyzer.exe

        WHY: `cargo install rust-analyzer` works on Windows.
        The binary has .exe extension and lands in ~/.cargo/bin.
        """
        from solidlsp.language_servers.rust_analyzer import RustAnalyzer

        home = pathlib.Path.home()
        cargo_path = str(home / ".cargo" / "bin" / "rust-analyzer.exe")

        def mock_isfile(path):
            return path == cargo_path

        def mock_access(path, mode):
            return path == cargo_path

        with patch("platform.system", return_value="Windows"):
            with patch("shutil.which", return_value=None):
                with patch("os.path.isfile", side_effect=mock_isfile):
                    with patch("os.access", side_effect=mock_access):
                        result = RustAnalyzer._ensure_rust_analyzer_installed()

        assert result == cargo_path

    @pytest.mark.rust
    def test_windows_error_message_suggests_windows_package_managers(self):
        """
        GIVEN rust-analyzer is NOT installed anywhere on Windows
        AND rustup is NOT installed
        WHEN _ensure_rust_analyzer_installed is called
        THEN it should raise RuntimeError with Windows-specific installation suggestions

        WHY: Windows users need Windows-specific package manager suggestions
        (Scoop, Chocolatey) instead of Homebrew/apt.
        """
        from solidlsp.language_servers.rust_analyzer import RustAnalyzer

        with patch("platform.system", return_value="Windows"):
            with patch("shutil.which", return_value=None):
                with patch("os.path.isfile", return_value=False):
                    with patch.object(RustAnalyzer, "_get_rust_analyzer_via_rustup", return_value=None):
                        with patch.object(RustAnalyzer, "_get_rustup_version", return_value=None):
                            with pytest.raises(RuntimeError) as exc_info:
                                RustAnalyzer._ensure_rust_analyzer_installed()

        error_message = str(exc_info.value)
        # Error should suggest Windows-specific package managers
        assert "Scoop" in error_message or "scoop" in error_message
        assert "Chocolatey" in error_message or "choco" in error_message
        # Should NOT suggest Homebrew on Windows
        assert "Homebrew" not in error_message and "brew" not in error_message

    @pytest.mark.rust
    def test_auto_install_via_rustup_when_not_found(self):
        """
        GIVEN rust-analyzer is NOT installed anywhere
        AND rustup IS installed
        WHEN _ensure_rust_analyzer_installed is called
        AND rustup component add succeeds
        THEN it should return the rustup-installed path

        WHY: Serena should auto-install rust-analyzer via rustup when possible.
        This matches the original behavior and enables CI to work without pre-installing.
        """
        from solidlsp.language_servers.rust_analyzer import RustAnalyzer

        with patch("shutil.which", return_value=None):
            with patch("os.path.isfile", return_value=False):
                with patch.object(RustAnalyzer, "_get_rust_analyzer_via_rustup") as mock_rustup_path:
                    # First call returns None (not installed), second returns path (after install)
                    mock_rustup_path.side_effect = [None, "/home/user/.rustup/toolchains/stable/bin/rust-analyzer"]
                    with patch.object(RustAnalyzer, "_get_rustup_version", return_value="1.70.0"):
                        with patch("subprocess.run") as mock_run:
                            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                            result = RustAnalyzer._ensure_rust_analyzer_installed()

        assert result == "/home/user/.rustup/toolchains/stable/bin/rust-analyzer"
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["rustup", "component", "add", "rust-analyzer"]

    @pytest.mark.rust
    def test_auto_install_failure_raises_error_with_stderr(self):
        """
        GIVEN rust-analyzer is NOT installed anywhere
        AND rustup IS installed
        WHEN _ensure_rust_analyzer_installed is called
        AND rustup component add FAILS
        THEN it should raise RuntimeError containing the stderr output

        WHY: When auto-install fails, users need to see the actual error from rustup
        to diagnose the problem (e.g., network issues, permission errors).
        Silently falling through to a generic error loses critical diagnostic info.
        """
        from solidlsp.language_servers.rust_analyzer import RustAnalyzer

        with patch("shutil.which", return_value=None):
            with patch("os.path.isfile", return_value=False):
                with patch.object(RustAnalyzer, "_get_rust_analyzer_via_rustup", return_value=None):
                    with patch.object(RustAnalyzer, "_get_rustup_version", return_value="1.70.0"):
                        with patch("subprocess.run") as mock_run:
                            mock_run.return_value = MagicMock(
                                returncode=1, stdout="", stderr="error: component 'rust-analyzer' is not available"
                            )
                            with pytest.raises(RuntimeError) as exc_info:
                                RustAnalyzer._ensure_rust_analyzer_installed()

        error_message = str(exc_info.value)
        # Error MUST contain the stderr from rustup so users can diagnose
        assert "component 'rust-analyzer' is not available" in error_message

    @pytest.mark.rust
    def test_auto_install_success_but_binary_not_found_raises_error(self):
        """
        GIVEN rust-analyzer is NOT installed anywhere
        AND rustup IS installed
        WHEN _ensure_rust_analyzer_installed is called
        AND rustup component add SUCCEEDS
        BUT the binary is still not found after installation
        THEN it should raise RuntimeError indicating installation succeeded but binary missing

        WHY: This edge case (install reports success but binary not in expected location)
        needs a specific error message to help diagnose rustup configuration issues.
        """
        from solidlsp.language_servers.rust_analyzer import RustAnalyzer

        with patch("shutil.which", return_value=None):
            with patch("os.path.isfile", return_value=False):
                with patch.object(RustAnalyzer, "_get_rust_analyzer_via_rustup", return_value=None):
                    with patch.object(RustAnalyzer, "_get_rustup_version", return_value="1.70.0"):
                        with patch("subprocess.run") as mock_run:
                            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                            with pytest.raises(RuntimeError) as exc_info:
                                RustAnalyzer._ensure_rust_analyzer_installed()

        error_message = str(exc_info.value)
        # Error should indicate installation appeared to succeed but binary not found
        assert "installation succeeded" in error_message.lower() or "not found" in error_message.lower()


class TestRustAnalyzerDetectionIntegration:
    """
    Integration tests that verify detection works on the current system.
    These tests are skipped if rust-analyzer is not installed.
    """

    @pytest.mark.rust
    def test_detection_finds_installed_rust_analyzer(self):
        """
        GIVEN rust-analyzer is installed on this system (via any method)
        WHEN _ensure_rust_analyzer_installed is called
        THEN it should return a valid path

        This test verifies the detection logic works end-to-end on the current system.
        """
        import shutil

        from solidlsp.language_servers.rust_analyzer import RustAnalyzer

        # Skip if rust-analyzer is not installed at all
        if not shutil.which("rust-analyzer"):
            # Check common locations
            common_paths = [
                "/opt/homebrew/bin/rust-analyzer",
                "/usr/local/bin/rust-analyzer",
                os.path.expanduser("~/.cargo/bin/rust-analyzer"),
            ]
            if not any(os.path.isfile(p) and os.access(p, os.X_OK) for p in common_paths):
                pytest.skip("rust-analyzer not installed on this system")

        result = RustAnalyzer._ensure_rust_analyzer_installed()

        assert result is not None
        assert os.path.isfile(result)
        assert os.access(result, os.X_OK)
