"""Scope filters — what gets synced, what's hard-excluded.

Inclusion is composable via settings; exclusion is a hard rule enforced
regardless of configuration (credential files, oversize binaries, symlinks).
The scope layer is the safety net that prevents accidentally uploading
``.env`` or ``id_rsa`` no matter how the user configures paths.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

import pathspec

from serena.cloud_sync.exceptions import ScopeError
from serena.cloud_sync.settings import MAX_OBJECT_SIZE_BYTES

HARD_EXCLUDE_PATTERNS: tuple[str, ...] = (
    "**/logs/**",
    "**/cache/**",
    "**/ls-cache/**",
    "**/*.env",
    "**/*.env.*",
    "**/*.secret",
    "**/*.secret.*",
    "**/*.key",
    "**/*.pem",
    "**/id_rsa",
    "**/id_rsa.pub",
    "**/*:Zone.Identifier",
)


@dataclass(frozen=True)
class ScopeRoot:
    """A root directory to scan, with a remote-key prefix under the sync root.

    ``remote_subprefix`` is joined after ``root_prefix`` from settings. For
    example, a global root produces keys ``serena-sync/global/<relpath>``.
    """
    local_root: Path
    remote_subprefix: str
    opt_in_local_yml: bool = False
    """If False, project.local.yml is hard-excluded from this root."""


@dataclass
class ScopeFilter:
    include_patterns: tuple[str, ...]
    opt_in_project_local_yml: bool = False

    _hard_exclude: pathspec.PathSpec = field(init=False)
    _include: pathspec.PathSpec = field(init=False)

    def __post_init__(self) -> None:
        hard = list(HARD_EXCLUDE_PATTERNS)
        if not self.opt_in_project_local_yml:
            hard.append("**/project.local.yml")
        self._hard_exclude = pathspec.PathSpec.from_lines(
            pathspec.patterns.GitWildMatchPattern, hard
        )
        self._include = pathspec.PathSpec.from_lines(
            pathspec.patterns.GitWildMatchPattern, list(self.include_patterns)
        )

    def is_hard_excluded(self, rel_posix: str) -> bool:
        return self._hard_exclude.match_file(rel_posix)

    def is_included(self, rel_posix: str) -> bool:
        return self._include.match_file(rel_posix) and not self._hard_exclude.match_file(rel_posix)

    def iter_files(self, roots: Iterable[ScopeRoot]) -> Iterator[tuple[ScopeRoot, Path, str]]:
        """Yield (root, absolute_path, posix_relpath) for every file that passes
        all scope rules (include + hard-exclude + size cap + symlink reject).
        """
        for root in roots:
            if not root.local_root.exists():
                continue
            for p in _walk_files(root.local_root):
                rel = p.relative_to(root.local_root).as_posix()
                if not self.is_included(rel):
                    continue
                try:
                    st = p.lstat()
                except OSError:
                    continue
                if _is_symlink(st):
                    continue
                if st.st_size > MAX_OBJECT_SIZE_BYTES:
                    continue
                yield root, p, rel


def _walk_files(root: Path) -> Iterator[Path]:
    """os.walk wrapper that tolerates a permission error on any subdir."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=lambda _e: None):
        base = Path(dirpath)
        for fn in filenames:
            yield base / fn


def _is_symlink(st: os.stat_result) -> bool:
    from stat import S_ISLNK
    return S_ISLNK(st.st_mode)


def enforce_no_credential_files(rel_posix: str) -> None:
    """Defensive check used at upload time. Raises ScopeError if the path is
    a credential file pattern even if include rules would have permitted it."""
    # Normalize a bare relpath into a pseudo-path pathspec can match
    probe = pathspec.PathSpec.from_lines(
        pathspec.patterns.GitWildMatchPattern, list(HARD_EXCLUDE_PATTERNS)
    )
    if probe.match_file(rel_posix):
        raise ScopeError(f"refusing to sync credential-family path: {rel_posix}")


DEFAULT_GLOBAL_INCLUDES: tuple[str, ...] = (
    "serena_config.yml",
    "contexts/**/*.yml",
    "contexts/**/*.yaml",
    "modes/**/*.yml",
    "modes/**/*.yaml",
    "memories/**/*",
)

DEFAULT_PROJECT_INCLUDES: tuple[str, ...] = (
    "project.yml",
    "project.local.yml",  # filtered out unless opt-in flag flips it on
    "memories/**/*.md",
    "memories/**/*.json",
)
