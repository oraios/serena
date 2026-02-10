"""
Utilities for detecting and managing Scala Metals H2 database state.

This module provides functions to detect existing Metals LSP instances by checking
the H2 database lock file, and to clean up stale locks from crashed processes.

Metals uses H2 AUTO_SERVER mode (enabled by default) to support multiple concurrent
instances sharing the same database. However, if a Metals process crashes without
proper cleanup, it can leave a stale lock file that prevents proper AUTO_SERVER
coordination, causing new instances to fall back to in-memory database mode.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


class MetalsDbStatus(Enum):
    """Status of the Metals H2 database for a project."""

    NO_DATABASE = "no_database"
    """No .metals directory or database exists (fresh project)."""

    NO_LOCK = "no_lock"
    """Database exists but no lock file (safe to start)."""

    ACTIVE_INSTANCE = "active_instance"
    """Lock held by a running process (will share via AUTO_SERVER)."""

    STALE_LOCK = "stale_lock"
    """Lock held by a dead process (needs cleanup)."""


@dataclass
class MetalsLockInfo:
    """Information extracted from an H2 database lock file."""

    pid: int | None
    """Process ID that holds the lock, if parseable."""

    port: int | None
    """TCP port for AUTO_SERVER connection, if parseable."""

    lock_path: Path
    """Path to the lock file."""

    is_stale: bool
    """True if the owning process is no longer running."""

    raw_content: str
    """Raw content of the lock file for debugging."""


def parse_h2_lock_file(lock_path: Path) -> MetalsLockInfo | None:
    """
    Parse an H2 database lock file to extract connection information.

    The H2 lock file format varies by version but typically contains
    server connection information. Common formats include:
    - Text format: "server:localhost:9092" or similar
    - Binary format with embedded PID

    Args:
        lock_path: Path to the .lock.db file

    Returns:
        MetalsLockInfo if the file can be parsed, None if file doesn't exist
        or is completely unparseable.

    """
    if not lock_path.exists():
        return None

    try:
        # Try reading as text first (most common for H2 AUTO_SERVER)
        content = lock_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        log.debug(f"Could not read lock file {lock_path}: {e}")
        return None

    pid: int | None = None
    port: int | None = None

    # Try to extract port from common H2 lock file formats
    # Format 1: "server:localhost:PORT"
    server_match = re.search(r"server:[\w.]+:(\d+)", content, re.IGNORECASE)
    if server_match:
        port = int(server_match.group(1))

    # Format 2: Look for standalone port numbers (H2 uses ports in 9000+ range typically)
    if port is None:
        port_match = re.search(r"\b(9\d{3})\b", content)
        if port_match:
            port = int(port_match.group(1))

    # Try to extract PID - H2 may embed this in various formats
    pid_match = re.search(r"pid[=:]?\s*(\d+)", content, re.IGNORECASE)
    if pid_match:
        pid = int(pid_match.group(1))

    # Check if the process is still alive
    is_stale = False
    if pid is not None:
        is_stale = not is_metals_process_alive(pid)
    elif port is not None:
        # If we have a port but no PID, try to find a Metals process using that port
        is_stale = not _is_port_in_use_by_metals(port)
    else:
        # Can't determine - assume stale if lock exists but we can't parse it
        # and no Metals processes are running for this project
        log.debug(f"Could not parse PID or port from lock file: {lock_path}")
        is_stale = True  # Conservative: treat unparseable as stale

    return MetalsLockInfo(
        pid=pid,
        port=port,
        lock_path=lock_path,
        is_stale=is_stale,
        raw_content=content[:200],  # Truncate for logging
    )


def is_metals_process_alive(pid: int) -> bool:
    """
    Check if a process with the given PID is alive and is a Metals process.

    Args:
        pid: Process ID to check

    Returns:
        True if the process exists and appears to be a Metals LSP server.

    """
    try:
        import psutil

        proc = psutil.Process(pid)
        if not proc.is_running():
            return False

        # Check if this is actually a Metals process
        cmdline = " ".join(proc.cmdline()).lower()
        return _is_metals_cmdline(cmdline)

    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False
    except Exception as e:
        log.debug(f"Error checking process {pid}: {e}")
        return False


def _is_metals_cmdline(cmdline: str) -> bool:
    """Check if a command line string appears to be a Metals LSP server."""
    cmdline_lower = cmdline.lower()
    # Metals is a Scala/Java application
    if "java" not in cmdline_lower:
        return False
    # Look for Metals-specific identifiers
    return any(
        marker in cmdline_lower
        for marker in [
            "metals",
            "org.scalameta",
            "-dmetals.client",
        ]
    )


def _is_port_in_use_by_metals(port: int) -> bool:
    """Check if the given port is in use by a Metals process."""
    try:
        import psutil

        for conn in psutil.net_connections(kind="tcp"):
            if conn.laddr.port == port and conn.status == "LISTEN":
                try:
                    proc = psutil.Process(conn.pid)
                    cmdline = " ".join(proc.cmdline()).lower()
                    if _is_metals_cmdline(cmdline):
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        return False
    except (psutil.AccessDenied, OSError) as e:
        # On some systems, net_connections requires elevated privileges
        log.debug(f"Could not check port {port}: {e}")
        return False


def check_metals_db_status(project_path: Path) -> tuple[MetalsDbStatus, MetalsLockInfo | None]:
    """
    Check the status of the Metals H2 database for a project.

    This function determines whether it's safe to start a new Metals instance
    and whether any cleanup is needed.

    Args:
        project_path: Path to the project root directory

    Returns:
        A tuple of (status, lock_info) where lock_info is populated for
        ACTIVE_INSTANCE and STALE_LOCK statuses.

    """
    metals_dir = project_path / ".metals"
    db_path = metals_dir / "metals.mv.db"
    lock_path = metals_dir / "metals.mv.db.lock.db"

    if not metals_dir.exists():
        log.debug(f"No .metals directory found at {metals_dir}")
        return MetalsDbStatus.NO_DATABASE, None

    if not db_path.exists():
        log.debug(f"No Metals database found at {db_path}")
        return MetalsDbStatus.NO_DATABASE, None

    if not lock_path.exists():
        log.debug(f"Metals database exists but no lock file at {lock_path}")
        return MetalsDbStatus.NO_LOCK, None

    # Lock file exists - parse it to determine status
    lock_info = parse_h2_lock_file(lock_path)

    if lock_info is None:
        # Lock file exists but couldn't be read - treat as stale
        log.warning(f"Could not read lock file at {lock_path}, treating as stale")
        return MetalsDbStatus.STALE_LOCK, MetalsLockInfo(
            pid=None,
            port=None,
            lock_path=lock_path,
            is_stale=True,
            raw_content="<unreadable>",
        )

    if lock_info.is_stale:
        log.debug(f"Stale Metals lock detected: {lock_info}")
        return MetalsDbStatus.STALE_LOCK, lock_info
    else:
        log.debug(f"Active Metals instance detected: {lock_info}")
        return MetalsDbStatus.ACTIVE_INSTANCE, lock_info


def cleanup_stale_lock(lock_path: Path) -> bool:
    """
    Remove a stale H2 database lock file.

    This should only be called when we've verified the owning process is dead.
    Removing a lock file from a running process could cause database corruption.

    Args:
        lock_path: Path to the .lock.db file to remove

    Returns:
        True if cleanup succeeded, False otherwise.

    """
    if not lock_path.exists():
        log.debug(f"Lock file already removed: {lock_path}")
        return True

    try:
        lock_path.unlink()
        log.info(f"Cleaned up stale Metals lock file: {lock_path}")
        return True
    except PermissionError as e:
        log.warning(f"Permission denied removing stale lock file {lock_path}: {e}")
        return False
    except OSError as e:
        log.warning(f"Could not remove stale lock file {lock_path}: {e}")
        return False
