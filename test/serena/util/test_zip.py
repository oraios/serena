import io
import os
import sys
import zipfile
from pathlib import Path
import pytest

from serena.util.zip import SafeZipExtractor


@pytest.fixture
def temp_zip_file(tmp_path: Path) -> Path:
    """Create a temporary ZIP file for testing."""
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zipf:
        zipf.writestr("file1.txt", "Hello World 1")
        zipf.writestr("file2.txt", "Hello World 2")
        zipf.writestr("folder/file3.txt", "Hello World 3")
    return zip_path


def test_extract_all_success(temp_zip_file: Path, tmp_path: Path) -> None:
    """All files should extract without error."""
    dest_dir = tmp_path / "extracted"
    extractor = SafeZipExtractor(temp_zip_file, dest_dir, verbose=False)
    extractor.extract_all()

    assert (dest_dir / "file1.txt").read_text() == "Hello World 1"
    assert (dest_dir / "file2.txt").read_text() == "Hello World 2"
    assert (dest_dir / "folder" / "file3.txt").read_text() == "Hello World 3"


def test_include_patterns(temp_zip_file: Path, tmp_path: Path) -> None:
    """Only files matching include_patterns should be extracted."""
    dest_dir = tmp_path / "extracted"
    extractor = SafeZipExtractor(
        temp_zip_file, dest_dir, verbose=False, include_patterns=["*.txt"]
    )
    extractor.extract_all()

    assert (dest_dir / "file1.txt").exists()
    assert (dest_dir / "file2.txt").exists()
    assert (dest_dir / "folder" / "file3.txt").exists()


def test_exclude_patterns(temp_zip_file: Path, tmp_path: Path) -> None:
    """Files matching exclude_patterns should be skipped."""
    dest_dir = tmp_path / "extracted"
    extractor = SafeZipExtractor(
        temp_zip_file, dest_dir, verbose=False, exclude_patterns=["file2.txt"]
    )
    extractor.extract_all()

    assert (dest_dir / "file1.txt").exists()
    assert not (dest_dir / "file2.txt").exists()
    assert (dest_dir / "folder" / "file3.txt").exists()


def test_include_and_exclude_patterns(temp_zip_file: Path, tmp_path: Path) -> None:
    """Exclude should override include if both match."""
    dest_dir = tmp_path / "extracted"
    extractor = SafeZipExtractor(
        temp_zip_file,
        dest_dir,
        verbose=False,
        include_patterns=["*.txt"],
        exclude_patterns=["file1.txt"],
    )
    extractor.extract_all()

    assert not (dest_dir / "file1.txt").exists()
    assert (dest_dir / "file2.txt").exists()
    assert (dest_dir / "folder" / "file3.txt").exists()


def test_skip_on_error(monkeypatch, temp_zip_file: Path, tmp_path: Path) -> None:
    """Should skip a file that raises an error and continue extracting others."""
    dest_dir = tmp_path / "extracted"

    original_open = zipfile.ZipFile.open

    def failing_open(self, member, *args, **kwargs):
        if member.filename == "file2.txt":
            raise IOError("Simulated failure")
        return original_open(self, member, *args, **kwargs)

    # Patch the method on the class, not on an instance
    monkeypatch.setattr(zipfile.ZipFile, "open", failing_open)

    extractor = SafeZipExtractor(temp_zip_file, dest_dir, verbose=False)
    extractor.extract_all()

    assert (dest_dir / "file1.txt").exists()
    assert not (dest_dir / "file2.txt").exists()
    assert (dest_dir / "folder" / "file3.txt").exists()

@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows-only test")
def test_long_path_normalization(temp_zip_file: Path, tmp_path: Path) -> None:
    """Ensure _normalize_path adds \\?\ prefix on Windows."""
    dest_dir = tmp_path / ("a" * 250)  # Simulate long path
    extractor = SafeZipExtractor(temp_zip_file, dest_dir, verbose=False)
    norm_path = extractor._normalize_path(dest_dir / "file.txt")
    assert str(norm_path).startswith("\\\\?\\")
