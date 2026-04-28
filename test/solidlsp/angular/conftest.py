"""
Pytest fixtures for Angular language server tests.

The Angular Language Server requires the project under test to have its
``node_modules`` populated (specifically ``@angular/core``) — otherwise ngserver
reports every file as "not in an Angular project" and template features return
empty. This conftest installs the test fixture's npm dependencies once per
session (cached in the test repo's ``node_modules``) before any Angular test
runs.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

import pytest

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2] / "resources" / "repos" / "angular" / "test_repo"
NODE_MODULES = REPO_ROOT / "node_modules"
ANGULAR_CORE_MARKER = NODE_MODULES / "@angular" / "core" / "package.json"


@pytest.fixture(scope="session", autouse=True)
def _install_angular_test_repo_node_modules() -> None:
    """
    Install npm dependencies into the Angular test repo if not already present.

    Cached across sessions: once ``node_modules/@angular/core/package.json`` exists,
    this is a no-op. Skipped (with the test session marked) if npm is unavailable.

    Note: under pytest-xdist multiple workers may race on the install; the
    committed ``package-lock.json`` makes concurrent ``npm install`` runs
    deterministic and safe to retry, and the marker check above short-circuits
    once one worker has finished.
    """
    if ANGULAR_CORE_MARKER.exists():
        log.info("Angular test repo node_modules already populated; skipping npm install")
        return

    if shutil.which("npm") is None:
        pytest.skip("npm is not available; cannot install Angular test repo dependencies")

    log.warning(
        "Installing npm dependencies into the Angular test repo at %s. This is a one-time cost per checkout and may take ~30s.",
        REPO_ROOT,
    )

    proc = subprocess.run(
        ["npm", "install", "--no-audit", "--no-fund", "--loglevel=warn"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=os.environ.copy(),
    )
    if proc.returncode != 0:
        log.error("npm install failed (rc=%s).\nstdout:\n%s\nstderr:\n%s", proc.returncode, proc.stdout, proc.stderr)
        pytest.skip(f"npm install failed in {REPO_ROOT} (rc={proc.returncode}); see logs for details")

    if not ANGULAR_CORE_MARKER.exists():
        pytest.skip(f"npm install completed but {ANGULAR_CORE_MARKER} is missing; cannot run Angular tests")

    log.info("Angular test repo node_modules installed successfully")
