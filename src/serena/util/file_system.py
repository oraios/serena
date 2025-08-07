import glob
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

import pathspec
from pathspec import PathSpec

log = logging.getLogger(__name__)


class ScanResult(NamedTuple):
    """Result of scanning a directory."""

    directories: list[str]
    files: list[str]


def scan_directory(
    path: str,
    recursive: bool = False,
    relative_to: str | None = None,
    is_ignored_dir: Callable[[str], bool] = lambda x: False,
    is_ignored_file: Callable[[str], bool] = lambda x: False,
) -> ScanResult:
    """
    :param path: the path to scan
    :param recursive: whether to recursively scan subdirectories
    :param relative_to: the path to which the results should be relative to; if None, provide absolute paths
    :param is_ignored_dir: a function with which to determine whether the given directory (abs. path) shall be ignored
    :param is_ignored_file: a function with which to determine whether the given file (abs. path) shall be ignored
    :return: the list of directories and files
    """
    files = []
    directories = []

    abs_path = os.path.abspath(path)
    rel_base = os.path.abspath(relative_to) if relative_to else None

    try:
        with os.scandir(abs_path) as entries:
            for entry in entries:
                try:
                    entry_path = entry.path

                    if rel_base:
                        result_path = os.path.relpath(entry_path, rel_base)
                    else:
                        result_path = entry_path

                    if entry.is_file():
                        if not is_ignored_file(entry_path):
                            files.append(result_path)
                    elif entry.is_dir():
                        if not is_ignored_dir(entry_path):
                            directories.append(result_path)
                            if recursive:
                                sub_result = scan_directory(
                                    entry_path,
                                    recursive=True,
                                    relative_to=relative_to,
                                    is_ignored_dir=is_ignored_dir,
                                    is_ignored_file=is_ignored_file,
                                )
                                files.extend(sub_result.files)
                                directories.extend(sub_result.directories)
                except PermissionError as ex:
                    # Skip files/directories that cannot be accessed due to permission issues
                    log.debug(f"Skipping entry due to permission error: {entry.path}", exc_info=ex)
                    continue
    except PermissionError as ex:
        # Skip the entire directory if it cannot be accessed
        log.debug(f"Skipping directory due to permission error: {abs_path}", exc_info=ex)
        return ScanResult([], [])

    return ScanResult(directories, files)


def find_all_non_ignored_files(repo_root: str) -> list[str]:
    """
    Find all non-ignored files in the repository, respecting all gitignore files in the repository.

    :param repo_root: The root directory of the repository
    :return: A list of all non-ignored files in the repository
    """
    gitignore_parser = GitignoreParser(repo_root)
    _, files = scan_directory(
        repo_root, recursive=True, is_ignored_dir=gitignore_parser.should_ignore, is_ignored_file=gitignore_parser.should_ignore
    )
    return files


@dataclass
class GitignoreSpec:
    file_path: str
    """Path to the gitignore file."""
    patterns: list[str] = field(default_factory=list)
    """List of patterns from the gitignore file.
    The patterns are adjusted based on the gitignore file location.
    """
    pathspec: PathSpec = field(init=False)
    """Compiled PathSpec object for pattern matching."""

    def __post_init__(self) -> None:
        """Initialize the PathSpec from patterns."""
        self.pathspec = PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, self.patterns)

    def matches(self, relative_path: str) -> bool:
        """
        Check if the given path matches any pattern in this gitignore spec.

        :param relative_path: Path to check (should be relative to repo root)
        :return: True if path matches any pattern
        """
        return match_path(relative_path, self.pathspec, root_path=os.path.dirname(self.file_path))


class GitignoreParser:
    """
    Parser for gitignore files in a repository.

    This class handles parsing multiple gitignore files throughout a repository
    and provides methods to check if paths should be ignored.
    """

    def __init__(self, repo_root: str) -> None:
        """
        Initialize the parser for a repository.

        :param repo_root: Root directory of the repository
        """
        self.repo_root = os.path.abspath(repo_root)
        self.ignore_specs: list[GitignoreSpec] = []
        self._load_gitignore_files()

    def _load_gitignore_files(self) -> None:
        """Load all gitignore files from the repository."""
        gitignore_files = self._find_gitignore_files()

        for gitignore_file in gitignore_files:
            spec = self._create_ignore_spec(gitignore_file)
            if spec.patterns:  # Only add non-empty specs
                self.ignore_specs.append(spec)

    def _find_gitignore_files(self) -> list[str]:
        """
        Find all .gitignore files in the repository.

        :return: List of absolute paths to .gitignore files
        """
        return glob.glob(self.repo_root + "/.gitignore") + glob.glob(self.repo_root + "/**/.gitignore")

    def _create_ignore_spec(self, gitignore_file_path: str) -> GitignoreSpec:
        """
        Create a GitignoreSpec from a single gitignore file.

        :param gitignore_file_path: Path to the .gitignore file
        :return: GitignoreSpec object for the gitignore patterns
        """
        try:
            with open(gitignore_file_path, encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            # If we can't read the file, return an empty spec
            return GitignoreSpec(gitignore_file_path, [])

        gitignore_dir = os.path.dirname(gitignore_file_path)
        patterns = self._parse_gitignore_content(content, gitignore_dir)

        return GitignoreSpec(gitignore_file_path, patterns)

    def _parse_gitignore_content(self, content: str, gitignore_dir: str) -> list[str]:
        """
        Parse gitignore content and adjust patterns based on the gitignore file location.

        :param content: Content of the .gitignore file
        :param gitignore_dir: Directory containing the .gitignore file (absolute path)
        :return: List of adjusted patterns
        """
        patterns = []

        # Get the relative path from repo root to the gitignore directory
        rel_dir = os.path.relpath(gitignore_dir, self.repo_root)
        if rel_dir == ".":
            rel_dir = ""

        for line in content.splitlines():
            # Strip trailing whitespace (but preserve leading whitespace for now)
            line = line.rstrip()

            # Skip empty lines and comments
            if not line or line.lstrip().startswith("#"):
                continue

            # Store whether this is a negation pattern
            is_negation = line.startswith("!")
            if is_negation:
                line = line[1:]

            # Strip leading/trailing whitespace after removing negation
            line = line.strip()

            if not line:
                continue

            # Handle escaped characters at the beginning
            if line.startswith(("\\#", "\\!")):
                line = line[1:]

            # Determine if pattern is anchored to the gitignore directory and remove leading slash for processing
            is_anchored = line.startswith("/")
            if is_anchored:
                line = line[1:]

            # Adjust pattern based on gitignore file location
            if rel_dir:
                if is_anchored:
                    # Anchored patterns are relative to the gitignore directory
                    adjusted_pattern = os.path.join(rel_dir, line)
                else:
                    # Non-anchored patterns can match anywhere below the gitignore directory
                    # We need to preserve this behavior
                    if line.startswith("**/"):
                        adjusted_pattern = line
                    else:
                        # Add the directory prefix but also allow matching in subdirectories
                        adjusted_pattern = os.path.join(rel_dir, "**", line)
            else:
                if is_anchored:
                    # Anchored patterns in root should only match at root level
                    # Add leading slash back to indicate root-only matching
                    adjusted_pattern = "/" + line
                else:
                    # Non-anchored patterns can match anywhere
                    adjusted_pattern = line

            # Re-add negation if needed
            if is_negation:
                adjusted_pattern = "!" + adjusted_pattern

            # Normalize path separators to forward slashes (gitignore uses forward slashes)
            adjusted_pattern = adjusted_pattern.replace(os.sep, "/")

            patterns.append(adjusted_pattern)

        return patterns

    def should_ignore(self, path: str) -> bool:
        """
        Check if a path should be ignored based on the gitignore rules.

        :param path: Path to check (absolute or relative to repo_root)
        :return: True if the path should be ignored, False otherwise
        """
        # Convert to relative path from repo root
        if os.path.isabs(path):
            try:
                rel_path = os.path.relpath(path, self.repo_root)
            except Exception as e:
                # If the path could not be converted to a relative path,
                # it is outside the repository root, so we ignore it
                log.info("Ignoring path '%s' which is outside of the repository root (%s)", path, e)
                return True
        else:
            rel_path = path

        # Ignore paths inside .git
        rel_path_first_path = Path(rel_path).parts[0]
        if rel_path_first_path == ".git":
            return True

        abs_path = os.path.join(self.repo_root, rel_path)

        # Normalize path separators
        rel_path = rel_path.replace(os.sep, "/")

        if os.path.exists(abs_path) and os.path.isdir(abs_path) and not rel_path.endswith("/"):
            rel_path = rel_path + "/"

        # Check against each ignore spec
        for spec in self.ignore_specs:
            if spec.matches(rel_path):
                return True

        return False

    def get_ignore_specs(self) -> list[GitignoreSpec]:
        """
        Get all loaded gitignore specs.

        :return: List of GitignoreSpec objects
        """
        return self.ignore_specs

    def reload(self) -> None:
        """Reload all gitignore files from the repository."""
        self.ignore_specs.clear()
        self._load_gitignore_files()


def match_path(relative_path: str, path_spec: PathSpec, root_path: str = "") -> bool:
    """
    Match a relative path against a given pathspec. Just pathspec.match_file() is not enough,
    we need to do some massaging to fix issues with pathspec matching.

    :param relative_path: relative path to match against the pathspec
    :param path_spec: the pathspec to match against
    :param root_path: the root path from which the relative path is derived
    :return:
    """
    normalized_path = str(relative_path).replace(os.path.sep, "/")

    # We can have patterns like /src/..., which would only match corresponding paths from the repo root
    # Unfortunately, pathspec can't know whether a relative path is relative to the repo root or not,
    # so it will never match src/...
    # The fix is to just always assume that the input path is relative to the repo root and to
    # prefix it with /.
    if not normalized_path.startswith("/"):
        normalized_path = "/" + normalized_path

    # pathspec can't handle the matching of directories if they don't end with a slash!
    # see https://github.com/cpburnz/python-pathspec/issues/89
    abs_path = os.path.abspath(os.path.join(root_path, relative_path))
    if os.path.isdir(abs_path) and not normalized_path.endswith("/"):
        normalized_path = normalized_path + "/"
    return path_spec.match_file(normalized_path)
