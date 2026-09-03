import logging
import os
import re
import stat
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

import pathspec
from pathspec import PathSpec
from sensai.util.logging import LogTime

log = logging.getLogger(__name__)


def write_file_atomic(path: str, content: str, *, encoding: str, newline: str | None = None) -> None:
    """
    Write ``content`` to ``path`` atomically: the content is written to a temporary file in the
    same directory first, then swapped into place with ``os.replace``. A plain
    ``open(path, "w")`` is not atomic: it truncates the file before the new content is complete,
    so a crash, an out-of-memory kill, or a disk-full error partway through the write leaves
    ``path`` holding neither the old content nor the new one.

    :param path: the path to write to
    :param content: the text content to write
    :param encoding: the encoding to use for the write
    :param newline: passed through to the underlying ``open()`` call to control newline translation
    """
    target_dir = os.path.dirname(path) or "."
    try:
        existing_mode: int | None = stat.S_IMODE(os.stat(path).st_mode)
    except FileNotFoundError:
        existing_mode = None
    fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix=os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline=newline) as f:
            f.write(content)
        # mkstemp creates the temp file with mode 0600 regardless of umask, which would silently
        # tighten an existing file's permissions (e.g. 0644 -> 0600) on replace. Restore the
        # original mode, or fall back to what a plain open(path, "w") would have produced for a
        # new file (0666 masked by the process umask).
        os.chmod(tmp_path, existing_mode if existing_mode is not None else _new_file_mode())
        _replace_with_retry(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _new_file_mode() -> int:
    """The mode a plain ``open(path, "w")`` would give a brand-new file: 0o666 masked by the
    process umask. Reading the umask requires setting it, so the previous value is restored
    immediately after.
    """
    current_umask = os.umask(0o022)
    os.umask(current_umask)
    return 0o666 & ~current_umask


def _replace_with_retry(src: str, dst: str, *, attempts: int = 10, delay_s: float = 0.05) -> None:
    """``os.replace(src, dst)`` with a short retry on a Windows sharing violation: on Windows the
    atomic rename fails with ``PermissionError`` if another process momentarily holds ``dst`` open
    (e.g. a second Serena process reading the same memory or source file). A brief bounded retry
    rides out that contention; the temp file is still complete, so this never falls back to a
    non-atomic write.
    """
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay_s)


# Characters meaningful to pathspec's gitignore grammar: glob wildcards, bracket expressions,
# the escape character itself, and '!'/'#' which change a whole pattern's meaning when they
# are its first character. Backslash-escaping them makes a literal name safe to interpolate.
_GITIGNORE_PATTERN_SPECIAL_CHARS_RE = re.compile(r"([\\*?\[\]!#])")


def _escape_gitignore_path_component(component: str) -> str:
    """Escape gitignore/pathspec pattern metacharacters in a single path component (no
    separators) so it is matched as a literal name rather than as glob syntax.
    """
    return _GITIGNORE_PATTERN_SPECIAL_CHARS_RE.sub(r"\\\1", component)


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
            try:
                entries = os.scandir(abs_path)
            except PermissionError as ex:
                log.debug(f"Skipping unreadable directory {abs_path}: {ex}")
                return
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=follow_symlinks):
                        queue.append(entry.path)
                    elif entry.is_file(follow_symlinks=follow_symlinks) and entry.name == ".gitignore":
                        yield entry.path
                except PermissionError as ex:
                    log.debug(f"Skipping entry due to permission error: {entry.path}", exc_info=ex)
                    continue
                except FileNotFoundError as ex:
                    log.debug(f"Skipping entry due to file not found error (possibly a broken link): {entry.path}", exc_info=ex)
                    continue

        while queue:
            next_abs_path = queue.pop(0)
            if next_abs_path != self.repo_root:
                try:
                    rel_path = os.path.relpath(next_abs_path, self.repo_root)
                except ValueError:
                    # If the path is on a different drive (Windows) or cannot be made relative for another reason, we ignore it
                    continue
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

        # Get the relative path from repo root to the gitignore directory. Normalize to
        # forward slashes immediately: os.path.relpath returns native separators, but
        # gitignore/pathspec patterns are always POSIX-style, and on Windows os.sep is
        # backslash -- the same character pathspec uses as its escape character. Building
        # the pattern with any raw os.sep would make a later blanket backslash->slash
        # normalization indistinguishable from the escape backslashes below.
        rel_dir = os.path.relpath(gitignore_dir, self.repo_root).replace(os.sep, "/")
        if rel_dir == ".":
            rel_dir = ""

        # rel_dir is a filesystem path, but the code below interpolates it into pattern
        # position; escape each of its components so a directory name containing pattern
        # metacharacters (e.g. "***") is matched literally instead of as glob syntax.
        rel_dir_pattern = "/".join(_escape_gitignore_path_component(part) for part in rel_dir.split("/")) if rel_dir else rel_dir

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

            # Adjust pattern based on gitignore file location. Joined with a literal "/",
            # never os.path.join/os.sep: gitignore patterns are always POSIX-style, and on
            # Windows os.sep is backslash, indistinguishable from the escape backslashes
            # rel_dir_pattern may already contain.
            if rel_dir:
                if is_anchored:
                    # Anchored patterns are relative to the gitignore directory
                    adjusted_pattern = f"{rel_dir_pattern}/{line}"
                else:
                    # Non-anchored patterns can match anywhere below the gitignore directory
                    # We need to preserve this behavior
                    if line.startswith("**/"):
                        # Even if pattern starts with **, it should still be scoped to the subdirectory
                        adjusted_pattern = f"{rel_dir_pattern}/{line}"
                    else:
                        # Add the directory prefix but also allow matching in subdirectories
                        adjusted_pattern = f"{rel_dir_pattern}/**/{line}"
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
    if str(relative_path) in {"", "."}:
        return False

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
