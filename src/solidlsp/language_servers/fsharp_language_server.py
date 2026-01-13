"""
Provides F# specific instantiation of the LanguageServer class.
"""

import logging
import os
import pathlib
import shutil
import threading
from pathlib import Path

from overrides import override

from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class FSharpLanguageServer(SolidLanguageServer):
    """
    Provides F# specific instantiation of the LanguageServer class using Ionide LSP (FsAutoComplete).
    Contains various configurations and settings specific to F# development.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates an FSharpLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        custom_command = solidlsp_settings.get_ls_specific_settings(self.get_language_enum_instance()).get(SolidLSPSettings.CustomLSSettings.COMMAND_KEY, None)
        if custom_command:
            cmd = custom_command
        else:
            cmd = self._setup_runtime_dependencies(config, solidlsp_settings)
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=cmd, cwd=repository_root_path),
            "fsharp",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "bin",
            "obj",
            "packages",
            ".paket",
            "paket-files",
            ".fake",
            ".ionide",
        ]

    @classmethod
    def _setup_runtime_dependencies(cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings) -> str:
        """
        Setup runtime dependencies for F# Language Server and return the command to start the server.
        """
        # First check if .NET SDK is installed
        dotnet_exe = shutil.which("dotnet")
        if not dotnet_exe:
            raise RuntimeError(
                ".NET SDK is not installed or not in PATH. Please install .NET SDK 8.0 or later and ensure 'dotnet' is in your PATH."
            )

        # Verify dotnet version
        import subprocess

        try:
            result = subprocess.run([dotnet_exe, "--version"], capture_output=True, text=True, check=True)
            log.info(f"Found .NET SDK version: {result.stdout.strip()}")
        except subprocess.CalledProcessError:
            raise RuntimeError("Failed to get .NET SDK version. Please ensure .NET SDK is properly installed.")

        RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="fsautocomplete",
                    description="FsAutoComplete (Ionide F# Language Server)",
                    command="dotnet tool install --tool-path ./ fsautocomplete",
                    platform_id="any",
                ),
            ]
        )

        # Install FsAutoComplete if not already installed
        fsharp_ls_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), "fsharp-lsp")
        fsautocomplete_path = os.path.join(fsharp_ls_dir, "fsautocomplete")

        # Handle Windows executable extension
        if os.name == "nt":
            fsautocomplete_path += ".exe"

        if not os.path.exists(fsautocomplete_path):
            log.info(f"FsAutoComplete executable not found at {fsautocomplete_path}. Installing...")

            # Ensure the directory exists
            os.makedirs(fsharp_ls_dir, exist_ok=True)

            # Install FsAutoComplete using dotnet tool install
            try:
                import subprocess

                result = subprocess.run(
                    [dotnet_exe, "tool", "install", "--tool-path", fsharp_ls_dir, "fsautocomplete"],
                    cwd=fsharp_ls_dir,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                log.info("FsAutoComplete installed successfully")
                log.debug(f"Installation output: {result.stdout}")
            except subprocess.CalledProcessError as e:
                log.error(f"Failed to install FsAutoComplete: {e.stderr}")
                raise RuntimeError(f"Failed to install FsAutoComplete: {e.stderr}")

        if not os.path.exists(fsautocomplete_path):
            raise FileNotFoundError(
                f"FsAutoComplete executable not found at {fsautocomplete_path}, something went wrong with the installation."
            )

        # FsAutoComplete uses --lsp flag for LSP mode
        return f"{fsautocomplete_path} --adaptive-lsp-server-enabled --project-graph-enabled --use-fcs-transparent-compiler"

    def _get_initialize_params(self) -> InitializeParams:
        """
        Returns the initialize params for the F# Language Server.
        """
        root_uri = pathlib.Path(self.repository_root_path).as_uri()

        initialize_params = {
            "processId": os.getpid(),
            "rootPath": self.repository_root_path,
            "rootUri": root_uri,
            "workspaceFolders": [{"name": "workspace", "uri": root_uri}],
            "capabilities": {
                "workspace": {
                    "applyEdit": True,
                    "workspaceEdit": {"documentChanges": True},
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                    "executeCommand": {"dynamicRegistration": True},
                    "configuration": True,
                    "workspaceFolders": True,
                },
                "textDocument": {
                    "synchronization": {
                        "dynamicRegistration": True,
                        "willSave": True,
                        "willSaveWaitUntil": True,
                        "didSave": True,
                    },
                    "completion": {
                        "dynamicRegistration": True,
                        "contextSupport": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "deprecatedSupport": True,
                        },
                    },
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"],
                    },
                    "signatureHelp": {
                        "dynamicRegistration": True,
                        "signatureInformation": {"documentationFormat": ["markdown", "plaintext"]},
                    },
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentHighlight": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 26))},  # All SymbolKind values
                        "hierarchicalDocumentSymbolSupport": True,
                    },
                    "codeAction": {
                        "dynamicRegistration": True,
                        "codeActionLiteralSupport": {
                            "codeActionKind": {
                                "valueSet": [
                                    "",
                                    "quickfix",
                                    "refactor",
                                    "refactor.extract",
                                    "refactor.inline",
                                    "refactor.rewrite",
                                    "source",
                                    "source.organizeImports",
                                ]
                            }
                        },
                    },
                    "codeLens": {"dynamicRegistration": True},
                    "formatting": {"dynamicRegistration": True},
                    "rangeFormatting": {"dynamicRegistration": True},
                    "onTypeFormatting": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True},
                    "documentLink": {"dynamicRegistration": True},
                    "publishDiagnostics": {
                        "relatedInformation": True,
                        "versionSupport": False,
                        "tagSupport": {"valueSet": [1, 2]},
                    },
                    "implementation": {"dynamicRegistration": True},
                    "typeDefinition": {"dynamicRegistration": True},
                    "colorProvider": {"dynamicRegistration": True},
                    "foldingRange": {
                        "dynamicRegistration": True,
                        "rangeLimit": 5000,
                        "lineFoldingOnly": True,
                    },
                    "declaration": {"dynamicRegistration": True},
                    "selectionRange": {"dynamicRegistration": True},
                },
                "window": {
                    "workDoneProgress": True,
                },
            },
            "initializationOptions": {
                # F# specific initialization options
                "automaticWorkspaceInit": True,
                "abstractClassStubGeneration": True,
                "abstractClassStubGenerationObjectIdentifier": "this",
                "abstractClassStubGenerationMethodBody": 'failwith "Not Implemented"',
                "addFsiWatcher": False,
                "codeLenses": {"signature": {"enabled": True}, "references": {"enabled": True}},
                "disableInMemoryProjectReferences": False,
                "dotNetRoot": self._get_dotnet_root(),
                "enableMSBuildProjectGraph": False,
                "excludeProjectDirectories": ["paket-files"],
                "externalAutocomplete": False,
                "fsac": {"attachDebugger": False, "silencedLogs": [], "conserveMemory": False, "netCoreDllPath": ""},
                "fsiExtraParameters": [],
                "generateBinlog": False,
                "interfaceStubGeneration": True,
                "interfaceStubGenerationObjectIdentifier": "this",
                "interfaceStubGenerationMethodBody": 'failwith "Not Implemented"',
                "keywordsAutocomplete": True,
                "linter": True,
                "pipelineHints": {"enabled": True},
                "recordStubGeneration": True,
                "recordStubGenerationBody": 'failwith "Not Implemented"',
                "resolveNamespaces": True,
                "saveOnlyOpenFiles": False,
                "showProjectExplorerIn": ["ionide", "solution"],
                "simplifyNameAnalyzer": True,
                "smartIndent": False,
                "suggestGitignore": True,
                "suggestSdkScripts": True,
                "unionCaseStubGeneration": True,
                "unionCaseStubGenerationBody": 'failwith "Not Implemented"',
                "unusedDeclarationsAnalyzer": True,
                "unusedOpensAnalyzer": True,
                "verboseLogging": False,
                "workspaceModePeekDeepLevel": 2,
                "workspacePath": self.repository_root_path,
            },
            "trace": "off",
        }

        return initialize_params  # type: ignore

    def _get_dotnet_root(self) -> str:
        """
        Get the .NET root directory.
        """
        dotnet_exe = shutil.which("dotnet")
        if dotnet_exe:
            # Try to get the installation path
            try:
                import subprocess

                result = subprocess.run([dotnet_exe, "--info"], capture_output=True, text=True, check=True)
                lines = result.stdout.split("\n")
                for line in lines:
                    if "Base Path:" in line or "Base path:" in line:
                        base_path = line.split(":", 1)[1].strip()
                        # Get the parent directory (remove 'sdk/version' part)
                        return str(Path(base_path).parent.parent)
            except (subprocess.CalledProcessError, Exception):
                pass

        # Fallback: use the directory containing dotnet executable
        if dotnet_exe:
            return str(Path(dotnet_exe).parent)

        return ""

    def _start_server(self) -> None:
        """
        Start the F# Language Server with custom handlers.
        """

        def handle_window_log_message(params: dict) -> None:
            """Handle window/logMessage from the LSP server."""
            message = params.get("message", "")
            message_type = params.get("type", 1)

            # Map LSP log levels to Python logging levels
            level_map = {1: logging.ERROR, 2: logging.WARNING, 3: logging.INFO, 4: logging.DEBUG}
            level = level_map.get(message_type, logging.INFO)

            log.log(level, f"FsAutoComplete: {message}")

        def handle_window_show_message(params: dict) -> None:
            """Handle window/showMessage from the LSP server."""
            message = params.get("message", "")
            message_type = params.get("type", 1)

            # Map LSP message types to Python logging levels
            level_map = {1: logging.ERROR, 2: logging.WARNING, 3: logging.INFO, 4: logging.DEBUG}
            level = level_map.get(message_type, logging.INFO)

            log.log(level, f"FsAutoComplete Message: {message}")

        def handle_workspace_configuration(params: dict) -> list:
            """Handle workspace/configuration requests from the LSP server."""
            # Return empty configuration for now
            items = params.get("items", [])
            return [None] * len(items)

        def handle_client_register_capability(params: dict) -> None:
            """Handle client/registerCapability requests from the LSP server."""
            # For now, just acknowledge the registration
            return

        def handle_client_unregister_capability(params: dict) -> None:
            """Handle client/unregisterCapability requests from the LSP server."""
            # For now, just acknowledge the unregistration
            return

        def handle_work_done_progress_create(params: dict) -> None:
            """Handle window/workDoneProgress/create requests from the LSP server."""
            # Just acknowledge the request - we don't need to track progress for now
            return

        # Register custom handlers
        self.server.on_notification("window/logMessage", handle_window_log_message)
        self.server.on_notification("window/showMessage", handle_window_show_message)
        self.server.on_request("workspace/configuration", handle_workspace_configuration)
        self.server.on_request("client/registerCapability", handle_client_register_capability)
        self.server.on_request("client/unregisterCapability", handle_client_unregister_capability)
        self.server.on_request("window/workDoneProgress/create", handle_work_done_progress_create)

        log.info("Starting FsAutoComplete F# language server process")

        try:
            self.server.start()
        except Exception as e:
            log.error(f"Failed to start F# language server process: {e}")
            raise SolidLSPException(f"Failed to start F# language server: {e}")

        # Send initialization
        initialize_params = self._get_initialize_params()

        log.info("Sending initialize request to F# language server")
        try:
            self.server.send.initialize(initialize_params)
            log.debug("Received initialize response from F# language server")
        except Exception as e:
            raise SolidLSPException(f"Failed to initialize F# language server for {self.repository_root_path}: {e}") from e

        # Complete initialization
        self.server.notify.initialized({})

        log.info("F# language server initialized successfully")

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        """
        F# projects can be large and may need more time for cross-file analysis.
        """
        return 15.0  # 15 seconds should be sufficient for most F# projects
