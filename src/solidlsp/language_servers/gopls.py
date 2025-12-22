import logging
import os
import pathlib
import subprocess
import threading
from typing import cast

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class Gopls(SolidLanguageServer):
    """
    Provides Go specific instantiation of the LanguageServer class using gopls.
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For Go projects, we should ignore:
        # - vendor: third-party dependencies vendored into the project
        # - node_modules: if the project has JavaScript components
        # - dist/build: common output directories
        return super().is_ignored_dirname(dirname) or dirname in ["vendor", "node_modules", "dist", "build"]

    @staticmethod
    def _determine_log_level(line: str) -> int:
        """Classify gopls stderr output to avoid false-positive errors."""
        line_lower = line.lower()

        # File discovery messages that are not actual errors
        if any(
            [
                "discover.go:" in line_lower,
                "walker.go:" in line_lower,
                "walking of {file://" in line_lower,
                "bus: -> discover" in line_lower,
            ]
        ):
            return logging.DEBUG

        return SolidLanguageServer._determine_log_level(line)

    @staticmethod
    def _get_go_version() -> str | None:
        """Get the installed Go version or None if not found."""
        try:
            result = subprocess.run(["go", "version"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        return None

    @staticmethod
    def _get_gopls_version() -> str | None:
        """Get the installed gopls version or None if not found."""
        try:
            result = subprocess.run(["gopls", "version"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        return None

    @staticmethod
    def _setup_runtime_dependency() -> bool:
        """
        Check if required Go runtime dependencies are available.
        Raises RuntimeError with helpful message if dependencies are missing.
        """
        go_version = Gopls._get_go_version()
        if not go_version:
            raise RuntimeError(
                "Go is not installed. Please install Go from https://golang.org/doc/install and make sure it is added to your PATH."
            )

        gopls_version = Gopls._get_gopls_version()
        if not gopls_version:
            raise RuntimeError(
                "Found a Go version but gopls is not installed.\n"
                "Please install gopls as described in https://pkg.go.dev/golang.org/x/tools/gopls#section-readme\n\n"
                "After installation, make sure it is added to your PATH (it might be installed in a different location than Go)."
            )

        return True

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        self._setup_runtime_dependency()

        super().__init__(config, repository_root_path, ProcessLaunchInfo(cmd="gopls", cwd=repository_root_path), "go", solidlsp_settings)
        self.server_ready = threading.Event()
        self.request_id = 0

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Go Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                },
                "workspace": {"workspaceFolders": True, "didChangeConfiguration": {"dynamicRegistration": True}},
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
        return cast(InitializeParams, initialize_params)

    def _start_server(self) -> None:
        """Start gopls server process"""

        def register_capability_handler(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting gopls server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]

        self.server.notify.initialized({})
        self.completions_available.set()

        # gopls server is typically ready immediately after initialization
        self.server_ready.set()
        self.server_ready.wait()
