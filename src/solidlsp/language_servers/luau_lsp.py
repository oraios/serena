"""
Provides Luau specific instantiation of the LanguageServer class using luau-lsp.

Luau is the programming language used by Roblox, derived from Lua 5.1 with
additional features like type annotations, string interpolation, and more.
This uses JohnnyMorganz/luau-lsp as the language server backend.

Requirements:
    - luau-lsp binary must be installed and available in PATH,
      or it will be automatically downloaded from GitHub releases.

See: https://github.com/JohnnyMorganz/luau-lsp
"""

import logging
import os
import pathlib
import platform
import shutil
import zipfile
from pathlib import Path

import requests
from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# Pin to a known stable release
LUAU_LSP_VERSION = "1.57.1"


class LuauLanguageServer(SolidLanguageServer):
    """
    Provides Luau specific instantiation of the LanguageServer class using luau-lsp.
    Luau is the programming language used by Roblox (a typed superset of Lua 5.1).
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",
            "Packages",  # Wally packages
            "DevPackages",  # Wally dev packages
            "roblox_packages",  # Some Rojo projects
            "build",
            "dist",
            ".cache",
        ]

    @staticmethod
    def _get_luau_lsp_path() -> str | None:
        """Get the path to luau-lsp executable."""
        # First check if it's in PATH
        luau_lsp = shutil.which("luau-lsp")
        if luau_lsp:
            return luau_lsp

        # Check common installation locations
        home = Path.home()
        possible_paths = [
            home / ".serena" / "language_servers" / "luau" / "luau-lsp",
            home / ".local" / "bin" / "luau-lsp",
            Path("/usr/local/bin/luau-lsp"),
        ]

        # Add platform-specific paths
        system = platform.system()
        if system == "Windows":
            possible_paths.extend(
                [
                    home / ".serena" / "language_servers" / "luau" / "luau-lsp.exe",
                    home / "AppData" / "Local" / "luau-lsp" / "luau-lsp.exe",
                ]
            )
        elif system == "Darwin":
            # Homebrew or aftman
            possible_paths.extend(
                [
                    Path("/opt/homebrew/bin/luau-lsp"),
                    home / ".aftman" / "bin" / "luau-lsp",
                ]
            )
        else:
            # Linux - aftman
            possible_paths.append(home / ".aftman" / "bin" / "luau-lsp")

        for path in possible_paths:
            if path.exists():
                return str(path)

        return None

    @staticmethod
    def _download_luau_lsp() -> str:
        """Download and install luau-lsp if not present."""
        system = platform.system()
        machine = platform.machine().lower()
        version = LUAU_LSP_VERSION

        # Map platform to download filename
        # Asset names: luau-lsp-win64.zip, luau-lsp-linux-x86_64.zip, luau-lsp-macos.zip
        if system == "Linux":
            if machine in ["x86_64", "amd64"]:
                asset_name = "luau-lsp-linux-x86_64.zip"
            else:
                raise RuntimeError(
                    f"Unsupported Linux architecture: {machine}. "
                    "luau-lsp only provides linux-x86_64 binaries. "
                    "Please build from source: https://github.com/JohnnyMorganz/luau-lsp"
                )
        elif system == "Darwin":
            # macOS uses a single universal binary
            asset_name = "luau-lsp-macos.zip"
        elif system == "Windows":
            asset_name = "luau-lsp-win64.zip"
        else:
            raise RuntimeError(f"Unsupported operating system: {system}")

        download_url = f"https://github.com/JohnnyMorganz/luau-lsp/releases/download/{version}/{asset_name}"

        # Create installation directory
        install_dir = Path.home() / ".serena" / "language_servers" / "luau"
        install_dir.mkdir(parents=True, exist_ok=True)

        # Download the file
        log.info(f"Downloading luau-lsp from {download_url}...")
        print(f"Downloading luau-lsp {version} from {download_url}...")
        response = requests.get(download_url, stream=True)
        response.raise_for_status()

        # Save the zip
        download_path = install_dir / asset_name
        with open(download_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        # Extract
        log.info(f"Extracting luau-lsp to {install_dir}...")
        print(f"Extracting luau-lsp to {install_dir}...")
        with zipfile.ZipFile(download_path, "r") as zip_ref:
            zip_ref.extractall(install_dir)

        # Clean up download file
        download_path.unlink()

        # Find the binary
        if system == "Windows":
            binary_name = "luau-lsp.exe"
        else:
            binary_name = "luau-lsp"

        binary_path = install_dir / binary_name
        if not binary_path.exists():
            # Some releases may extract into a subdirectory
            for candidate in install_dir.rglob(binary_name):
                binary_path = candidate
                break

        if not binary_path.exists():
            raise RuntimeError("Failed to find luau-lsp executable after extraction")

        # Make executable on Unix systems
        if system != "Windows":
            binary_path.chmod(0o755)

        log.info(f"luau-lsp installed at: {binary_path}")
        print(f"luau-lsp installed at: {binary_path}")
        return str(binary_path)

    @staticmethod
    def _setup_runtime_dependency() -> str:
        """
        Check if luau-lsp is available.
        Downloads it if not present.
        """
        luau_lsp_path = LuauLanguageServer._get_luau_lsp_path()

        if not luau_lsp_path:
            log.info("luau-lsp not found. Downloading...")
            print("luau-lsp not found. Downloading...")
            luau_lsp_path = LuauLanguageServer._download_luau_lsp()

        return luau_lsp_path

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        luau_lsp_path = self._setup_runtime_dependency()

        # luau-lsp uses subcommand 'lsp' to start in Language Server mode
        # The binary itself is the command, with 'lsp' as an argument
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=[luau_lsp_path, "lsp"], cwd=repository_root_path),
            "luau",
            solidlsp_settings,
        )
        self.request_id = 0

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Luau Language Server.
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
                    "signatureHelp": {
                        "dynamicRegistration": True,
                        "signatureInformation": {
                            "documentationFormat": ["markdown", "plaintext"],
                            "parameterInformation": {"labelOffsetSupport": True},
                        },
                    },
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                    "callHierarchy": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "configuration": True,
                    "symbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
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
            # luau-lsp initialization options
            # These can be overridden via .luaurc in the project root
            "initializationOptions": {},
        }
        return initialize_params  # type: ignore[return-value]

    def _start_server(self) -> None:
        """Start Luau Language Server process"""

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

        log.info("Starting Luau Language Server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]
        assert "documentSymbolProvider" in init_response["capabilities"]
        assert "referencesProvider" in init_response["capabilities"]

        self.server.notify.initialized({})

        # luau-lsp is typically ready immediately after initialization
