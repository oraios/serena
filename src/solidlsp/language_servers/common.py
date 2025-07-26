from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass

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
    command: str | None = None
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
        logger.log(f"Running command for {dep.id}: '{dep.command}' in '{cwd}'", logging.INFO)
        try:
            if PlatformUtils.get_platform_id().value.startswith("win"):
                subprocess.run(
                    dep.command,
                    shell=True,
                    check=True,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                )
            else:
                import pwd

                user = pwd.getpwuid(os.getuid()).pw_name
                subprocess.run(
                    dep.command,
                    shell=True,
                    check=True,
                    user=user,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                )
            logger.log(f"Successfully ran command for {dep.id}.", logging.INFO)
        except subprocess.CalledProcessError as e:
            logger.log(f"Error running command for {dep.id}: {e}", logging.ERROR)
            logger.log(f"Stderr: {e.stderr}", logging.ERROR)
            logger.log(f"Stdout: {e.stdout}", logging.ERROR)
            raise

    @staticmethod
    def _install_from_url(dep: RuntimeDependency, logger: LanguageServerLogger, target_dir: str) -> None:
        if dep.archive_type == "gz" and dep.binary_name:
            dest = os.path.join(target_dir, dep.binary_name)
            FileUtils.download_and_extract_archive(logger, dep.url, dest, dep.archive_type)
        else:
            FileUtils.download_and_extract_archive(logger, dep.url, target_dir, dep.archive_type or "zip")
