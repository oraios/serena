"""
Provides TOML specific instantiation of the LanguageServer class using Taplo.
Contains various configurations and settings specific to TOML files.
"""

import gzip
import hashlib
import logging
import os
import platform
import shutil
import socket
import stat
import threading
import urllib.request
from typing import Any

# Download timeout in seconds (prevents indefinite hangs)
DOWNLOAD_TIMEOUT_SECONDS = 120

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_utils import PathUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# Taplo release version and download URLs
TAPLO_VERSION = "0.10.0"
TAPLO_DOWNLOAD_BASE = f"https://github.com/tamasfe/taplo/releases/download/{TAPLO_VERSION}"

# SHA256 checksums for Taplo releases (verified from official GitHub releases)
# Source: https://github.com/tamasfe/taplo/releases/tag/0.10.0
# To update: download each release file and run: sha256sum <filename>
TAPLO_SHA256_CHECKSUMS: dict[str, str] = {
    "taplo-windows-x86_64.zip": "1615eed140039bd58e7089109883b1c434de5d6de8f64a993e6e8c80ca57bdf9",
    "taplo-windows-x86.zip": "b825701daab10dcfc0251e6d668cd1a9c0e351e7f6762dd20844c3f3f3553aa0",
    "taplo-darwin-x86_64.gz": "898122cde3a0b1cd1cbc2d52d3624f23338218c91b5ddb71518236a4c2c10ef2",
    "taplo-darwin-aarch64.gz": "713734314c3e71894b9e77513c5349835eefbd52908445a0d73b0c7dc469347d",
    "taplo-linux-x86_64.gz": "8fe196b894ccf9072f98d4e1013a180306e17d244830b03986ee5e8eabeb6156",
    "taplo-linux-aarch64.gz": "033681d01eec8376c3fd38fa3703c79316f5e14bb013d859943b60a07bccdcc3",
    "taplo-linux-armv7.gz": "6b728896afe2573522f38b8e668b1ff40eb5928fd9d6d0c253ecae508274d417",
}


def _verify_sha256(file_path: str, expected_hash: str) -> bool:
    """Verify SHA256 checksum of a downloaded file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    actual_hash = sha256_hash.hexdigest()
    return actual_hash.lower() == expected_hash.lower()


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
        custom_command = solidlsp_settings.get_ls_specific_settings(self.get_language_enum_instance()).get(SolidLSPSettings.CustomLSSettings.COMMAND_KEY, None)
        if custom_command:
            cmd = custom_command
        else:
            taplo_executable_path = self._setup_runtime_dependencies(solidlsp_settings)
            cmd = f"{taplo_executable_path} lsp stdio"
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=cmd, cwd=repository_root_path),
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
        """Download and extract Taplo binary with SHA256 verification."""
        # TODO: consider using existing download utilities in SolidLSP instead of the custom logic here
        download_url, _ = _get_taplo_download_url()
        archive_filename = os.path.basename(download_url)

        try:
            log.info(f"Downloading Taplo from: {download_url}")
            archive_path = os.path.join(install_dir, archive_filename)

            # Download the archive with timeout to prevent indefinite hangs
            old_timeout = socket.getdefaulttimeout()
            try:
                socket.setdefaulttimeout(DOWNLOAD_TIMEOUT_SECONDS)
                urllib.request.urlretrieve(download_url, archive_path)
            finally:
                socket.setdefaulttimeout(old_timeout)

            # Verify SHA256 checksum
            expected_hash = TAPLO_SHA256_CHECKSUMS.get(archive_filename)
            if expected_hash:
                if not _verify_sha256(archive_path, expected_hash):
                    os.remove(archive_path)
                    raise RuntimeError(
                        f"SHA256 checksum verification failed for {archive_filename}. "
                        "The downloaded file may be corrupted or tampered with. "
                        "Try installing manually: cargo install taplo-cli --locked"
                    )
                log.info(f"SHA256 checksum verified for {archive_filename}")
            else:
                log.warning(
                    f"No SHA256 checksum available for {archive_filename}. "
                    "Skipping verification - consider installing manually: cargo install taplo-cli --locked"
                )

            # Extract based on format
            if archive_path.endswith(".gz") and not archive_path.endswith(".tar.gz"):
                # Single file gzip
                with gzip.open(archive_path, "rb") as f_in:
                    with open(executable_path, "wb") as f_out:
                        f_out.write(f_in.read())
            elif archive_path.endswith(".zip"):
                import zipfile

                with zipfile.ZipFile(archive_path, "r") as zip_ref:
                    # Security: Validate paths to prevent zip slip vulnerability
                    for member in zip_ref.namelist():
                        member_path = os.path.normpath(os.path.join(install_dir, member))
                        if not member_path.startswith(os.path.normpath(install_dir)):
                            raise RuntimeError(f"Zip slip detected: {member} attempts to escape install directory")
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
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
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
