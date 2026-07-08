"""
Pytest fixtures for Astro language server tests.

This conftest does NOT install the language server itself -- that is handled by
``RuntimeDependencyCollection`` inside ``AstroLanguageServer`` and lands in Serena's
managed ``ls_resources_dir`` like every other LS download.

What we install here is the *test fixture project's* npm dependencies (notably
``astro``) into the fixture's own ``node_modules``. The companion tsserver (via
``@astrojs/ts-plugin``) needs ``astro`` resolvable from the workspace to understand
``.astro`` modules; without it, cross-file references between ``.ts`` and ``.astro``
files return nothing and the tests would pass vacuously. Vendoring ``node_modules``
in-repo is impractical, so we run ``npm install`` once per checkout, cached across
sessions, and serialised across xdist workers via ``filelock``.
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

REPO_ROOT = Path(__file__).resolve().parents[2] / "resources" / "repos" / "astro" / "test_repo"
NODE_MODULES = REPO_ROOT / "node_modules"
ASTRO_MARKER = NODE_MODULES / "astro" / "package.json"
# Lock file lives inside the repo (covered by its .gitignore) so xdist workers can
# serialise on the install.
INSTALL_LOCK = REPO_ROOT / ".astro-install.lock"


@pytest.fixture(scope="session", autouse=True)
def _install_astro_test_repo_node_modules() -> None:
    """Populate the Astro fixture's project dependencies via npm (cached across sessions)."""
    if ASTRO_MARKER.exists():
        log.info("Astro test repo node_modules already populated; skipping npm install")
        return

    npm_executable = shutil.which("npm.cmd") or shutil.which("npm")
    if npm_executable is None:
        pytest.skip("npm is not available; cannot install Astro test repo dependencies")

    with FileLock(str(INSTALL_LOCK)):
        # Re-check inside the lock: a sibling worker may have just installed.
        if ASTRO_MARKER.exists():
            log.info("Astro test repo node_modules populated by another worker; skipping npm install")
            return

        log.warning(
            "Installing npm dependencies into the Astro test repo at %s. This is a one-time cost per checkout.",
            REPO_ROOT,
        )
        proc = subprocess.run(
            [npm_executable, "install", "--no-audit", "--no-fund", "--loglevel=warn"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
            env=os.environ.copy(),
        )
        if proc.returncode != 0:
            log.error("npm install failed (rc=%s).\nstdout:\n%s\nstderr:\n%s", proc.returncode, proc.stdout, proc.stderr)
            pytest.skip(f"npm install failed in {REPO_ROOT} (rc={proc.returncode}); see logs for details")

        if not ASTRO_MARKER.exists():
            pytest.skip(f"npm install completed but {ASTRO_MARKER} is missing; cannot run Astro tests")

        log.info("Astro test repo node_modules installed successfully")
