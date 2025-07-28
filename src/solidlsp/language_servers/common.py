from __future__ import annotations

import logging
import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import FileUtils, PlatformUtils

logger = logging.getLogger(__name__)

@dataclass(kw_only=True)
class RuntimeDependency:
    """Represents a runtime dependency for a language server."""

    id: str
    platform_id: str | None = None
    url: str | None = None
    archive_type: str | None = None
    binary_name: str | None = None
    command: list[str] | None = None
    command_shell: bool = True
    package_name: str | None = None
    package_version: str | None = None
    extract_path: str | None = None
    description: str | None = None


class RuntimeDependencyCollection:
    """Utility to handle installation of runtime dependencies."""

    def __init__(self, dependencies: Sequence[RuntimeDependency]):
        self._dependencies = list(dependencies)

    def for_platform(self, platform_id: str) -> list[RuntimeDependency]:
        return [d for d in self._dependencies if d.platform_id in (platform_id, "any", "platform-agnostic", None)]

    def for_current_platform(self) -> list[RuntimeDependency]:
        return self.for_platform(PlatformUtils.get_platform_id().value)

    def single_for_current_platform(self) -> RuntimeDependency:
        deps = self.for_current_platform()
        if len(deps) != 1:
            raise RuntimeError(f"Expected exactly one runtime dependency for {PlatformUtils.get_platform_id().value}, found {len(deps)}")
        return deps[0]

    def binary_path(self, target_dir: str) -> str:
        dep = self.single_for_current_platform()
        if not dep.binary_name:
            return target_dir
        return os.path.join(target_dir, dep.binary_name)

    def install(self, logger: LanguageServerLogger, target_dir: str) -> dict[str, str]:
        """Install all dependencies for the current platform into *target_dir*.

        Returns a mapping from dependency id to the resolved binary path.
        """
        os.makedirs(target_dir, exist_ok=True)
        results: dict[str, str] = {}
        for dep in self.for_current_platform():
            if dep.url:
                self._install_from_url(dep, logger, target_dir)
            if dep.command:
                self._run_command(dep, logger, target_dir)
            if dep.binary_name:
                results[dep.id] = os.path.join(target_dir, dep.binary_name)
            else:
                results[dep.id] = target_dir
        return results

    @staticmethod
    def _run_command(dep: RuntimeDependency, logger: LanguageServerLogger, cwd: str) -> None:
        kwargs = {}
        if PlatformUtils.get_platform_id().is_windows():
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore
        else:
            import pwd

            kwargs["user"] = pwd.getpwuid(os.getuid()).pw_name

        logger.log(f"Running command: '{' '.join(dep.command)}' in '{cwd}'", logging.INFO)

        try:
            completed_process = subprocess.run(
                dep.command,
                input="",  # Needed for Claude Code on Windows to avoid hanging
                shell=dep.command_shell,
                capture_output=True,
                check=True,
                cwd=cwd,
                **kwargs,
            )
            if completed_process.returncode != 0:
                logger.log(
                    f"Command '{' '.join(dep.command)}' failed with return code {completed_process.returncode}, stderr: \n{completed_process.stderr.decode()}, stddout: \n{completed_process.stdout.decode()}",
                    logging.WARNING,
                )
                logger.log(f"Command output:\n{completed_process.stdout}", logging.WARNING)
            else:
                logger.log("Command completed successfully", logging.INFO)
        except Exception as e:
            logger.log(f"Failed to run command '{' '.join(dep.command)}': {e}", logging.ERROR)
            raise

    @staticmethod
    def _install_from_url(dep: RuntimeDependency, logger: LanguageServerLogger, target_dir: str) -> None:
        if dep.archive_type == "gz" and dep.binary_name:
            dest = os.path.join(target_dir, dep.binary_name)
            FileUtils.download_and_extract_archive(logger, dep.url, dest, dep.archive_type)
        else:
            FileUtils.download_and_extract_archive(logger, dep.url, target_dir, dep.archive_type or "zip")


class CommandUtils:
    """
    Utility functions for command building.
    """

    @staticmethod
    def get_npm_path() -> str | None:
        """
        Get the path to the npm CLI JavaScript script that can be executed with node.

        Returns:
            Path to npm-cli.js script or None if not found

        """
        if PlatformUtils.get_platform_id().is_windows():
            npm_executable = shutil.which("npm")
            if not npm_executable:
                return None

            npm_path = Path(npm_executable)
            npm_dir = npm_path.parent

            # Look for npm-cli.js in node_modules
            npm_cli_path = npm_dir / "node_modules" / "npm" / "bin" / "npm-cli.js"
            if npm_cli_path.exists():
                return str(npm_cli_path)

            # Alternative location for older versions
            npm_cli_alt_path = npm_dir / "node_modules" / "npm" / "lib" / "cli.js"
            if npm_cli_alt_path.exists():
                return str(npm_cli_alt_path)

            return None

        # For Linux/macOS: use npm config get prefix
        else:
            try:
                result = subprocess.run(
                    "npm config get prefix",
                    shell=True,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    npm_prefix = result.stdout.strip()
                    npm_cli_path = Path(npm_prefix) / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js"
                    if npm_cli_path.exists():
                        return str(npm_cli_path)
            except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
                logger.warning("Failed to run npm config get prefix: %s", e)

            return None
