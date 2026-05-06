"""
Provides TOML specific instantiation of the LanguageServer class using Taplo.
Contains various configurations and settings specific to TOML files.

You can pass the following entries in ``ls_specific_settings["toml"]``:
    - taplo_version: Override the pinned Taplo version downloaded by Serena
      (default: the bundled Serena version).
"""

import logging
import os
import platform
import shutil
import stat
from typing import Any

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_utils import FileUtils, PathUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

TAPLO_ALLOWED_HOSTS = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
# To update: download each release file and run: sha256sum <filename>, copy values into DEFAULT_*.
INITIAL_TAPLO_VERSION = "0.10.0"
INITIAL_TAPLO_SHA256_CHECKSUMS: dict[str, str] = {
    "taplo-windows-x86_64.zip": "1615eed140039bd58e7089109883b1c434de5d6de8f64a993e6e8c80ca57bdf9",
    "taplo-windows-x86.zip": "b825701daab10dcfc0251e6d668cd1a9c0e351e7f6762dd20844c3f3f3553aa0",
    "taplo-darwin-x86_64.gz": "898122cde3a0b1cd1cbc2d52d3624f23338218c91b5ddb71518236a4c2c10ef2",
    "taplo-darwin-aarch64.gz": "713734314c3e71894b9e77513c5349835eefbd52908445a0d73b0c7dc469347d",
    "taplo-linux-x86_64.gz": "8fe196b894ccf9072f98d4e1013a180306e17d244830b03986ee5e8eabeb6156",
    "taplo-linux-aarch64.gz": "033681d01eec8376c3fd38fa3703c79316f5e14bb013d859943b60a07bccdcc3",
    "taplo-linux-armv7.gz": "6b728896afe2573522f38b8e668b1ff40eb5928fd9d6d0c253ecae508274d417",
}
DEFAULT_TAPLO_VERSION = "0.10.0"
DEFAULT_TAPLO_SHA256_CHECKSUMS: dict[str, str] = {
    "taplo-windows-x86_64.zip": "1615eed140039bd58e7089109883b1c434de5d6de8f64a993e6e8c80ca57bdf9",
    "taplo-windows-x86.zip": "b825701daab10dcfc0251e6d668cd1a9c0e351e7f6762dd20844c3f3f3553aa0",
    "taplo-darwin-x86_64.gz": "898122cde3a0b1cd1cbc2d52d3624f23338218c91b5ddb71518236a4c2c10ef2",
    "taplo-darwin-aarch64.gz": "713734314c3e71894b9e77513c5349835eefbd52908445a0d73b0c7dc469347d",
    "taplo-linux-x86_64.gz": "8fe196b894ccf9072f98d4e1013a180306e17d244830b03986ee5e8eabeb6156",
    "taplo-linux-aarch64.gz": "033681d01eec8376c3fd38fa3703c79316f5e14bb013d859943b60a07bccdcc3",
    "taplo-linux-armv7.gz": "6b728896afe2573522f38b8e668b1ff40eb5928fd9d6d0c253ecae508274d417",
}


def _taplo_sha(version: str, archive_filename: str) -> str | None:
    if version == INITIAL_TAPLO_VERSION:
        return INITIAL_TAPLO_SHA256_CHECKSUMS.get(archive_filename)
    if version == DEFAULT_TAPLO_VERSION:
        return DEFAULT_TAPLO_SHA256_CHECKSUMS.get(archive_filename)
    return None


def _get_taplo_download_url(version: str = DEFAULT_TAPLO_VERSION) -> tuple[str, str]:
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

    return f"https://github.com/tamasfe/taplo/releases/download/{version}/{filename}", executable


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
        super().__init__(
            config,
            repository_root_path,
            None,
            "toml",
            solidlsp_settings,
        )

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Setup runtime dependencies for Taplo and return the command to start the server.
            """
            # First check if taplo is already installed system-wide
            system_taplo = shutil.which("taplo")
            if system_taplo:
                log.info(f"Using system-installed Taplo at: {system_taplo}")
                return system_taplo

            # Setup local installation directory; legacy unversioned dir reserved for INITIAL only
            taplo_version = self._custom_settings.get("taplo_version", DEFAULT_TAPLO_VERSION)
            ls_dirname = "taplo" if taplo_version == INITIAL_TAPLO_VERSION else f"taplo-{taplo_version}"
            taplo_dir = os.path.join(self._ls_resources_dir, ls_dirname)
            os.makedirs(taplo_dir, exist_ok=True)
            _, executable_name = _get_taplo_download_url(taplo_version)
            taplo_executable = os.path.join(taplo_dir, executable_name)

            if os.path.exists(taplo_executable) and os.access(taplo_executable, os.X_OK):
                log.info(f"Using cached Taplo at: {taplo_executable}")
                return taplo_executable

            # Download and install Taplo
            log.info(f"Taplo not found. Downloading version {taplo_version}...")
            self._download_taplo(taplo_dir, taplo_executable, taplo_version)

            if not os.path.exists(taplo_executable):
                raise FileNotFoundError(
                    f"Taplo executable not found at {taplo_executable}. "
                    "Installation may have failed. Try installing manually: cargo install taplo-cli --locked"
                )

            return taplo_executable

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "lsp", "stdio"]

        @classmethod
        def _download_taplo(cls, install_dir: str, executable_path: str, version: str = DEFAULT_TAPLO_VERSION) -> None:
            """Download and extract Taplo binary using the shared verified download helper."""
            download_url, _ = _get_taplo_download_url(version)
            archive_filename = os.path.basename(download_url)
            # only verify the SHA when the resolved version is one of our pinned ones (INITIAL or current DEFAULT)
            expected_hash = _taplo_sha(version, archive_filename)
            if expected_hash is None and version in (INITIAL_TAPLO_VERSION, DEFAULT_TAPLO_VERSION):
                raise RuntimeError(f"No SHA256 checksum configured for Taplo archive: {archive_filename}")

            try:
                log.info(f"Downloading Taplo from: {download_url}")
                archive_type = "zip" if archive_filename.endswith(".zip") else "gz"
                target_path = install_dir if archive_type == "zip" else executable_path
                FileUtils.download_and_extract_archive_verified(
                    download_url,
                    target_path,
                    archive_type,
                    expected_sha256=expected_hash,
                    allowed_hosts=TAPLO_ALLOWED_HOSTS,
                )

                # Make executable on Unix systems
                if os.name != "nt":
                    os.chmod(executable_path, os.stat(executable_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

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

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        if dirname == ".vscode":
            # special case, one might want to analyze toml files in .vscode
            return False
        dirnames_to_ignore = ["target", ".cargo", "node_modules"]
        return dirname in dirnames_to_ignore or super().is_ignored_dirname(dirname)
