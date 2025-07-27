from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import FileUtils, PlatformUtils


@dataclass(kw_only=True)
class RuntimeDependency:
    """Represents a runtime dependency for a language server."""

    id: str
    platform_id: str | None = None
    url: str | None = None
    archive_type: str | None = None
    binary_name: str | None = None
    command: str | list[str] | None = None
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
                self._run_command(dep.command, logger, target_dir)
            if dep.binary_name:
                results[dep.id] = os.path.join(target_dir, dep.binary_name)
            else:
                results[dep.id] = target_dir
        return results

    @staticmethod
    def _run_command(command: str | list[str], logger: LanguageServerLogger, cwd: str) -> None:

        is_windows = PlatformUtils.get_platform_id().value.startswith("win")
        if isinstance(command, list):
            command_parts = command
        else:
            command_parts = shlex.split(command, posix=not is_windows)

        logger.log(f"Running command parts: {command_parts}", logging.INFO)

        if is_windows:
            process = subprocess.Popen(
                command_parts,
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=os.environ.copy(),
                cwd=cwd,
            )
            process.wait(60)
            process.communicate()
            if process.returncode != 0:
                logger.log(
                    f"Command '{command}' failed with return code {process.returncode} in '{cwd}', stderr: {process.stderr.read().decode()}, stdout: {process.stdout.read().decode()}",
                    logging.ERROR
                )
        else:
            import pwd

            user = pwd.getpwuid(os.getuid()).pw_name
            subprocess.run(
                command_parts,
                check=True,
                user=user,
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        logger.log(f"Command '{command}' executed successfully in '{cwd}'", logging.INFO)

    @staticmethod
    def _install_from_url(dep: RuntimeDependency, logger: LanguageServerLogger, target_dir: str) -> None:
        if dep.archive_type == "gz" and dep.binary_name:
            dest = os.path.join(target_dir, dep.binary_name)
            FileUtils.download_and_extract_archive(logger, dep.url, dest, dep.archive_type)
        else:
            FileUtils.download_and_extract_archive(logger, dep.url, target_dir, dep.archive_type or "zip")


class NodeJsUtils:
    """
    Utility functions for Node.js executable resolution across all operating systems.
    """

    @staticmethod
    def find_node_executable() -> str | None:
        """
        Find the path to the node executable.
        Returns the full path to node executable or None if not found.
        """
        return shutil.which("node")

    @staticmethod
    def find_npm_executable() -> str | None:
        """
        Find the path to the npm executable.
        Returns the full path to npm executable or None if not found.
        """
        return shutil.which("npm")

    @staticmethod
    def get_npm_cli_script_path() -> str | None:
        """
        Get the path to the npm CLI JavaScript script that can be executed with node.
        Uses npm executable location to find the corresponding npm-cli.js script.

        Returns:
            Path to npm-cli.js script or None if not found

        """
        npm_executable = NodeJsUtils.find_npm_executable()
        if not npm_executable:
            return None

        npm_path = Path(npm_executable)
        npm_dir = npm_path.parent

        # Look for node_modules in the same directory as npm executable
        npm_cli_path = npm_dir / "node_modules" / "npm" / "bin" / "npm-cli.js"
        if npm_cli_path.exists():
            return str(npm_cli_path)

        # Alternative location for older versions
        npm_cli_alt_path = npm_dir / "node_modules" / "npm" / "lib" / "cli.js"
        if npm_cli_alt_path.exists():
            return str(npm_cli_alt_path)

        return None

    @staticmethod
    def build_node_command(node_executable: str, script_path: str, args: list[str] | None = None) -> list[str]:
        """
        Build a command list for executing a Node.js script directly with node.
        Returns a list that can be used with subprocess.run().

        Args:
            node_executable: Path to the node executable
            script_path: Path to the JavaScript file to execute
            args: Additional arguments to pass to the script

        """
        command = [node_executable, script_path]
        if args:
            command.extend(args)
        return command

    @staticmethod
    def build_npm_install_command(install_args: list[str]) -> list[str] | None:
        """
        Build a command for npm install using direct node execution.

        Args:
            install_args: Arguments for npm install (e.g., ["install", "--prefix", "./", "package@version"])

        Returns:
            Complete command list for direct execution, or None if node/npm not found

        """
        node_executable = NodeJsUtils.find_node_executable()
        npm_cli_script = NodeJsUtils.get_npm_cli_script_path()

        if not node_executable or not npm_cli_script:
            return None

        return NodeJsUtils.build_node_command(node_executable, npm_cli_script, install_args)
