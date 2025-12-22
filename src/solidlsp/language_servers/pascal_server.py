"""
Provides Pascal/Free Pascal specific instantiation of the LanguageServer class using pasls.
Contains various configurations and settings specific to Pascal and Free Pascal.
"""

import logging
import os
import pathlib
import shutil
import subprocess
import threading
from typing import Optional

from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection, quote_windows_path
from solidlsp.ls import DocumentSymbols, LSPFileBuffer, SolidLanguageServer
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

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a PascalLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        pasls_executable_path = self._setup_runtime_dependencies(config, solidlsp_settings)
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=pasls_executable_path, cwd=repository_root_path),
            "pascal",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.completions_available_event = threading.Event()

    @classmethod
    def _setup_runtime_dependencies(cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings) -> str:
        """
        Setup runtime dependencies for Pascal Language Server (pasls) and return the command to start the server.

        This method will:
        1. Check if pasls is in PATH
        2. Check if pasls exists in a known location
        3. If not found, attempt to build pasls using lazbuild

        Returns:
            str: The command to start the pasls server
        """
        # First, check if pasls is already in PATH
        pasls_in_path = shutil.which("pasls")
        if pasls_in_path:
            log.info(f"Found pasls in PATH: {pasls_in_path}")
            return quote_windows_path(pasls_in_path)

        # Check common installation locations
        pasls_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), "pasls")
        pasls_executable = os.path.join(pasls_dir, "pasls")

        # Handle Windows executable extension
        if os.name == "nt":
            pasls_executable += ".exe"

        # If pasls exists in our managed directory, use it
        if os.path.exists(pasls_executable):
            log.info(f"Found pasls at: {pasls_executable}")
            return quote_windows_path(pasls_executable)

        # pasls not found, attempt to build it
        log.info("pasls not found. Attempting to build from source...")
        cls._build_pasls(pasls_dir, solidlsp_settings)

        if not os.path.exists(pasls_executable):
            raise FileNotFoundError(
                f"pasls executable not found at {pasls_executable}. "
                f"Please ensure Free Pascal Compiler (fpc) and Lazarus are installed, "
                f"or manually compile pasls and add it to PATH. "
                f"See: https://github.com/genericptr/pascal-language-server"
            )

        return quote_windows_path(pasls_executable)

    @classmethod
    def _build_pasls(cls, target_dir: str, solidlsp_settings: SolidLSPSettings) -> None:
        """
        Attempt to build pasls using lazbuild.

        This requires:
        - Free Pascal Compiler (fpc)
        - Lazarus (specifically lazbuild)
        - Git (to clone the repository)
        """
        # Check if lazbuild is available
        lazbuild = shutil.which("lazbuild")
        if not lazbuild:
            # Try common locations for lazbuild
            common_lazbuild_paths = [
                r"D:\che_m\laz32\lazarus\lazbuild.exe",  # User's configured path
                r"C:\lazarus\lazbuild.exe",
                r"C:\Program Files\Lazarus\lazbuild.exe",
                r"C:\Program Files (x86)\Lazarus\lazbuild.exe",
                "/usr/bin/lazbuild",
                "/usr/local/bin/lazbuild",
            ]

            for path in common_lazbuild_paths:
                if os.path.exists(path):
                    lazbuild = path
                    break

        if not lazbuild:
            raise FileNotFoundError(
                "lazbuild not found. Please install Lazarus or add lazbuild to PATH. "
                "See: https://www.lazarus-ide.org/"
            )

        log.info(f"Found lazbuild at: {lazbuild}")

        # Check if git is available
        git = shutil.which("git")
        if not git:
            raise FileNotFoundError("git not found. Please install git to clone the pasls repository.")

        # Create target directory
        os.makedirs(target_dir, exist_ok=True)

        # Clone pasls repository
        pasls_repo_url = "https://github.com/genericptr/pascal-language-server.git"
        pasls_source_dir = os.path.join(target_dir, "source")

        if not os.path.exists(pasls_source_dir):
            log.info(f"Cloning pasls repository to {pasls_source_dir}")
            subprocess.run(
                [git, "clone", pasls_repo_url, pasls_source_dir],
                check=True,
                capture_output=True,
                text=True
            )
        else:
            log.info(f"pasls source already exists at {pasls_source_dir}")

        # Build pasls using lazbuild
        pasls_project_file = os.path.join(pasls_source_dir, "src", "standard", "pasls.lpi")

        if not os.path.exists(pasls_project_file):
            raise FileNotFoundError(f"pasls project file not found at {pasls_project_file}")

        log.info(f"Building pasls using lazbuild...")
        try:
            result = subprocess.run(
                [lazbuild, pasls_project_file],
                check=True,
                capture_output=True,
                text=True,
                cwd=pasls_source_dir
            )
            log.info("pasls built successfully")
            log.debug(f"Build output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            log.error(f"Failed to build pasls: {e.stderr}")
            raise RuntimeError(f"Failed to build pasls. Error: {e.stderr}")

        # Copy the built executable to target directory
        built_pasls = os.path.join(pasls_source_dir, "src", "standard", "pasls")
        if os.name == "nt":
            built_pasls += ".exe"

        target_pasls = os.path.join(target_dir, os.path.basename(built_pasls))

        if os.path.exists(built_pasls):
            import shutil as shutil_module
            shutil_module.copy2(built_pasls, target_pasls)
            log.info(f"Copied pasls executable to {target_pasls}")
        else:
            raise FileNotFoundError(f"Built pasls executable not found at {built_pasls}")

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Pascal Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()

        # Get environment variables for FPC and Lazarus
        fpcdir = os.environ.get("FPCDIR", "")
        lazarusdir = os.environ.get("LAZARUSDIR", "")

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
            "initializationOptions": {
                "fpcOptions": [],  # Compiler options can be configured here
                "symbolDatabase": "",  # Optional: path to symbol database
                "maximumCompletions": 100,
                "overloadPolicy": "default",
                "insertCompletionsAsSnippets": True,
                "checkSyntax": True,
                "publishDiagnostics": True,
                "workspaceSymbols": True,
            },
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

        # Add environment variables if available
        if fpcdir or lazarusdir:
            env_config = {}
            if fpcdir:
                env_config["FPCDIR"] = fpcdir
            if lazarusdir:
                env_config["LAZARUSDIR"] = lazarusdir
            initialize_params["initializationOptions"]["environment"] = env_config

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

    def request_document_symbols(self, relative_file_path: str, file_buffer: LSPFileBuffer | None = None) -> DocumentSymbols:
        """
        Request document symbols for a Pascal file.
        """
        log.debug(f"Requesting document symbols for Pascal file: {relative_file_path}")
        document_symbols = super().request_document_symbols(relative_file_path, file_buffer=file_buffer)

        # Log what we found for debugging
        symbols_list = list(document_symbols.iter_symbols())
        log.info(f"Found {len(symbols_list)} symbols in {relative_file_path}")

        return document_symbols
