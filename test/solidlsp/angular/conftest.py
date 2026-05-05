"""
Pytest fixtures for Angular language server tests.

This conftest is NOT installing the language server itself — that is fully handled
by ``RuntimeDependencyCollection`` inside ``AngularLanguageServer`` and lands in
Serena's managed ``ls_resources_dir`` like every other LS download.

What we install here is the *test fixture project's* npm dependencies (notably
``@angular/core``) into the fixture's own ``node_modules``. ngserver requires
``@angular/core`` to be resolvable from the workspace root or it silently treats
every file as "not in an Angular project", at which point all template-aware
features (definition / hover / references on .html, cross-file template→component
navigation) return empty results — tests would pass vacuously while exercising
nothing. Vendoring ``node_modules`` in-repo is impractical (~500MB), so we run
``npm install`` once per checkout, cached across sessions, and serialised across
xdist workers via ``filelock``.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from filelock import FileLock

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2] / "resources" / "repos" / "angular" / "test_repo"
NODE_MODULES = REPO_ROOT / "node_modules"
ANGULAR_CORE_MARKER = NODE_MODULES / "@angular" / "core" / "package.json"
# Lock file lives inside the repo (covered by its .gitignore) so xdist workers
# can serialise on the install. Putting it elsewhere risks placing it on a
# different filesystem from the install dir, which makes flock semantics fuzzy.
INSTALL_LOCK = REPO_ROOT / ".angular-install.lock"


@pytest.fixture(scope="session", autouse=True)
def _install_angular_test_repo_node_modules() -> None:
    """
    Populate the *test fixture project's* ``node_modules`` (NOT the language server's
    install; see module docstring for the distinction).

    Cached across sessions: once ``node_modules/@angular/core/package.json`` exists,
    this is a no-op. Skipped (with the test session marked) if npm is unavailable.

    Under pytest-xdist multiple workers race on the install. ``npm install`` does
    not internally serialize concurrent runs against the same install dir, so we
    take an exclusive ``filelock`` around the whole install/check sequence — the
    second worker into the lock will then short-circuit on the marker check.
    """
    if ANGULAR_CORE_MARKER.exists():
        log.info("Angular test repo node_modules already populated; skipping npm install")
        return

    if shutil.which("npm") is None:
        pytest.skip("npm is not available; cannot install Angular test repo dependencies")

    with FileLock(str(INSTALL_LOCK)):
        # Re-check inside the lock: a sibling worker may have just installed.
        if ANGULAR_CORE_MARKER.exists():
            log.info("Angular test repo node_modules populated by another worker; skipping npm install")
            return

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
