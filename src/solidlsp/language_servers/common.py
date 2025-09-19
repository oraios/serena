from __future__ import annotations

import logging
import os
import platform
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, cast

from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import FileUtils, PlatformUtils
from solidlsp.util.subprocess_util import subprocess_kwargs

log = logging.getLogger(__name__)


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

    def __init__(self, dependencies: Sequence[RuntimeDependency], overrides: Iterable[Mapping[str, Any]] = ()) -> None:
        """Initialize the collection with a list of dependencies and optional overrides.

        :param dependencies: List of base RuntimeDependency instances. The combination of 'id' and 'platform_id' must be unique.
        :param overrides: List of dictionaries which represent overrides or additions to the base dependencies.
            Each entry must contain at least the 'id' key, and optionally 'platform_id' to uniquely identify the dependency to override.
        """
        self._id_and_platform_id_to_dep: dict[tuple[str, str | None], RuntimeDependency] = {}
        for dep in dependencies:
            dep_key = (dep.id, dep.platform_id)
            if dep_key in self._id_and_platform_id_to_dep:
                raise ValueError(f"Duplicate runtime dependency with id '{dep.id}' and platform_id '{dep.platform_id}':\n{dep}")
            self._id_and_platform_id_to_dep[dep_key] = dep

        for dep_values_override in overrides:
            override_key = cast(tuple[str, str | None], (dep_values_override["id"], dep_values_override.get("platform_id")))
            base_dep = self._id_and_platform_id_to_dep.get(override_key)
            if base_dep is None:
                new_runtime_dep = RuntimeDependency(**dep_values_override)
                self._id_and_platform_id_to_dep[override_key] = new_runtime_dep
            else:
                self._id_and_platform_id_to_dep[override_key] = replace(base_dep, **dep_values_override)

    def get_dependencies_for_platform(self, platform_id: str) -> list[RuntimeDependency]:
        return [d for d in self._id_and_platform_id_to_dep.values() if d.platform_id in (platform_id, "any", "platform-agnostic", None)]

    def get_dependencies_for_current_platform(self) -> list[RuntimeDependency]:
        return self.get_dependencies_for_platform(PlatformUtils.get_platform_id().value)

    def get_single_dep_for_current_platform(self, dependency_id: str | None = None) -> RuntimeDependency:
        deps = self.get_dependencies_for_current_platform()
        if dependency_id is not None:
            deps = [d for d in deps if d.id == dependency_id]
        if len(deps) != 1:
            raise RuntimeError(
                f"Expected exactly one runtime dependency for platform-{PlatformUtils.get_platform_id().value} and {dependency_id=}, found {len(deps)}"
            )
        return deps[0]

    def binary_path(self, target_dir: str) -> str:
        dep = self.get_single_dep_for_current_platform()
        if not dep.binary_name:
            return target_dir
        return os.path.join(target_dir, dep.binary_name)

    def install(self, logger: LanguageServerLogger, target_dir: str) -> dict[str, str]:
        """Install all dependencies for the current platform into *target_dir*.

        Returns a mapping from dependency id to the resolved binary path.
        """
        os.makedirs(target_dir, exist_ok=True)
        results: dict[str, str] = {}
        for dep in self.get_dependencies_for_current_platform():
            if dep.url:
                self._install_from_url(dep, logger, target_dir)
            if dep.command:
                self._run_command(dep.command, target_dir)
            if dep.binary_name:
                results[dep.id] = os.path.join(target_dir, dep.binary_name)
            else:
                results[dep.id] = target_dir
        return results

    @staticmethod
    def _run_command(command: str | list[str], cwd: str) -> None:
        kwargs = subprocess_kwargs()
        if not PlatformUtils.get_platform_id().is_windows():
            import pwd

            kwargs["user"] = pwd.getpwuid(os.getuid()).pw_name

        is_windows = platform.system() == "Windows"
        if not isinstance(command, str) and not is_windows:
            # Since we are using the shell, we need to convert the command list to a single string
            # on Linux/macOS
            command = " ".join(command)

        log.info("Running command %s in '%s'", f"'{command}'" if isinstance(command, str) else command, cwd)

        completed_process = subprocess.run(
            command,
            shell=True,
            check=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **kwargs,
        )
        if completed_process.returncode != 0:
            log.warning("Command '%s' failed with return code %d", command, completed_process.returncode)
            log.warning("Command output:\n%s", completed_process.stdout)
        else:
            log.info(
                "Command completed successfully",
            )

    @staticmethod
    def _install_from_url(dep: RuntimeDependency, logger: LanguageServerLogger, target_dir: str) -> None:
        assert dep.url is not None
        if dep.archive_type == "gz" and dep.binary_name:
            dest = os.path.join(target_dir, dep.binary_name)
            FileUtils.download_and_extract_archive(logger, dep.url, dest, dep.archive_type)
        else:
            FileUtils.download_and_extract_archive(logger, dep.url, target_dir, dep.archive_type or "zip")


def quote_windows_path(path: str) -> str:
    """
    Quote a path for Windows command execution if needed.

    On Windows, paths need to be quoted for proper command execution.
    The function checks if the path is already quoted to avoid double-quoting.
    On other platforms, the path is returned unchanged.

    Args:
        path: The file path to potentially quote

    Returns:
        The quoted path on Windows (if not already quoted), unchanged path on other platforms

    """
    if platform.system() == "Windows":
        # Check if already quoted to avoid double-quoting
        if path.startswith('"') and path.endswith('"'):
            return path
        return f'"{path}"'
    return path
