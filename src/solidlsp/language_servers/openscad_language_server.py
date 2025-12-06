"""
Provides OpenSCAD specific instantiation of the LanguageServer class using openscad-lsp.
"""

import logging
import os
import pathlib
import shutil
import subprocess
import threading

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class OpenSCADLanguageServer(SolidLanguageServer):
    """
    Provides OpenSCAD specific instantiation of the LanguageServer class using openscad-lsp.
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For OpenSCAD projects, we should ignore:
        # - build: common build output directory
        # - dist: distribution directory
        # - node_modules: if the project has JavaScript components
        return super().is_ignored_dirname(dirname) or dirname in ["build", "dist", "node_modules"]

    @staticmethod
    def _check_openscad_lsp_installed() -> bool:
        """Check if openscad-lsp is installed in the system."""
        return shutil.which("openscad-lsp") is not None

    @staticmethod
    def _check_cargo_installed() -> bool:
        """Check if cargo is installed in the system."""
        return shutil.which("cargo") is not None

    @staticmethod
    def _check_cargo_binstall_installed() -> bool:
        """Check if cargo-binstall is installed in the system."""
        try:
            result = subprocess.run(["cargo", "binstall", "--version"], capture_output=True, text=True, check=False)
            return result.returncode == 0
        except FileNotFoundError:
            return False

    @staticmethod
    def _install_with_cargo_binstall() -> bool:
        """Try to install openscad-lsp using cargo binstall."""
        log.info("Attempting to install openscad-lsp using cargo binstall...")
        try:
            result = subprocess.run(
                ["cargo", "binstall", "openscad-lsp", "--no-confirm"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                log.info("Successfully installed openscad-lsp using cargo binstall")
                return True
            log.warning(f"cargo binstall failed: {result.stderr}")
        except FileNotFoundError:
            log.warning("cargo binstall not found")
        return False

    @staticmethod
    def _install_with_cargo_install() -> bool:
        """Try to install openscad-lsp using cargo install."""
        log.info("Attempting to install openscad-lsp using cargo install (this may take a while)...")
        try:
            result = subprocess.run(
                ["cargo", "install", "openscad-lsp"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                log.info("Successfully installed openscad-lsp using cargo install")
                return True
            log.warning(f"cargo install failed: {result.stderr}")
        except FileNotFoundError:
            log.warning("cargo not found")
        return False

    @staticmethod
    def _setup_runtime_dependency() -> bool:
        """
        Check if openscad-lsp is available, and try to install it if not.
        Raises RuntimeError with helpful message if installation fails.
        """
        # First check if openscad-lsp is already installed
        if OpenSCADLanguageServer._check_openscad_lsp_installed():
            log.info("openscad-lsp is already installed")
            return True

        # Check if cargo is available for installation
        if not OpenSCADLanguageServer._check_cargo_installed():
            raise RuntimeError(
                "openscad-lsp is not installed and cargo (Rust toolchain) is not available.\n"
                "Please either:\n"
                "  1. Install openscad-lsp manually from https://github.com/Leathong/openscad-LSP\n"
                "  2. Install the Rust toolchain from https://rustup.rs/ to enable automatic installation\n"
            )

        # Try cargo binstall first (faster, downloads pre-built binary)
        if OpenSCADLanguageServer._check_cargo_binstall_installed():
            if OpenSCADLanguageServer._install_with_cargo_binstall():
                return True

        # Fall back to cargo install (compiles from source)
        if OpenSCADLanguageServer._install_with_cargo_install():
            return True

        raise RuntimeError(
            "Failed to install openscad-lsp automatically.\n"
            "Please install it manually:\n"
            "  cargo install openscad-lsp\n"
            "Or download pre-built binaries from https://github.com/Leathong/openscad-LSP/releases"
        )

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        self._setup_runtime_dependency()

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=["openscad-lsp", "--stdio"], cwd=repository_root_path),
            "openscad",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the OpenSCAD Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "deprecatedSupport": True,
                            "preselectSupport": True,
                        },
                    },
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"],
                    },
                    "rename": {
                        "dynamicRegistration": True,
                        "prepareSupport": True,
                    },
                    "formatting": {
                        "dynamicRegistration": True,
                    },
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "configuration": True,
                },
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
        return initialize_params  # type: ignore[return-value]

    def _start_server(self) -> None:
        """Start OpenSCAD Language Server process."""

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

        log.info("Starting OpenSCAD Language Server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]
        assert "documentSymbolProvider" in init_response["capabilities"]

        self.server.notify.initialized({})
        self.completions_available.set()

        # Server is ready after initialization
        self.server_ready.set()
