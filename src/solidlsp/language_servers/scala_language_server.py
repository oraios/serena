"""
Provides Scala specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Scala.
"""

import logging
import os
import pathlib
import shutil
import subprocess
from enum import Enum

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_utils import PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

if not PlatformUtils.get_platform_id().value.startswith("win"):
    pass


log = logging.getLogger(__name__)

# Default configuration constants
DEFAULT_METALS_VERSION = "1.6.4"
DEFAULT_CLIENT_NAME = "Serena"
DEFAULT_ON_STALE_LOCK = "auto-clean"
DEFAULT_LOG_MULTI_INSTANCE_NOTICE = True


class StaleLockMode(Enum):
    """Mode for handling stale Metals H2 database locks."""

    AUTO_CLEAN = "auto-clean"
    """Automatically remove stale lock files (default, recommended)."""

    WARN = "warn"
    """Log a warning but proceed; may result in degraded experience."""

    FAIL = "fail"
    """Raise an error and refuse to start."""


def _get_scala_settings(solidlsp_settings: SolidLSPSettings) -> dict[str, object]:
    """
    Extract Scala-specific settings with defaults applied.

    Returns a dictionary with keys:
        - metals_version: str
        - client_name: str
        - on_stale_lock: StaleLockMode
        - log_multi_instance_notice: bool
    """
    from solidlsp.ls_config import Language

    defaults: dict[str, object] = {
        "metals_version": DEFAULT_METALS_VERSION,
        "client_name": DEFAULT_CLIENT_NAME,
        "on_stale_lock": StaleLockMode.AUTO_CLEAN,
        "log_multi_instance_notice": DEFAULT_LOG_MULTI_INSTANCE_NOTICE,
    }

    if not solidlsp_settings.ls_specific_settings:
        return defaults

    scala_settings = solidlsp_settings.get_ls_specific_settings(Language.SCALA)

    # Parse stale lock mode with validation
    on_stale_lock_str = scala_settings.get("on_stale_lock", DEFAULT_ON_STALE_LOCK)
    try:
        on_stale_lock = StaleLockMode(on_stale_lock_str)
    except ValueError:
        log.warning(f"Invalid on_stale_lock value '{on_stale_lock_str}', using '{DEFAULT_ON_STALE_LOCK}'")
        on_stale_lock = StaleLockMode.AUTO_CLEAN

    return {
        "metals_version": scala_settings.get("metals_version", DEFAULT_METALS_VERSION),
        "client_name": scala_settings.get("client_name", DEFAULT_CLIENT_NAME),
        "on_stale_lock": on_stale_lock,
        "log_multi_instance_notice": scala_settings.get("log_multi_instance_notice", DEFAULT_LOG_MULTI_INSTANCE_NOTICE),
    }


class ScalaLanguageServer(SolidLanguageServer):
    """
    Provides Scala specific instantiation of the LanguageServer class.
    Contains various configurations and settings specific to Scala.

    Configurable options in ls_specific_settings (in serena_config.yml):

        ls_specific_settings:
          scala:
            # Stale lock handling: auto-clean | warn | fail
            on_stale_lock: 'auto-clean'
            # Log notice when another Metals instance is detected
            log_multi_instance_notice: true
            # Metals version to bootstrap (default: DEFAULT_METALS_VERSION)
            metals_version: '1.6.4'
            # Client identifier sent to Metals (default: DEFAULT_CLIENT_NAME)
            client_name: 'Serena'

    Multi-instance support:
        Metals uses H2 AUTO_SERVER mode (enabled by default) to support multiple
        concurrent instances sharing the same database. Running Serena's Metals
        alongside VS Code's Metals is designed to work. The only issue is stale
        locks from crashed processes, which this class can detect and clean up.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a ScalaLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        # Check for stale locks before setting up dependencies (fail-fast)
        self._check_metals_db_status(repository_root_path, solidlsp_settings)

        scala_lsp_executable_path = self._setup_runtime_dependencies(config, solidlsp_settings)
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=scala_lsp_executable_path, cwd=repository_root_path),
            config.code_language.value,
            solidlsp_settings,
        )

    def _check_metals_db_status(self, repository_root_path: str, solidlsp_settings: SolidLSPSettings) -> None:
        """
        Check the Metals H2 database status and handle stale locks.

        This method is called before setting up runtime dependencies to fail-fast
        if there's a stale lock that the user has configured to fail on.
        """
        from pathlib import Path

        from solidlsp.ls_exceptions import MetalsStaleLockError
        from solidlsp.util.metals_db_utils import (
            MetalsDbStatus,
            check_metals_db_status,
            cleanup_stale_lock,
        )

        project_path = Path(repository_root_path)
        status, lock_info = check_metals_db_status(project_path)

        # Get settings using the shared helper function
        settings = _get_scala_settings(solidlsp_settings)
        on_stale_lock: StaleLockMode = settings["on_stale_lock"]  # type: ignore[assignment]
        log_multi_instance_notice: bool = settings["log_multi_instance_notice"]  # type: ignore[assignment]

        if status == MetalsDbStatus.ACTIVE_INSTANCE:
            if log_multi_instance_notice and lock_info:
                log.info(
                    f"Another Metals instance detected (PID: {lock_info.pid}). "
                    "This is fine - Metals supports multiple instances via H2 AUTO_SERVER. "
                    "Both instances will share the database and Bloop build server."
                )

        elif status == MetalsDbStatus.STALE_LOCK:
            lock_path = lock_info.lock_path if lock_info else project_path / ".metals" / "metals.mv.db.lock.db"
            lock_path_str = str(lock_path)

            if on_stale_lock == StaleLockMode.AUTO_CLEAN:
                log.info(f"Stale Metals lock detected, cleaning up: {lock_path_str}")
                cleanup_success = cleanup_stale_lock(lock_path)
                if not cleanup_success:
                    log.warning(
                        f"Failed to clean up stale lock at {lock_path_str}. "
                        "Metals may fall back to in-memory database (degraded experience)."
                    )

            elif on_stale_lock == StaleLockMode.WARN:
                log.warning(
                    f"Stale Metals lock detected at {lock_path_str}. "
                    "A previous Metals process may have crashed. "
                    "Metals will fall back to in-memory database (degraded experience). "
                    "Consider removing the lock file manually or setting on_stale_lock='auto-clean'."
                )

            elif on_stale_lock == StaleLockMode.FAIL:
                raise MetalsStaleLockError(lock_path_str)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            ".bloop",
            ".metals",
            "target",
        ]

    @classmethod
    def _setup_runtime_dependencies(cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings) -> list[str]:
        """
        Setup runtime dependencies for Scala Language Server and return the command to start the server.
        """
        assert shutil.which("java") is not None, "JDK is not installed or not in PATH."

        # Get settings using the shared helper function
        settings = _get_scala_settings(solidlsp_settings)
        metals_version: str = settings["metals_version"]  # type: ignore[assignment]
        client_name: str = settings["client_name"]  # type: ignore[assignment]

        metals_home = os.path.join(cls.ls_resources_dir(solidlsp_settings), "metals-lsp")
        os.makedirs(metals_home, exist_ok=True)
        metals_executable = os.path.join(metals_home, metals_version, "metals")
        coursier_command_path = shutil.which("coursier")
        cs_command_path = shutil.which("cs")
        assert cs_command_path is not None or coursier_command_path is not None, "coursier is not installed or not in PATH."

        if not os.path.exists(metals_executable):
            if not cs_command_path:
                assert coursier_command_path is not None
                log.info("'cs' command not found. Trying to install it using 'coursier'.")
                try:
                    log.info("Running 'coursier setup --yes' to install 'cs'...")
                    subprocess.run([coursier_command_path, "setup", "--yes"], check=True, capture_output=True, text=True)
                except subprocess.CalledProcessError as e:
                    raise RuntimeError(f"Failed to set up 'cs' command with 'coursier setup'. Stderr: {e.stderr}")

                cs_command_path = shutil.which("cs")
                if not cs_command_path:
                    raise RuntimeError(
                        "'cs' command not found after running 'coursier setup'. Please check your PATH or install it manually."
                    )
                log.info("'cs' command installed successfully.")

            log.info(f"metals executable not found at {metals_executable}, bootstrapping...")
            subprocess.run(["mkdir", "-p", os.path.join(metals_home, metals_version)], check=True)
            artifact = f"org.scalameta:metals_2.13:{metals_version}"
            cmd = [
                cs_command_path,
                "bootstrap",
                "--java-opt",
                "-XX:+UseG1GC",
                "--java-opt",
                "-XX:+UseStringDeduplication",
                "--java-opt",
                "-Xss4m",
                "--java-opt",
                "-Xms100m",
                "--java-opt",
                f"-Dmetals.client={client_name}",
                artifact,
                "-o",
                metals_executable,
                "-f",
            ]
            log.info("Bootstrapping metals...")
            subprocess.run(cmd, cwd=metals_home, check=True)
            log.info("Bootstrapping metals finished.")
        return [metals_executable]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Scala Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "initializationOptions": {
                "compilerOptions": {
                    "completionCommand": None,
                    "isCompletionItemDetailEnabled": True,
                    "isCompletionItemDocumentationEnabled": True,
                    "isCompletionItemResolve": True,
                    "isHoverDocumentationEnabled": True,
                    "isSignatureHelpDocumentationEnabled": True,
                    "overrideDefFormat": "ascli",
                    "snippetAutoIndent": False,
                },
                "debuggingProvider": True,
                "decorationProvider": False,
                "didFocusProvider": False,
                "doctorProvider": False,
                "executeClientCommandProvider": False,
                "globSyntax": "uri",
                "icons": "unicode",
                "inputBoxProvider": False,
                "isVirtualDocumentSupported": False,
                "isExitOnShutdown": True,
                "isHttpEnabled": True,
                "openFilesOnRenameProvider": False,
                "quickPickProvider": False,
                "renameFileThreshold": 200,
                "statusBarProvider": "false",
                "treeViewProvider": False,
                "testExplorerProvider": False,
                "openNewWindowProvider": False,
                "copyWorksheetOutputProvider": False,
                "doctorVisibilityProvider": False,
            },
            "capabilities": {"textDocument": {"documentSymbol": {"hierarchicalDocumentSymbolSupport": True}}},
        }
        return initialize_params  # type: ignore

    def _start_server(self) -> None:
        """
        Starts the Scala Language Server
        """
        log.info("Starting Scala server process")
        self.server.start()

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")

        initialize_params = self._get_initialize_params(self.repository_root_path)
        self.server.send.initialize(initialize_params)
        self.server.notify.initialized({})

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 5
