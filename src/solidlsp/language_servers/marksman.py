"""
Provides Markdown specific instantiation of the LanguageServer class using marksman.
Contains various configurations and settings specific to Markdown.
"""

import logging
import os
import pathlib
import platform
import shutil
import threading
from pathlib import Path

import requests
from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


class Marksman(SolidLanguageServer):
    """
    Provides Markdown specific instantiation of the LanguageServer class using marksman.
    """

    @staticmethod
    def _get_marksman_path():
        """Get the path to marksman executable."""
        # First check if it's in PATH
        marksman = shutil.which("marksman")
        if marksman:
            return marksman

        # Check common installation locations
        home = Path.home()
        possible_paths = [
            home / ".local" / "bin" / "marksman",
            home / ".serena" / "language_servers" / "marksman" / "marksman",
            Path("/usr/local/bin/marksman"),
        ]

        # Add Windows-specific paths
        if platform.system() == "Windows":
            possible_paths.extend(
                [
                    home / "AppData" / "Local" / "marksman" / "marksman.exe",
                    home / ".serena" / "language_servers" / "marksman" / "marksman.exe",
                ]
            )

        for path in possible_paths:
            if path.exists():
                return str(path)

        return None

    @staticmethod
    def _download_marksman():
        """Download and install marksman if not present."""
        system = platform.system()
        marksman_version = "2024-12-18"

        # Map platform to download URL and filename
        if system == "Linux":
            download_name = "marksman-linux-x64"
            download_url = f"https://github.com/artempyanykh/marksman/releases/download/{marksman_version}/{download_name}"
        elif system == "Darwin":
            # Use universal binary for macOS
            download_name = "marksman"
            download_url = f"https://github.com/artempyanykh/marksman/releases/download/{marksman_version}/{download_name}"
        elif system == "Windows":
            download_name = "marksman.exe"
            download_url = f"https://github.com/artempyanykh/marksman/releases/download/{marksman_version}/{download_name}"
        else:
            raise RuntimeError(f"Unsupported operating system: {system}")

        # Create installation directory
        install_dir = Path.home() / ".serena" / "language_servers" / "marksman"
        install_dir.mkdir(parents=True, exist_ok=True)

        # Download the file
        print(f"Downloading marksman from {download_url}...")
        response = requests.get(download_url, stream=True)
        response.raise_for_status()

        # Save the binary
        if system == "Windows":
            marksman_path = install_dir / "marksman.exe"
        else:
            marksman_path = install_dir / "marksman"

        with open(marksman_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        # Make executable on Unix systems
        if system != "Windows":
            marksman_path.chmod(0o755)

        print(f"marksman installed at: {marksman_path}")
        return str(marksman_path)

    @staticmethod
    def _setup_runtime_dependency():
        """
        Check if marksman is available.
        Downloads marksman if not present.
        """
        marksman_path = Marksman._get_marksman_path()

        if not marksman_path:
            print("marksman not found. Downloading...")
            marksman_path = Marksman._download_marksman()
            print(f"marksman installed at: {marksman_path}")

        return marksman_path

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        """
        Creates a Marksman instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        marksman_path = self._setup_runtime_dependency()

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=f"{marksman_path} server", cwd=repository_root_path),
            "markdown",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["node_modules", ".obsidian", ".vitepress", ".vuepress"]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Marksman Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params: InitializeParams = {  # type: ignore
            "processId": os.getpid(),
            "locale": "en",
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "codeAction": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }
        return initialize_params

    def _start_server(self):
        """
        Starts the Marksman Language Server and waits for it to be ready.
        """

        def register_capability_handler(_params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        def do_nothing(_params):
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting marksman server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to marksman server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)
        self.logger.log(f"Received initialize response from marksman server: {init_response}", logging.DEBUG)

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]

        self.server.notify.initialized({})

        # marksman is typically ready immediately after initialization
        self.logger.log("Marksman server initialization complete", logging.INFO)
        self.server_ready.set()
        self.completions_available.set()
