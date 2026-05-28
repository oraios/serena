from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from filelock import FileLock

log = logging.getLogger(__name__)

repo_path = Path(__file__).resolve().parents[2] / "resources" / "repos" / "svelte" / "test_repo"
NODE_MODULES = repo_path / "node_modules"
SVELTE_MARKER = NODE_MODULES / "svelte" / "package.json"
SVELTE_KIT_ADAPTER_MARKER = NODE_MODULES / "@sveltejs" / "adapter-auto" / "package.json"
INSTALL_LOCK = repo_path / ".svelte-install.lock"


@pytest.fixture(scope="session", autouse=True)
def _install_svelte_test_repo_node_modules() -> None:
    """Populate the Svelte fixture's project dependencies via npm."""
    if SVELTE_MARKER.exists() and SVELTE_KIT_ADAPTER_MARKER.exists():
        log.info("Svelte test repo node_modules already populated; skipping npm install")
        return

    npm_executable = shutil.which("npm.cmd") or shutil.which("npm")
    if npm_executable is None:
        pytest.skip("npm is not available; cannot install Svelte test repo dependencies")

    with FileLock(str(INSTALL_LOCK)):
        if SVELTE_MARKER.exists() and SVELTE_KIT_ADAPTER_MARKER.exists():
            log.info("Svelte test repo node_modules populated by another worker; skipping npm install")
            return

        log.warning("Installing npm dependencies into the Svelte test repo at %s.", repo_path)
        proc = subprocess.run(
            [npm_executable, "install"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=False,
            env=os.environ.copy(),
        )
        if proc.returncode != 0:
            log.error("npm install failed (rc=%s).\nstdout:\n%s\nstderr:\n%s", proc.returncode, proc.stdout, proc.stderr)
            pytest.skip(f"npm install failed in {repo_path} (rc={proc.returncode}); see logs for details")

        if not SVELTE_MARKER.exists() or not SVELTE_KIT_ADAPTER_MARKER.exists():
            pytest.skip("npm install completed but required Svelte fixture packages are missing")

        log.info("Svelte test repo node_modules installed successfully")
