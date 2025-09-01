"""
Provides Scala specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Scala.
"""

import logging
import os
import pathlib
import re
import shutil
import subprocess
import threading

from overrides import override

from solidlsp import ls_types
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

# Platform-specific imports
if os.name != "nt":  # Unix-like systems
    import pwd
else:
    # Dummy pwd module for Windows
    class pwd:
        @staticmethod
        def getpwuid(uid):
            return type("obj", (), {"pw_name": os.environ.get("USERNAME", "unknown")})()


if not PlatformUtils.get_platform_id().value.startswith("win"):
    pass


class ScalaLanguageServer(SolidLanguageServer):
    """
    Provides Scala specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Scala.
    """

    _metals_compiling: bool
    _is_metals: bool

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        """
        Creates a ScalaLanguageServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        scala_lsp_executable_path = self._setup_runtime_dependencies(logger, config, solidlsp_settings)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=scala_lsp_executable_path, cwd=repository_root_path),
            config.code_language.value,
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()
        self._metals_refs_retry_event = threading.Event()
        self._metals_compiling = False
        self._is_metals = False 
    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            ".bloop",
            ".metals",
            "target",
        ]

    @classmethod
    def _setup_runtime_dependencies(
        cls, logger: LanguageServerLogger, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings
    ) -> list[str]:
        """
        Setup runtime dependencies for Scala Language Server and return the command to start the server.
        """
        assert shutil.which("java") is not None, "JDK is not installed or not in PATH."

        metals_home = os.path.join(cls.ls_resources_dir(solidlsp_settings), "metals-lsp")
        os.makedirs(metals_home, exist_ok=True)
        metals_executable = os.path.join(metals_home, "metals")
        coursier_command_path = shutil.which("coursier")
        cs_command_path = shutil.which("cs")

        if not os.path.exists(metals_executable):
            if not cs_command_path:
                logger.log("'cs' command not found. Trying to install it using 'coursier'.", logging.INFO)
                if not coursier_command_path:
                    raise RuntimeError("'coursier' not found isn't in PATH. Please install coursier try again.")
                try:
                    logger.log("Running 'coursier setup --yes' to install 'cs'...", logging.INFO)
                    subprocess.run([coursier_command_path, "setup", "--yes"], check=True, capture_output=True, text=True)
                except subprocess.CalledProcessError as e:
                    raise RuntimeError(f"Failed to set up 'cs' command with 'coursier setup'. Stderr: {e.stderr}")

                cs_command_path = shutil.which("cs")
                if not cs_command_path:
                    raise RuntimeError(
                        "'cs' command not found after running 'coursier setup'. Please check your PATH or install it manually."
                    )
                logger.log("'cs' command installed successfully.", logging.INFO)

            logger.log(f"metals executable not found at {metals_executable}, bootstrapping...", logging.INFO)
            artifact = "org.scalameta:metals_2.13:1.6.2"
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
            logger.log("Bootstrapping metals...", logging.INFO)
            subprocess.run(cmd, cwd=metals_home, check=True)
            logger.log("Bootstrapping metals finished.", logging.INFO)
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
        }
        return initialize_params

    def _start_server(self):
        """
        Starts the Scala Language Server
        """

        def register_capability_handler(params):
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
                if registration["method"] == "textDocument/completion":
                    self.logger.log("Completion capability registered by server.", logging.INFO)
                    self.completions_available.set()
                if registration["method"] in ["textDocument/documentSymbol", "textDocument/definition"]:
                    self.logger.log(f"Essential capability {registration['method']} registered, server is ready", logging.INFO)
                    self.server_ready.set()
            return

        def execute_client_command_handler(params):
            return []

        def do_nothing(params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)
            msg = (params or {}).get("message", "").lower()
            if "find references" in msg or "references again" in msg:
                self._metals_refs_retry_event.set()


        def window_show_message_request(params):
            """
            Handle window/showMessageRequest from Metals
            """
            self.logger.log(f"LSP: window/showMessageRequest: {params}", logging.INFO)
            message = params.get("message", "")
            actions = params.get("actions", [])

            # Auto-import sbt projects
            if "Import build" in message and actions:
                for action in actions:
                    if action.get("title") == "Import build":
                        self.logger.log("Auto-importing sbt build", logging.INFO)
                        return action

            # Return the first action if available, otherwise None
            if actions:
                return actions[0]
            return None

        def check_experimental_status(params):
            """
            Also Listen for experimental/serverStatus as a backup signal
            """
            if params.get("quiescent") == True:
                self.server_ready.set()
                self.completions_available.set()

        def check_metals_status(params):
            """
            Listen for metals/status notifications
            """
            self.logger.log(f"Received metals/status: {params}", logging.DEBUG)
            if params.get("text") == "Indexing finished":
                self.logger.log("Metals indexing finished, marking as ready", logging.INFO)
                self.server_ready.set()
            text = (params or {}).get("text", "")
            show = bool((params or {}).get("show"))
            hide = bool((params or {}).get("hide"))
            if show and re.search(r"compile", text, re.I):
                self._metals_compiling = True
            if hide and self._metals_compiling:
                self._metals_compiling = False
                self._metals_refs_retry_event.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("window/showMessageRequest", window_show_message_request)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)
        self.server.on_notification("metals/status", check_metals_status)

        self.logger.log("Starting Scala server process", logging.INFO)
        self.server.start()

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )

        initialize_params = self._get_initialize_params(self.repository_root_path)
        self.server.send.initialize(initialize_params)

        self.server.notify.initialized({})
        # scala LS doesn't send a reliable ready signal, assume it's ready immediately
        self.server_ready.set()
        self.completions_available.set()

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 10

    @override
    def request_references(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        """
        Requests references and handles Metals' specific behavior of returning incomplete results
        while background compilation runs. It waits for a signal that compilation is done and
        retries the request to get complete results.
        """
        self._metals_refs_retry_event.clear()

        # Initial request
        references = super().request_references(relative_file_path, line, column)

        # Wait for the retry event, which is set when Metals finishes compilation
        # The timeout is a fallback.
        got_new_references = self._metals_refs_retry_event.wait(timeout=self._get_wait_time_for_cross_file_referencing())

        if got_new_references:
            self.logger.log("Metals compilation finished, re-requesting references.", logging.INFO)
            # Second request to get potentially more complete results
            more_references = super().request_references(relative_file_path, line, column)
            
            # Combine and deduplicate references
            all_references = references + more_references
            unique_references = []
            seen_hashes = set()
            for ref in all_references:
                # Create a stable hashable representation of the location dictionary
                ref_hash = tuple(sorted(ref.items()))
                if ref_hash not in seen_hashes:
                    unique_references.append(ref)
                    seen_hashes.add(ref_hash)
            references = unique_references

        return references
