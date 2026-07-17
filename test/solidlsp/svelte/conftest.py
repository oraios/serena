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
PACKAGE_LOCK = repo_path / "package-lock.json"
SVELTE_MARKER = NODE_MODULES / "svelte" / "package.json"
SVELTE_KIT_ADAPTER_MARKER = NODE_MODULES / "@sveltejs" / "adapter-auto" / "package.json"
SVELTE_KIT_TSCONFIG = repo_path / ".svelte-kit" / "tsconfig.json"
INSTALL_LOCK = repo_path / ".svelte-install.lock"


def _fixture_ready() -> bool:
    return SVELTE_MARKER.exists() and SVELTE_KIT_ADAPTER_MARKER.exists() and SVELTE_KIT_TSCONFIG.exists()


def _run_svelte_kit_sync(npm_executable: str) -> None:
    """Generate .svelte-kit (notably its tsconfig.json carrying the $lib path aliases), failing loudly on error.

    The fixture's own ``prepare`` script masks sync failures (``svelte-kit sync || echo ''``); a missing
    ``.svelte-kit/tsconfig.json`` leaves the fixture tsconfig's ``extends`` dangling, tsserver silently loses
    the ``$lib`` path aliases, and cross-file tests fail with partial results that look like LS flakes.
    """
    sync = subprocess.run(
        [npm_executable, "exec", "--", "svelte-kit", "sync"],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        check=False,
        env=os.environ.copy(),
    )
    if sync.returncode != 0 or not SVELTE_KIT_TSCONFIG.exists():
        pytest.fail(
            f"svelte-kit sync failed (rc={sync.returncode}) or did not produce {SVELTE_KIT_TSCONFIG}; "
            "without it the $lib path aliases do not resolve and cross-file svelte tests fail with partial results.\n"
            "Known cause: npm silently skipping platform-specific optional dependencies (npm/cli#4828), which "
            "leaves rolldown without its native binding; remedy: remove node_modules and reinstall.\n"
            f"stdout:\n{sync.stdout}\nstderr:\n{sync.stderr}"
        )
    log.info("svelte-kit sync succeeded; %s is present", SVELTE_KIT_TSCONFIG)


@pytest.fixture(scope="session", autouse=True)
def _install_svelte_test_repo_node_modules() -> None:
    """Populate the Svelte fixture's project dependencies via npm and generate .svelte-kit."""
    if _fixture_ready():
        log.info("Svelte test repo node_modules and .svelte-kit already populated; skipping npm install")
        return

    npm_executable = shutil.which("npm.cmd") or shutil.which("npm")
    if npm_executable is None:
        pytest.skip("npm is not available; cannot install Svelte test repo dependencies")

    if not PACKAGE_LOCK.exists():
        pytest.fail(f"Svelte fixture lockfile is missing: {PACKAGE_LOCK}. Regenerate it before running npm ci.")

    with FileLock(str(INSTALL_LOCK)):
        if _fixture_ready():
            log.info("Svelte test repo dependencies populated by another worker; skipping npm install")
            return

        if not SVELTE_MARKER.exists() or not SVELTE_KIT_ADAPTER_MARKER.exists():
            log.warning("Installing npm dependencies into the Svelte test repo at %s with npm ci.", repo_path)
            proc = subprocess.run(
                [npm_executable, "ci"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=False,
                env=os.environ.copy(),
            )
            if proc.returncode != 0:
                log.error("npm ci failed (rc=%s).\nstdout:\n%s\nstderr:\n%s", proc.returncode, proc.stdout, proc.stderr)
                pytest.skip(f"npm ci failed in {repo_path} (rc={proc.returncode}); see logs for details")

            if not SVELTE_MARKER.exists() or not SVELTE_KIT_ADAPTER_MARKER.exists():
                pytest.skip("npm ci completed but required Svelte fixture packages are missing")

            log.info("Svelte test repo node_modules installed successfully")

        _run_svelte_kit_sync(npm_executable)
