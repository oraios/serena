"""
Unit tests for the metals_db_utils module.

Tests the detection of Metals H2 database status and stale lock handling.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from solidlsp.util.metals_db_utils import (
    MetalsDbStatus,
    check_metals_db_status,
    cleanup_stale_lock,
    is_metals_process_alive,
    parse_h2_lock_file,
)


@pytest.mark.scala
class TestParseH2LockFile:
    """Tests for parse_h2_lock_file function."""

    def test_returns_none_when_file_does_not_exist(self, tmp_path: Path) -> None:
        """Should return None when lock file doesn't exist."""
        lock_path = tmp_path / "nonexistent.lock.db"
        result = parse_h2_lock_file(lock_path)
        assert result is None

    def test_parses_server_format_lock_file(self, tmp_path: Path) -> None:
        """Should parse lock file with server:host:port format."""
        lock_path = tmp_path / "metals.mv.db.lock.db"
        lock_path.write_text("server:localhost:9092\n")

        result = parse_h2_lock_file(lock_path)

        assert result is not None
        assert result.port == 9092
        assert result.lock_path == lock_path

    def test_parses_port_only_format(self, tmp_path: Path) -> None:
        """Should extract port from content containing a port number."""
        lock_path = tmp_path / "metals.mv.db.lock.db"
        lock_path.write_text("some content 9123 more content\n")

        result = parse_h2_lock_file(lock_path)

        assert result is not None
        assert result.port == 9123

    def test_parses_pid_format(self, tmp_path: Path) -> None:
        """Should extract PID from lock file content."""
        lock_path = tmp_path / "metals.mv.db.lock.db"
        lock_path.write_text("pid=12345\nserver:localhost:9092\n")

        result = parse_h2_lock_file(lock_path)

        assert result is not None
        assert result.pid == 12345
        assert result.port == 9092

    def test_handles_unreadable_file(self, tmp_path: Path) -> None:
        """Should return None for unreadable files."""
        lock_path = tmp_path / "metals.mv.db.lock.db"
        lock_path.write_text("content")
        # Make file unreadable (Unix only)
        if os.name != "nt":
            lock_path.chmod(0o000)
            try:
                result = parse_h2_lock_file(lock_path)
                assert result is None
            finally:
                lock_path.chmod(0o644)

    def test_truncates_raw_content(self, tmp_path: Path) -> None:
        """Should truncate raw_content to 200 chars."""
        lock_path = tmp_path / "metals.mv.db.lock.db"
        long_content = "x" * 500
        lock_path.write_text(long_content)

        result = parse_h2_lock_file(lock_path)

        assert result is not None
        assert len(result.raw_content) == 200


@pytest.mark.scala
class TestIsMetalsProcessAlive:
    """Tests for is_metals_process_alive function."""

    def test_returns_false_for_nonexistent_process(self) -> None:
        """Should return False for a PID that doesn't exist."""
        # Use a very high PID that's unlikely to exist
        result = is_metals_process_alive(999999999)
        assert result is False

    def test_returns_true_for_metals_process(self) -> None:
        """Should return True for a running Metals process."""
        import psutil

        with patch.object(psutil, "Process") as mock_process_class:
            mock_proc = MagicMock()
            mock_proc.is_running.return_value = True
            mock_proc.cmdline.return_value = [
                "java",
                "-Dmetals.client=vscode",
                "-jar",
                "metals.jar",
            ]
            mock_process_class.return_value = mock_proc

            result = is_metals_process_alive(12345)

            assert result is True

    def test_returns_false_for_non_metals_java_process(self) -> None:
        """Should return False for a Java process that isn't Metals."""
        import psutil

        with patch.object(psutil, "Process") as mock_process_class:
            mock_proc = MagicMock()
            mock_proc.is_running.return_value = True
            mock_proc.cmdline.return_value = [
                "java",
                "-jar",
                "some-other-app.jar",
            ]
            mock_process_class.return_value = mock_proc

            result = is_metals_process_alive(12345)

            assert result is False

    def test_returns_false_for_non_running_process(self) -> None:
        """Should return False for a process that's not running."""
        import psutil

        with patch.object(psutil, "Process") as mock_process_class:
            mock_proc = MagicMock()
            mock_proc.is_running.return_value = False
            mock_process_class.return_value = mock_proc

            result = is_metals_process_alive(12345)

            assert result is False

    def test_handles_no_such_process(self) -> None:
        """Should return False when process doesn't exist."""
        import psutil

        with patch.object(psutil, "Process") as mock_process_class:
            mock_process_class.side_effect = psutil.NoSuchProcess(12345)

            result = is_metals_process_alive(12345)

            assert result is False


@pytest.mark.scala
class TestCheckMetalsDbStatus:
    """Tests for check_metals_db_status function."""

    def test_returns_no_database_when_metals_dir_missing(self, tmp_path: Path) -> None:
        """Should return NO_DATABASE when .metals directory doesn't exist."""
        status, lock_info = check_metals_db_status(tmp_path)

        assert status == MetalsDbStatus.NO_DATABASE
        assert lock_info is None

    def test_returns_no_database_when_db_missing(self, tmp_path: Path) -> None:
        """Should return NO_DATABASE when database file doesn't exist."""
        metals_dir = tmp_path / ".metals"
        metals_dir.mkdir()

        status, lock_info = check_metals_db_status(tmp_path)

        assert status == MetalsDbStatus.NO_DATABASE
        assert lock_info is None

    def test_returns_no_lock_when_lock_file_missing(self, tmp_path: Path) -> None:
        """Should return NO_LOCK when database exists but lock doesn't."""
        metals_dir = tmp_path / ".metals"
        metals_dir.mkdir()
        db_path = metals_dir / "metals.mv.db"
        db_path.touch()

        status, lock_info = check_metals_db_status(tmp_path)

        assert status == MetalsDbStatus.NO_LOCK
        assert lock_info is None

    def test_returns_active_instance_when_process_alive(self, tmp_path: Path) -> None:
        """Should return ACTIVE_INSTANCE when lock holder is running."""
        import solidlsp.util.metals_db_utils as metals_utils

        metals_dir = tmp_path / ".metals"
        metals_dir.mkdir()
        db_path = metals_dir / "metals.mv.db"
        db_path.touch()
        lock_path = metals_dir / "metals.mv.db.lock.db"
        lock_path.write_text("pid=12345\nserver:localhost:9092\n")

        with patch.object(metals_utils, "is_metals_process_alive", return_value=True):
            status, lock_info = check_metals_db_status(tmp_path)

        assert status == MetalsDbStatus.ACTIVE_INSTANCE
        assert lock_info is not None
        assert lock_info.is_stale is False

    def test_returns_stale_lock_when_process_dead(self, tmp_path: Path) -> None:
        """Should return STALE_LOCK when lock holder is not running."""
        import solidlsp.util.metals_db_utils as metals_utils

        metals_dir = tmp_path / ".metals"
        metals_dir.mkdir()
        db_path = metals_dir / "metals.mv.db"
        db_path.touch()
        lock_path = metals_dir / "metals.mv.db.lock.db"
        lock_path.write_text("pid=12345\nserver:localhost:9092\n")

        with patch.object(metals_utils, "is_metals_process_alive", return_value=False):
            status, lock_info = check_metals_db_status(tmp_path)

        assert status == MetalsDbStatus.STALE_LOCK
        assert lock_info is not None
        assert lock_info.is_stale is True


@pytest.mark.scala
class TestCleanupStaleLock:
    """Tests for cleanup_stale_lock function."""

    def test_removes_lock_file(self, tmp_path: Path) -> None:
        """Should successfully remove a lock file."""
        lock_path = tmp_path / "metals.mv.db.lock.db"
        lock_path.touch()

        result = cleanup_stale_lock(lock_path)

        assert result is True
        assert not lock_path.exists()

    def test_returns_true_when_file_already_removed(self, tmp_path: Path) -> None:
        """Should return True when file doesn't exist."""
        lock_path = tmp_path / "nonexistent.lock.db"

        result = cleanup_stale_lock(lock_path)

        assert result is True

    def test_returns_false_on_permission_error(self, tmp_path: Path) -> None:
        """Should return False when file can't be removed due to permissions."""
        if os.name == "nt":
            pytest.skip("Permission test not reliable on Windows")

        lock_path = tmp_path / "metals.mv.db.lock.db"
        lock_path.touch()
        # Make parent directory read-only
        tmp_path.chmod(0o555)

        try:
            result = cleanup_stale_lock(lock_path)
            assert result is False
            assert lock_path.exists()
        finally:
            tmp_path.chmod(0o755)
