"""Utilities for secure, deterministic downloads (retries & safe extraction)."""
from __future__ import annotations

import logging
import random
import shutil
import tarfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from solidlsp.ls_exceptions import SolidLSPException

_log = logging.getLogger(__name__)


def download_with_retries(
    url: str,
    dest: Path,
    attempts: int = 3,
    backoff_base: float = 0.5,
    fetch_fn: Optional[Callable[[str, Path], None]] = None,
) -> Path:
    """Download URL to dest with bounded retries.

    fetch_fn injected for testability (defaults to urllib).
    """
    import urllib.request

    if fetch_fn is None:
        def _default_fetch(u: str, p: Path):  # type: ignore
            urllib.request.urlretrieve(u, p)
        fetch_fn = _default_fetch

    last_err: Exception | None = None
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, attempts + 1):
        try:
            if dest.exists():
                dest.unlink()
            _log.debug("Downloading %s -> %s (attempt %d/%d)", url, dest, attempt, attempts)
            fetch_fn(url, dest)
            return dest
        except Exception as e:  # pragma: no cover - network variability
            last_err = e
            sleep_for = backoff_base * (2 ** (attempt - 1)) + random.uniform(0, 0.1)
            _log.warning("Download failed (%s). Retrying in %.2fs", e, sleep_for)
            time.sleep(sleep_for)
    raise SolidLSPException(f"Failed to download {url} after {attempts} attempts: {last_err}")


def safe_extract_zip(archive: Path, target_dir: Path) -> None:
    from solidlsp.util.zip import SafeZipExtractor
    extractor = SafeZipExtractor(archive_path=archive, extract_dir=target_dir, verbose=False)
    extractor.extract_all()


def safe_extract_tar_gz(archive: Path, target_dir: Path) -> None:
    """Extract a .tar.gz safely (prevent path traversal)."""
    def is_within_directory(directory: Path, target: Path) -> bool:
        try:
            directory = directory.resolve()
            target = target.resolve()
            return str(target).startswith(str(directory))
        except Exception:  # pragma: no cover - defensive
            return False

    with tarfile.open(archive, 'r:gz') as tf:
        for member in tf.getmembers():
            member_path = target_dir / member.name
            if not is_within_directory(target_dir, member_path):
                raise SolidLSPException(f"Refusing to extract path-traversal entry: {member.name}")
        tf.extractall(target_dir)


def cleanup_path(p: Path) -> None:
    try:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink()
    except Exception:  # pragma: no cover - best effort
        pass
