"""
Provides Scala specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Scala.
"""

import logging
import os
import pathlib
import shutil
import subprocess

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


class ScalaLanguageServer(SolidLanguageServer):
    """
    Provides Scala specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Scala.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a ScalaLanguageServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        scala_lsp_executable_path = self._setup_runtime_dependencies(config, solidlsp_settings)
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=scala_lsp_executable_path, cwd=repository_root_path),
            config.code_language.value,
            solidlsp_settings,
        )

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

        metals_version = "1.6.4"

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
                "-Dmetals.client=Serena",
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
            "capabilities": {
                "textDocument": {
                    "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                    "inlayHint": {"dynamicRegistration": True},
                }
            },
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
