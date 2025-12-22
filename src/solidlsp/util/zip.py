import fnmatch
import logging
import os
import sys
import zipfile
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class SafeZipExtractor:
    """
    A utility class for extracting ZIP archives safely.

    Features:
    - Handles long file paths on Windows
    - Skips files that fail to extract, continuing with the rest
    - Creates necessary directories automatically
    - Optional include/exclude pattern filters
    """

    def __init__(
        self,
        archive_path: Path,
        extract_dir: Path,
        verbose: bool = True,
        include_patterns: Optional[list[str]] = None,
        exclude_patterns: Optional[list[str]] = None,
    ) -> None:
        """
        Initialize the SafeZipExtractor.

        :param archive_path: Path to the ZIP archive file
        :param extract_dir: Directory where files will be extracted
        :param verbose: Whether to log status messages
        :param include_patterns: List of glob patterns for files to extract (None = all files)
        :param exclude_patterns: List of glob patterns for files to skip
        """
        self.archive_path = Path(archive_path)
        self.extract_dir = Path(extract_dir)
        self.verbose = verbose
        self.include_patterns = include_patterns or []
        self.exclude_patterns = exclude_patterns or []

    def extract_all(self) -> None:
        """
        Extract all files from the archive, skipping any that fail.
        """
        if not self.archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {self.archive_path}")

        if self.verbose:
            log.info(f"Extracting from: {self.archive_path} to {self.extract_dir}")

        with zipfile.ZipFile(self.archive_path, "r") as zip_ref:
            for member in zip_ref.infolist():
                if self._should_extract(member.filename):
                    self._extract_member(zip_ref, member)
                elif self.verbose:
                    log.info(f"Skipped: {member.filename}")

    def _should_extract(self, filename: str) -> bool:
        """
        Determine whether a file should be extracted based on include/exclude patterns.

        :param filename: The file name from the archive
        :return: True if the file should be extracted
        """
        # If include_patterns is set, only extract if it matches at least one pattern
        if self.include_patterns:
            if not any(fnmatch.fnmatch(filename, pattern) for pattern in self.include_patterns):
                return False

        # If exclude_patterns is set, skip if it matches any pattern
        if self.exclude_patterns:
            if any(fnmatch.fnmatch(filename, pattern) for pattern in self.exclude_patterns):
                return False

        return True

    def _extract_member(self, zip_ref: zipfile.ZipFile, member: zipfile.ZipInfo) -> None:
        """
        Extract a single member from the archive with error handling.

        :param zip_ref: Open ZipFile object
        :param member: ZipInfo object representing the file
        """
        try:
            target_path = self.extract_dir / member.filename

            # Ensure directory structure exists
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Handle long paths on Windows
            final_path = self._normalize_path(target_path)

            # Extract file
            with zip_ref.open(member) as source, open(final_path, "wb") as target:
                target.write(source.read())

            if self.verbose:
                log.info(f"Extracted: {member.filename}")

        except Exception as e:
            log.error(f"Failed to extract {member.filename}: {e}")

    @staticmethod
    def _normalize_path(path: Path) -> Path:
        """
        Adjust path to handle long paths on Windows.

        :param path: Original path
        :return: Normalized path
        """
        if sys.platform.startswith("win"):
            return Path(rf"\\?\{os.path.abspath(path)}")
        return path  # type: ignore


# Example usage:
# extractor = SafeZipExtractor(
#     archive_path=Path("file.nupkg"),
#     extract_dir=Path("extract_dir"),
#     include_patterns=["*.dll", "*.xml"],
#     exclude_patterns=["*.pdb"]
# )
# extractor.extract_all()
