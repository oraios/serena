"""
Provides PHP specific instantiation of the LanguageServer class using Devsense.
"""

import logging
import os
import shutil
import subprocess

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection


class DevsensePHP(SolidLanguageServer):
    """
    Provides PHP specific instantiation of the LanguageServer class using Devsense.

    Devsense is a fast PHP language server providing advanced static analysis,
    as an alternative to Intelephense.

    You can pass the following entries in ls_specific_settings["php"]:
        - maxMemory
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For PHP projects, we should ignore:
        # - vendor: third-party dependencies managed by Composer
        # - node_modules: if the project has JavaScript components
        # - cache: commonly used for caching
        return super().is_ignored_dirname(dirname) or dirname in ["node_modules", "vendor", "cache"]

    @classmethod
    def _setup_runtime_dependencies(cls, logger: LanguageServerLogger, solidlsp_settings: SolidLSPSettings) -> list[str]:
        """
        Setup runtime dependencies for Devsense and return the command to start the server.
        """
        platform_id = PlatformUtils.get_platform_id()

        valid_platforms = [
            PlatformId.LINUX_x64,
            PlatformId.LINUX_arm64,
            PlatformId.OSX,
            PlatformId.OSX_x64,
            PlatformId.OSX_arm64,
            PlatformId.WIN_x64,
            PlatformId.WIN_arm64,
        ]
        assert platform_id in valid_platforms, f"Platform {platform_id} is not supported for Devsense PHP at the moment"

        # Verify PHP is installed
        is_php_installed = shutil.which("php") is not None
        assert is_php_installed, "php is not installed or isn't in PATH. Please install PHP and try again."

        # Get PHP version
        try:
            result = subprocess.run(["php", "--version"], capture_output=True, text=True, check=True)
            php_version = result.stdout.split("\n")[0]
            logger.log(f"PHP version: {php_version}", logging.INFO)
        except subprocess.CalledProcessError as e:
            logger.log(f"Warning: Could not determine PHP version: {e}", logging.WARNING)

        # Setup Devsense PHP Language Server
        devsense_ls_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), "devsense-php")
        os.makedirs(devsense_ls_dir, exist_ok=True)

        # Determine Devsense binary based on platform
        platform_bin_map = {
            PlatformId.LINUX_x64: "linux-x64/devsense",
            PlatformId.LINUX_arm64: "linux-arm64/devsense",
            PlatformId.WIN_x64: "win-x64/devsense.exe",
            PlatformId.WIN_arm64: "win-arm64/devsense.exe",
            PlatformId.OSX_x64: "osx-x64/devsense",
            PlatformId.OSX_arm64: "osx-arm64/devsense",
            PlatformId.OSX: "osx-x64/devsense",  # Fallback for generic OSX
        }

        rel_binary_path = platform_bin_map.get(platform_id)
        if not rel_binary_path:
            raise RuntimeError(f"Devsense binary not available for platform {platform_id}")

        devsense_executable_path = os.path.join(devsense_ls_dir, rel_binary_path)

        # Download/install Devsense if not already present
        if not os.path.exists(devsense_executable_path):
            logger.log("Devsense binary not found, attempting to download...", logging.INFO)
            # Use Composer to install Devsense
            deps = RuntimeDependencyCollection(
                [
                    RuntimeDependency(
                        id="devsense",
                        command="composer global require devsense/devsense-cli",
                        platform_id="any",
                    )
                ]
            )
            try:
                deps.install(logger, devsense_ls_dir)
            except Exception as e:
                logger.log(
                    f"Warning: Failed to install Devsense via Composer: {e}. "
                    "Please ensure Composer is installed and run 'composer global require devsense/devsense-cli'",
                    logging.WARNING,
                )

        # Make binary executable on Unix-like systems
        if not platform_id.is_windows():
            os.chmod(devsense_executable_path, 0o755)

        if not os.path.exists(devsense_executable_path):
            raise RuntimeError(
                f"Devsense executable not found at {devsense_executable_path}. "
                "Please install Devsense manually via Composer: 'composer global require devsense/devsense-cli'"
            )

        return [devsense_executable_path, "server", "--stdio"]

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        # Setup runtime dependencies before initializing
        devsense_cmd = self._setup_runtime_dependencies(logger, solidlsp_settings)

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=devsense_cmd, cwd=repository_root_path),
            "php",
            solidlsp_settings,
        )
        # Override internal language enum for file matching
        from solidlsp.ls_config import Language

        self.language = Language.PHP_DEVSENSE
