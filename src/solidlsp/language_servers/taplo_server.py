"""
Provides TOML specific instantiation of the LanguageServer class using Taplo.
Contains various configurations and settings specific to TOML files.
"""

import gzip
import logging
import os
import platform
import shutil
import stat
import threading
import urllib.request
from typing import Any

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings
from solidlsp.utils.path_utils import PathUtils

log = logging.getLogger(__name__)

# Taplo release version and download URLs
TAPLO_VERSION = "0.10.0"
TAPLO_DOWNLOAD_BASE = f"https://github.com/tamasfe/taplo/releases/download/{TAPLO_VERSION}"


def _get_taplo_download_url() -> tuple[str, str]:
    """
    Get the appropriate Taplo download URL for the current platform.

    Returns:
        Tuple of (download_url, executable_name)

    """
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Map machine architecture to Taplo naming convention
    arch_map = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "x86": "x86",
        "i386": "x86",
        "i686": "x86",
        "aarch64": "aarch64",
        "arm64": "aarch64",
        "armv7l": "armv7",
    }

    arch = arch_map.get(machine, "x86_64")  # Default to x86_64

    if system == "windows":
        filename = f"taplo-windows-{arch}.zip"
        executable = "taplo.exe"
    elif system == "darwin":
        filename = f"taplo-darwin-{arch}.gz"
        executable = "taplo"
    else:  # Linux and others
        filename = f"taplo-linux-{arch}.gz"
        executable = "taplo"

    return f"{TAPLO_DOWNLOAD_BASE}/{filename}", executable


class TaploServer(SolidLanguageServer):
    """
    Provides TOML specific instantiation of the LanguageServer class using Taplo.
    Taplo is a TOML toolkit with LSP support for validation, formatting, and schema support.
    """

    @staticmethod
    def _determine_log_level(line: str) -> int:
        """Classify Taplo stderr output to avoid false-positive errors."""
        line_lower = line.lower()

        # Known informational messages from Taplo
        if any(
            [
                "schema" in line_lower and "not found" in line_lower,
                "warning" in line_lower,
            ]
        ):
            return logging.DEBUG

        return SolidLanguageServer._determine_log_level(line)

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a TaploServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        taplo_executable_path = self._setup_runtime_dependencies(solidlsp_settings)
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=f"{taplo_executable_path} lsp stdio", cwd=repository_root_path),
            "toml",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    @classmethod
    def _setup_runtime_dependencies(cls, solidlsp_settings: SolidLSPSettings) -> str:
        """
        Setup runtime dependencies for Taplo and return the command to start the server.
        """
        # First check if taplo is already installed system-wide
        system_taplo = shutil.which("taplo")
        if system_taplo:
            log.info(f"Using system-installed Taplo at: {system_taplo}")
            return system_taplo

        # Setup local installation directory
        taplo_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), "taplo")
        os.makedirs(taplo_dir, exist_ok=True)

        _, executable_name = _get_taplo_download_url()
        taplo_executable = os.path.join(taplo_dir, executable_name)

        if os.path.exists(taplo_executable) and os.access(taplo_executable, os.X_OK):
            log.info(f"Using cached Taplo at: {taplo_executable}")
            return taplo_executable

        # Download and install Taplo
        log.info(f"Taplo not found. Downloading version {TAPLO_VERSION}...")
        cls._download_taplo(taplo_dir, taplo_executable)

        if not os.path.exists(taplo_executable):
            raise FileNotFoundError(
                f"Taplo executable not found at {taplo_executable}. "
                "Installation may have failed. Try installing manually: cargo install taplo-cli --locked"
            )

        return taplo_executable

    @classmethod
    def _download_taplo(cls, install_dir: str, executable_path: str) -> None:
        """Download and extract Taplo binary."""
        download_url, _ = _get_taplo_download_url()

        try:
            log.info(f"Downloading Taplo from: {download_url}")
            archive_path = os.path.join(install_dir, os.path.basename(download_url))

            # Download the archive
            urllib.request.urlretrieve(download_url, archive_path)

            # Extract based on format
            if archive_path.endswith(".gz") and not archive_path.endswith(".tar.gz"):
                # Single file gzip
                with gzip.open(archive_path, "rb") as f_in:
                    with open(executable_path, "wb") as f_out:
                        f_out.write(f_in.read())
            elif archive_path.endswith(".zip"):
                import zipfile

                with zipfile.ZipFile(archive_path, "r") as zip_ref:
                    # Extract all and find the executable
                    zip_ref.extractall(install_dir)

            # Make executable on Unix systems
            if os.name != "nt":
                os.chmod(executable_path, os.stat(executable_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

            # Clean up archive
            os.remove(archive_path)
            log.info(f"Taplo installed successfully at: {executable_path}")

        except Exception as e:
            log.error(f"Failed to download Taplo: {e}")
            raise RuntimeError(
                f"Failed to download Taplo from {download_url}. Try installing manually: cargo install taplo-cli --locked"
            ) from e

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Taplo Language Server.
        """
        root_uri = PathUtils.path_to_uri(repository_absolute_path)
        initialize_params = {
            "locale": "en",
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
                    "formatting": {"dynamicRegistration": True},
                    "semanticTokens": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
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
            "initializationOptions": {
                "configuration": {
                    "evenBetterToml": {
                        "schema": {
                            "enabled": True,
                            "repositoryEnabled": True,
                            "repositoryUrl": "https://taplo.tamasfe.dev/schema_index.json",
                        },
                        "formatter": {"alignEntries": False, "alignComments": True, "arrayTrailingComma": True},
                    }
                }
            },
        }
        return initialize_params  # type: ignore

    def _start_server(self) -> None:
        """
        Starts the Taplo Language Server and initializes it.
        """

        def register_capability_handler(params: Any) -> None:
            return

        def do_nothing(params: Any) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Taplo server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request to Taplo server")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response from Taplo: {init_response}")

        # Verify document symbol support
        capabilities = init_response.get("capabilities", {})
        if capabilities.get("documentSymbolProvider"):
            log.info("Taplo server supports document symbols")
        else:
            log.warning("Taplo server may have limited document symbol support")

        self.server.notify.initialized({})

        log.info("Taplo server initialization complete")
        self.server_ready.set()
        self.completions_available.set()

    def is_ignored_dirname(self, dirname: str) -> bool:
        """Define TOML-specific directories to ignore."""
        return super().is_ignored_dirname(dirname) or dirname in ["target", ".cargo", "node_modules"]
