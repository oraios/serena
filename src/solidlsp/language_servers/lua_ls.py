"""
Provides Lua specific instantiation of the LanguageServer class using lua-language-server.
"""

import logging
import os
import pathlib
import platform
import shutil
import tarfile
import threading
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


class LuaLanguageServer(SolidLanguageServer):
    """
    Provides Lua specific instantiation of the LanguageServer class using lua-language-server.
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For Lua projects, we should ignore:
        # - .luarocks: package manager cache
        # - lua_modules: local dependencies
        # - node_modules: if the project has JavaScript components
        return super().is_ignored_dirname(dirname) or dirname in [".luarocks", "lua_modules", "node_modules", "build", "dist", ".cache"]

    @staticmethod
    def _get_lua_ls_path() -> str | None:
        """Get the path to lua-language-server executable."""
        # First check if it's in PATH
        lua_ls = shutil.which("lua-language-server")
        if lua_ls:
            return lua_ls

        # Check common installation locations
        home = Path.home()
        possible_paths = [
            home / ".local" / "bin" / "lua-language-server",
            home / ".serena" / "language_servers" / "lua" / "bin" / "lua-language-server",
            Path("/usr/local/bin/lua-language-server"),
            Path("/opt/lua-language-server/bin/lua-language-server"),
        ]

        # Add Windows-specific paths
        if platform.system() == "Windows":
            possible_paths.extend(
                [
                    home / "AppData" / "Local" / "lua-language-server" / "bin" / "lua-language-server.exe",
                    home / ".serena" / "language_servers" / "lua" / "bin" / "lua-language-server.exe",
                ]
            )

        for path in possible_paths:
            if path.exists():
                return str(path)

        return None

    @staticmethod
    def _download_lua_ls() -> str:
        """Download and install lua-language-server if not present."""
        system = platform.system()
        machine = platform.machine().lower()
        lua_ls_version = "3.15.0"

        # Map platform and architecture to download URL
        if system == "Linux":
            if machine in ["x86_64", "amd64"]:
                download_name = f"lua-language-server-{lua_ls_version}-linux-x64.tar.gz"
            elif machine in ["aarch64", "arm64"]:
                download_name = f"lua-language-server-{lua_ls_version}-linux-arm64.tar.gz"
            else:
                raise RuntimeError(f"Unsupported Linux architecture: {machine}")
        elif system == "Darwin":
            if machine in ["x86_64", "amd64"]:
                download_name = f"lua-language-server-{lua_ls_version}-darwin-x64.tar.gz"
            elif machine in ["arm64", "aarch64"]:
                download_name = f"lua-language-server-{lua_ls_version}-darwin-arm64.tar.gz"
            else:
                raise RuntimeError(f"Unsupported macOS architecture: {machine}")
        elif system == "Windows":
            if machine in ["amd64", "x86_64"]:
                download_name = f"lua-language-server-{lua_ls_version}-win32-x64.zip"
            else:
                raise RuntimeError(f"Unsupported Windows architecture: {machine}")
        else:
            raise RuntimeError(f"Unsupported operating system: {system}")

        download_url = f"https://github.com/LuaLS/lua-language-server/releases/download/{lua_ls_version}/{download_name}"

        # Create installation directory
        install_dir = Path.home() / ".serena" / "language_servers" / "lua"
        install_dir.mkdir(parents=True, exist_ok=True)

        # Download the file
        print(f"Downloading lua-language-server from {download_url}...")
        response = requests.get(download_url, stream=True)
        response.raise_for_status()

        # Save and extract
        download_path = install_dir / download_name
        with open(download_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"Extracting lua-language-server to {install_dir}...")
        if download_name.endswith(".tar.gz"):
            with tarfile.open(download_path, "r:gz") as tar:
                tar.extractall(install_dir)
        elif download_name.endswith(".zip"):
            with zipfile.ZipFile(download_path, "r") as zip_ref:
                zip_ref.extractall(install_dir)

        # Clean up download file
        download_path.unlink()

        # Make executable on Unix systems
        if system != "Windows":
            lua_ls_path = install_dir / "bin" / "lua-language-server"
            if lua_ls_path.exists():
                lua_ls_path.chmod(0o755)
                return str(lua_ls_path)
        else:
            lua_ls_path = install_dir / "bin" / "lua-language-server.exe"
            if lua_ls_path.exists():
                return str(lua_ls_path)

        raise RuntimeError("Failed to find lua-language-server executable after extraction")

    @staticmethod
    def _setup_runtime_dependency() -> str:
        """
        Check if required Lua runtime dependencies are available.
        Downloads lua-language-server if not present.
        """
        lua_ls_path = LuaLanguageServer._get_lua_ls_path()

        if not lua_ls_path:
            print("lua-language-server not found. Downloading...")
            lua_ls_path = LuaLanguageServer._download_lua_ls()
            print(f"lua-language-server installed at: {lua_ls_path}")

        return lua_ls_path

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        lua_ls_path = self._setup_runtime_dependency()

        super().__init__(
            config, repository_root_path, ProcessLaunchInfo(cmd=lua_ls_path, cwd=repository_root_path), "lua", solidlsp_settings
        )
        self.server_ready = threading.Event()
        self.request_id = 0

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Lua Language Server.
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
            "initializationOptions": {
                # Lua Language Server specific options
                "runtime": {
                    "version": "Lua 5.4",
                    "path": ["?.lua", "?/init.lua"],
                },
                "diagnostics": {
                    "enable": True,
                    "globals": ["vim", "describe", "it", "before_each", "after_each"],  # Common globals
                },
                "workspace": {
                    "library": [],  # Can be extended with project-specific libraries
                    "checkThirdParty": False,
                    "userThirdParty": [],
                },
                "telemetry": {
                    "enable": False,
                },
                "completion": {
                    "enable": True,
                    "callSnippet": "Both",
                    "keywordSnippet": "Both",
                },
            },
        }
        return initialize_params  # type: ignore[return-value]

    def _start_server(self) -> None:
        """Start Lua Language Server process"""

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

        log.info("Starting Lua Language Server process")
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
        self.completions_available.set()

        # Lua Language Server is typically ready immediately after initialization
        self.server_ready.set()
        self.server_ready.wait()
