"""
Provides Pascal/Free Pascal specific instantiation of the LanguageServer class using pasls.
Contains various configurations and settings specific to Pascal and Free Pascal.

pasls installation strategy:
1. Use existing pasls from PATH
2. Download prebuilt binary from GitHub releases

Supported platforms for binary download:
- linux-x64, linux-arm64
- osx-x64, osx-arm64
- win-x64

You can pass the following entries in ls_specific_settings["pascal"]:
- (reserved for future use)
"""

import logging
import os
import pathlib
import shutil
import threading

from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection, quote_windows_path
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class PascalLanguageServer(SolidLanguageServer):
    """
    Provides Pascal specific instantiation of the LanguageServer class using pasls.
    Contains various configurations and settings specific to Free Pascal and Lazarus.
    """

    PASLS_VERSION = "0.1.0"
    PASLS_RELEASES_URL = "https://github.com/zen010101/pascal-language-server/releases/download"

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a PascalLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        custom_command = solidlsp_settings.get_ls_specific_settings(self.get_language_enum_instance()).get("command", None)
        if custom_command:
            cmd = custom_command
        else:
            cmd = self._setup_runtime_dependencies(solidlsp_settings)
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=cmd, cwd=repository_root_path),
            "pascal",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.completions_available_event = threading.Event()

    @classmethod
    def _setup_runtime_dependencies(cls, solidlsp_settings: SolidLSPSettings) -> str:
        """
        Setup runtime dependencies for Pascal Language Server (pasls).

        Returns:
            str: The command to start the pasls server

        """
        # Check if pasls is already in PATH
        pasls_in_path = shutil.which("pasls")
        if pasls_in_path:
            log.info(f"Found pasls in PATH: {pasls_in_path}")
            return quote_windows_path(pasls_in_path)

        # Use RuntimeDependencyCollection for download
        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="PascalLanguageServer",
                    description="Pascal Language Server for Linux (x64)",
                    url=f"{cls.PASLS_RELEASES_URL}/v{cls.PASLS_VERSION}/pasls-linux-x64.tar.gz",
                    platform_id="linux-x64",
                    archive_type="gztar",
                    binary_name="pasls",
                ),
                RuntimeDependency(
                    id="PascalLanguageServer",
                    description="Pascal Language Server for Linux (arm64)",
                    url=f"{cls.PASLS_RELEASES_URL}/v{cls.PASLS_VERSION}/pasls-linux-arm64.tar.gz",
                    platform_id="linux-arm64",
                    archive_type="gztar",
                    binary_name="pasls",
                ),
                RuntimeDependency(
                    id="PascalLanguageServer",
                    description="Pascal Language Server for macOS (x64)",
                    url=f"{cls.PASLS_RELEASES_URL}/v{cls.PASLS_VERSION}/pasls-darwin-x64.tar.gz",
                    platform_id="osx-x64",
                    archive_type="gztar",
                    binary_name="pasls",
                ),
                RuntimeDependency(
                    id="PascalLanguageServer",
                    description="Pascal Language Server for macOS (arm64)",
                    url=f"{cls.PASLS_RELEASES_URL}/v{cls.PASLS_VERSION}/pasls-darwin-arm64.tar.gz",
                    platform_id="osx-arm64",
                    archive_type="gztar",
                    binary_name="pasls",
                ),
                RuntimeDependency(
                    id="PascalLanguageServer",
                    description="Pascal Language Server for Windows (x64)",
                    url=f"{cls.PASLS_RELEASES_URL}/v{cls.PASLS_VERSION}/pasls-win32-x64.zip",
                    platform_id="win-x64",
                    archive_type="zip",
                    binary_name="pasls.exe",
                ),
            ]
        )

        pasls_dir = cls.ls_resources_dir(solidlsp_settings)
        pasls_executable_path = deps.binary_path(pasls_dir)

        if not os.path.exists(pasls_executable_path):
            log.info(f"Downloading pasls to {pasls_dir}...")
            deps.install(pasls_dir)

        assert os.path.exists(pasls_executable_path), f"pasls executable not found at {pasls_executable_path}"
        os.chmod(pasls_executable_path, 0o755)
        log.info(f"Using pasls at: {pasls_executable_path}")

        return quote_windows_path(pasls_executable_path)

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Pascal Language Server.

        pasls (genericptr/pascal-language-server) reads compiler paths from:
        1. Environment variables (PP, FPCDIR, LAZARUSDIR) via TCodeToolsOptions.InitWithEnvironmentVariables
        2. Lazarus config files via GuessCodeToolConfig

        We only pass target OS/CPU in initializationOptions if explicitly set.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()

        # Build initializationOptions from environment variables
        # pasls reads these to configure CodeTools:
        # - PP: Path to FPC compiler executable
        # - FPCDIR: Path to FPC source directory
        # - LAZARUSDIR: Path to Lazarus directory (only needed for LCL projects)
        # - FPCTARGET: Target OS
        # - FPCTARGETCPU: Target CPU
        initialization_options: dict = {}

        env_vars = ["PP", "FPCDIR", "LAZARUSDIR", "FPCTARGET", "FPCTARGETCPU"]
        for var in env_vars:
            value = os.environ.get(var, "")
            if value:
                initialization_options[var] = value

        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {
                        "didSave": True,
                        "dynamicRegistration": True,
                        "willSave": True,
                        "willSaveWaitUntil": True,
                    },
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                        },
                    },
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"],
                    },
                    "signatureHelp": {
                        "dynamicRegistration": True,
                        "signatureInformation": {
                            "documentationFormat": ["markdown", "plaintext"],
                        },
                    },
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentHighlight": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "codeAction": {
                        "dynamicRegistration": True,
                        "codeActionLiteralSupport": {
                            "codeActionKind": {
                                "valueSet": [
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
                    "formatting": {"dynamicRegistration": True},
                    "rangeFormatting": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                    "executeCommand": {"dynamicRegistration": True},
                    "configuration": True,
                    "workspaceEdit": {
                        "documentChanges": True,
                    },
                },
            },
            "initializationOptions": initialization_options,
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }

        return initialize_params  # type: ignore

    def _start_server(self) -> None:
        """
        Starts the Pascal Language Server, waits for the server to be ready and yields the LanguageServer instance.
        """

        def register_capability_handler(params: dict) -> None:
            log.debug(f"Capability registered: {params}")
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")
            # Mark server as ready when we see initialization messages
            message_text = msg.get("message", "")
            if "initialized" in message_text.lower() or "ready" in message_text.lower():
                log.info("Pascal language server ready signal detected")
                self.server_ready.set()
                self.completions_available.set()

        def publish_diagnostics(params: dict) -> None:
            log.debug(f"Diagnostics: {params}")
            return

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("window/showMessage", window_log_message)
        self.server.on_notification("textDocument/publishDiagnostics", publish_diagnostics)
        self.server.on_notification("$/progress", do_nothing)

        log.info("Starting Pascal server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response from Pascal server: {init_response}")

        # Verify capabilities
        capabilities = init_response.get("capabilities", {})
        assert "textDocumentSync" in capabilities

        # Check for various capabilities
        if "completionProvider" in capabilities:
            log.info("Pascal server supports code completion")
        if "definitionProvider" in capabilities:
            log.info("Pascal server supports go to definition")
        if "referencesProvider" in capabilities:
            log.info("Pascal server supports find references")
        if "documentSymbolProvider" in capabilities:
            log.info("Pascal server supports document symbols")

        self.server.notify.initialized({})

        # Wait for server readiness with timeout
        log.info("Waiting for Pascal language server to be ready...")
        if not self.server_ready.wait(timeout=5.0):
            # pasls may not send explicit ready signals, so we proceed after timeout
            log.info("Timeout waiting for Pascal server ready signal, assuming server is ready")
            self.server_ready.set()
            self.completions_available.set()
        else:
            log.info("Pascal server initialization complete")

    def is_ignored_dirname(self, dirname: str) -> bool:
        """
        Check if a directory should be ignored for Pascal projects.
        Common Pascal/Lazarus directories to ignore.
        """
        ignored_dirs = {
            "lib",
            "backup",
            "__history",
            "__recovery",
            "bin",
            ".git",
            ".svn",
            ".hg",
            "node_modules",
        }
        return dirname.lower() in ignored_dirs
