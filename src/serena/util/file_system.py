import logging
import os
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

import pathspec
from pathspec import PathSpec
from sensai.util.logging import LogTime

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GitState:
    """Represents the current git state of a repository."""

    branch: str
    commit: str
    worktree_path: str | None = None  # Stored as string for hashability
    is_worktree: bool = False

    def __str__(self) -> str:
        worktree_info = f" (worktree: {self.worktree_path})" if self.is_worktree else ""
        return f"branch={self.branch}{worktree_info}, commit={self.commit[:8]}"

    def __eq__(self, other) -> bool:
        if not isinstance(other, GitState):
            return False
        return (
            self.branch == other.branch
            and self.commit == other.commit
            and self.worktree_path == other.worktree_path
            and self.is_worktree == other.is_worktree
        )

    def __hash__(self) -> int:
        return hash((self.branch, self.commit, self.worktree_path, self.is_worktree))


def is_git_worktree(path: str | Path) -> bool:
    """
    Detect if the given path is inside a git worktree.

    A git worktree has a `.git` file (not directory) that contains a reference
    to the main repository's git directory.

    :param path: the path to check
    :return: True if the path is inside a git worktree, False otherwise
    """
    git_path = Path(path) / ".git"
    # A worktree has a .git file (not directory) with "gitdir:" inside
    return git_path.is_file() and _is_git_worktree_file(git_path)


def _is_git_worktree_file(git_file: Path) -> bool:
    """Check if the given .git file is a worktree reference."""
    try:
        with open(git_file) as f:
            content = f.read().strip()
            return content.startswith("gitdir:")
    except OSError:
        return False


def find_git_main_repo_path(path: str | Path) -> Path | None:
    """
    Find the main repository path for a given path.

    If the path is inside a git worktree, this returns the path to the main
    repository (the one containing the actual .git directory).

    :param path: the path to check
    :return: Path to the main repository, or None if not a worktree
    """
    path = Path(path).resolve()
    git_path = path / ".git"

    if not is_git_worktree(path):
        return None

    # Read the gitdir from the .git file
    try:
        with open(git_path) as f:
            content = f.read().strip()
            if content.startswith("gitdir:"):
                gitdir = content.split(":", 1)[1].strip()
                gitdir_path = Path(gitdir).resolve()

                # The worktrees directory structure is:
                # <main-repo>/.git/worktrees/<worktree-name>/
                # The main repo is before .git/worktrees/<name>
                if ".git/worktrees/" in str(gitdir_path):
                    # Extract the main repo path
                    parts = gitdir_path.parts
                    worktrees_idx = parts.index(".git")
                    # The main repo is before .git/worktrees/<name>
                    main_repo = Path(*parts[:worktrees_idx])
                    return main_repo
    except (OSError, ValueError):
        pass

    # Fallback: try using git command
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=False,
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            toplevel = Path(result.stdout.strip()).resolve()
            # If toplevel differs from input path, we're in a worktree
            if toplevel != path:
                return toplevel
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return None


def get_git_common_dir(path: str | Path) -> Path | None:
    """
    Get the common git directory for a repository or worktree.

    For a regular repo, this is <path>/.git.
    For a worktree, this is the main repo's .git directory.

    :param path: the path to check
    :return: Path to the common git directory, or None if not a git repo
    """
    path = Path(path).resolve()

    # Try git rev-parse --git-common-dir first (most reliable)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            check=False,
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            common_dir = result.stdout.strip()
            if common_dir:
                return Path(common_dir).resolve()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Fallback to checking .git directly
    git_path = path / ".git"
    if git_path.is_dir():
        return git_path
    elif is_git_worktree(path):
        return find_git_main_repo_path(path) / ".git" if find_git_main_repo_path(path) else None

    return None


def get_git_state(path: str | Path) -> GitState | None:
    """
    Get the current git state (branch, commit, worktree info) for a path.

    :param path: The path to check
    :return: GitState with current branch, commit, and worktree info, or None if not a git repo
    """
    path = Path(path).resolve()

    # Check if this is a worktree
    is_wt = is_git_worktree(path)
    worktree_path_obj = find_git_main_repo_path(path) if is_wt else None
    worktree_path = str(worktree_path_obj) if worktree_path_obj else None

    try:
        # Get the current branch name
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            check=False,
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        branch = result.stdout.strip()

        # Get the current commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        commit = result.stdout.strip()

        return GitState(
            branch=branch,
            commit=commit,
            worktree_path=worktree_path,
            is_worktree=is_wt,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


class ScanResult(NamedTuple):
    """Result of scanning a directory."""

    directories: list[str]
    files: list[str]


def scan_directory(
    path: str,
    recursive: bool = False,
    relative_to: str | None = None,
    is_ignored_dir: Callable[[str], bool] | None = None,
    is_ignored_file: Callable[[str], bool] | None = None,
) -> ScanResult:
    """
    :param path: the path to scan
    :param recursive: whether to recursively scan subdirectories
    :param relative_to: the path to which the results should be relative to; if None, provide absolute paths
    :param is_ignored_dir: a function with which to determine whether the given directory (abs. path) shall be ignored
    :param is_ignored_file: a function with which to determine whether the given file (abs. path) shall be ignored
    :return: the list of directories and files
    """
    if is_ignored_file is None:
        is_ignored_file = lambda x: False
    if is_ignored_dir is None:
        is_ignored_dir = lambda x: False

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
                        try:
                            result_path = os.path.relpath(entry_path, rel_base)
                        except:
                            log.debug(f"Skipping entry due to relative path conversion error: {entry.path}")
                            continue
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
        with LogTime("Loading of .gitignore files", logger=log):
            for gitignore_path in self._iter_gitignore_files():
                log.info("Processing .gitignore file: %s", gitignore_path)
                spec = self._create_ignore_spec(gitignore_path)
                if spec.patterns:  # Only add non-empty specs
                    self.ignore_specs.append(spec)

    def _iter_gitignore_files(self, follow_symlinks: bool = False) -> Iterator[str]:
        """
        Iteratively discover .gitignore files in a top-down fashion, starting from the repository root.
        Directory paths are skipped if they match any already loaded ignore patterns.

        :return: an iterator yielding paths to .gitignore files (top-down)
        """
        queue: list[str] = [self.repo_root]

        def scan(abs_path: str | None) -> Iterator[str]:
            for entry in os.scandir(abs_path):
                if entry.is_dir(follow_symlinks=follow_symlinks):
                    queue.append(entry.path)
                elif entry.is_file(follow_symlinks=follow_symlinks) and entry.name == ".gitignore":
                    yield entry.path

        while queue:
            next_abs_path = queue.pop(0)
            if next_abs_path != self.repo_root:
                rel_path = os.path.relpath(next_abs_path, self.repo_root)
                if self.should_ignore(rel_path):
                    continue
            yield from scan(next_abs_path)

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
                        # Even if pattern starts with **, it should still be scoped to the subdirectory
                        adjusted_pattern = os.path.join(rel_dir, line)
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
