"""
Unit tests for the Pascal language server auto-update functionality.

These tests validate the version comparison, checksum verification,
and other helper methods without requiring network access or the
actual Pascal language server.
"""

from __future__ import annotations

import hashlib
import os
import tarfile
import tempfile
import time

import pytest

from solidlsp.language_servers.pascal_server import PascalLanguageServer

pytestmark = [pytest.mark.pascal]


class TestVersionNormalization:
    """Test version string normalization."""

    def test_normalize_version_with_v_prefix(self) -> None:
        """Test that 'v' prefix is stripped."""
        assert PascalLanguageServer._normalize_version("v1.0.0") == "1.0.0"

    def test_normalize_version_with_capital_v_prefix(self) -> None:
        """Test that 'V' prefix is stripped."""
        assert PascalLanguageServer._normalize_version("V1.0.0") == "1.0.0"

    def test_normalize_version_without_prefix(self) -> None:
        """Test version without prefix is unchanged."""
        assert PascalLanguageServer._normalize_version("1.0.0") == "1.0.0"

    def test_normalize_version_with_whitespace(self) -> None:
        """Test that whitespace is stripped."""
        assert PascalLanguageServer._normalize_version("  v1.0.0  ") == "1.0.0"

    def test_normalize_version_empty(self) -> None:
        """Test empty version returns empty string."""
        assert PascalLanguageServer._normalize_version("") == ""

    def test_normalize_version_none(self) -> None:
        """Test None returns empty string."""
        assert PascalLanguageServer._normalize_version(None) == ""


class TestVersionComparison:
    """Test version comparison logic."""

    def test_newer_version_major(self) -> None:
        """Test detection of newer major version."""
        assert PascalLanguageServer._is_newer_version("v2.0.0", "v1.0.0") is True

    def test_newer_version_minor(self) -> None:
        """Test detection of newer minor version."""
        assert PascalLanguageServer._is_newer_version("v1.1.0", "v1.0.0") is True

    def test_newer_version_patch(self) -> None:
        """Test detection of newer patch version."""
        assert PascalLanguageServer._is_newer_version("v1.0.1", "v1.0.0") is True

    def test_same_version(self) -> None:
        """Test same version returns False."""
        assert PascalLanguageServer._is_newer_version("v1.0.0", "v1.0.0") is False

    def test_older_version(self) -> None:
        """Test older version returns False."""
        assert PascalLanguageServer._is_newer_version("v1.0.0", "v2.0.0") is False

    def test_latest_none_returns_false(self) -> None:
        """Test None latest version returns False."""
        assert PascalLanguageServer._is_newer_version(None, "v1.0.0") is False

    def test_local_none_returns_true(self) -> None:
        """Test None local version returns True (first install)."""
        assert PascalLanguageServer._is_newer_version("v1.0.0", None) is True

    def test_both_none_returns_false(self) -> None:
        """Test both None returns False."""
        assert PascalLanguageServer._is_newer_version(None, None) is False

    def test_version_with_different_lengths(self) -> None:
        """Test versions with different number of parts."""
        assert PascalLanguageServer._is_newer_version("v1.0.1", "v1.0") is True
        assert PascalLanguageServer._is_newer_version("v1.0", "v1.0.1") is False

    def test_version_with_prerelease(self) -> None:
        """Test versions with prerelease suffixes."""
        # Prerelease suffix is ignored, only numeric parts are compared
        assert PascalLanguageServer._is_newer_version("v1.1.0-beta", "v1.0.0") is True


class TestSHA256Checksum:
    """Test SHA256 checksum calculation and verification."""

    def test_calculate_sha256(self) -> None:
        """Test SHA256 calculation for a known content."""
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
            f.write(b"test content")
            temp_path = f.name

        try:
            result = PascalLanguageServer._calculate_sha256(temp_path)
            expected = hashlib.sha256(b"test content").hexdigest()
            assert result == expected
        finally:
            os.unlink(temp_path)

    def test_verify_checksum_correct(self) -> None:
        """Test checksum verification with correct checksum."""
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
            f.write(b"test content")
            temp_path = f.name

        try:
            expected = hashlib.sha256(b"test content").hexdigest()
            assert PascalLanguageServer._verify_checksum(temp_path, expected) is True
        finally:
            os.unlink(temp_path)

    def test_verify_checksum_incorrect(self) -> None:
        """Test checksum verification with incorrect checksum."""
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
            f.write(b"test content")
            temp_path = f.name

        try:
            wrong_checksum = "0" * 64
            assert PascalLanguageServer._verify_checksum(temp_path, wrong_checksum) is False
        finally:
            os.unlink(temp_path)

    def test_verify_checksum_case_insensitive(self) -> None:
        """Test checksum verification is case insensitive."""
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
            f.write(b"test content")
            temp_path = f.name

        try:
            expected = hashlib.sha256(b"test content").hexdigest().upper()
            assert PascalLanguageServer._verify_checksum(temp_path, expected) is True
        finally:
            os.unlink(temp_path)


class TestTarfileSafety:
    """Test tarfile path traversal protection."""

    def test_safe_tar_member_normal_path(self) -> None:
        """Test normal path is considered safe."""
        member = tarfile.TarInfo(name="pasls")
        assert PascalLanguageServer._is_safe_tar_member(member, "/tmp/target") is True

    def test_safe_tar_member_nested_path(self) -> None:
        """Test nested path is considered safe."""
        member = tarfile.TarInfo(name="subdir/pasls")
        assert PascalLanguageServer._is_safe_tar_member(member, "/tmp/target") is True

    def test_unsafe_tar_member_path_traversal(self) -> None:
        """Test path traversal is detected."""
        member = tarfile.TarInfo(name="../etc/passwd")
        assert PascalLanguageServer._is_safe_tar_member(member, "/tmp/target") is False

    def test_unsafe_tar_member_hidden_traversal(self) -> None:
        """Test hidden path traversal in nested path."""
        member = tarfile.TarInfo(name="subdir/../../etc/passwd")
        assert PascalLanguageServer._is_safe_tar_member(member, "/tmp/target") is False

    def test_safe_tar_member_similar_name(self) -> None:
        """Test path containing '..' in filename (not directory) is safe."""
        member = tarfile.TarInfo(name="file..name")
        assert PascalLanguageServer._is_safe_tar_member(member, "/tmp/target") is True


class TestMetadataManagement:
    """Test metadata directory and file management."""

    def test_meta_dir_creates_directory(self) -> None:
        """Test _meta_dir creates directory if not exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            meta_path = PascalLanguageServer._meta_dir(temp_dir)
            assert os.path.exists(meta_path)
            assert meta_path == os.path.join(temp_dir, PascalLanguageServer.META_DIR)

    def test_meta_file_returns_correct_path(self) -> None:
        """Test _meta_file returns correct path."""
        with tempfile.TemporaryDirectory() as temp_dir:
            meta_file = PascalLanguageServer._meta_file(temp_dir, "version")
            expected = os.path.join(temp_dir, PascalLanguageServer.META_DIR, "version")
            assert meta_file == expected


class TestUpdateCheckTiming:
    """Test update check timing logic."""

    def test_should_check_update_no_last_check(self) -> None:
        """Test should check when no last_check file exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            assert PascalLanguageServer._should_check_update(temp_dir) is True

    def test_should_check_update_recent_check(self) -> None:
        """Test should not check when recently checked."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create meta dir and last_check file with current time
            meta_dir = PascalLanguageServer._meta_dir(temp_dir)
            last_check_file = os.path.join(meta_dir, "last_check")
            with open(last_check_file, "w") as f:
                f.write(str(time.time()))

            assert PascalLanguageServer._should_check_update(temp_dir) is False

    def test_should_check_update_old_check(self) -> None:
        """Test should check when last check was > 24 hours ago."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create meta dir and last_check file with old time
            meta_dir = PascalLanguageServer._meta_dir(temp_dir)
            last_check_file = os.path.join(meta_dir, "last_check")
            old_time = time.time() - (PascalLanguageServer.UPDATE_CHECK_INTERVAL + 3600)
            with open(last_check_file, "w") as f:
                f.write(str(old_time))

            assert PascalLanguageServer._should_check_update(temp_dir) is True

    def test_update_last_check_creates_file(self) -> None:
        """Test _update_last_check creates timestamp file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            PascalLanguageServer._update_last_check(temp_dir)
            last_check_file = PascalLanguageServer._meta_file(temp_dir, "last_check")
            assert os.path.exists(last_check_file)

            with open(last_check_file) as f:
                timestamp = float(f.read().strip())
            assert abs(timestamp - time.time()) < 5  # within 5 seconds


class TestVersionPersistence:
    """Test local version persistence."""

    def test_save_and_get_local_version(self) -> None:
        """Test saving and retrieving local version."""
        with tempfile.TemporaryDirectory() as temp_dir:
            PascalLanguageServer._save_local_version(temp_dir, "v1.0.0")
            version = PascalLanguageServer._get_local_version(temp_dir)
            assert version == "v1.0.0"

    def test_get_local_version_not_exists(self) -> None:
        """Test getting version when file doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            version = PascalLanguageServer._get_local_version(temp_dir)
            assert version is None
