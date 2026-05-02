"""
Provides Lua specific instantiation of the LanguageServer class using lua-language-server.

You can pass the following entries in ``ls_specific_settings["lua"]``:
    - lua_language_server_version: Override the pinned lua-language-server version
      downloaded by Serena (default: the bundled Serena version).
"""

import logging
import os
import pathlib
import platform
import shutil
from collections.abc import Hashable
from pathlib import Path

from overrides import override

from solidlsp.ls import RawDocumentSymbol, SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_types import SymbolKind
from solidlsp.ls_utils import FileUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

LUA_LS_ALLOWED_HOSTS = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_LUA_LS_VERSION = "3.15.0"
INITIAL_LUA_LS_SHA256_BY_ASSET = {
    "lua-language-server-3.15.0-linux-x64.tar.gz": "4877b874c52fb7587707898da9026cc3a6c854d9bbab115ef49ac4e6a1b88007",
    "lua-language-server-3.15.0-linux-arm64.tar.gz": "7dff8edfed4f34cf6325ff384791287d95f9a8dd9615a5279c7c6af81cf8c45d",
    "lua-language-server-3.15.0-darwin-x64.tar.gz": "01d28a31e264434e51662814a68f584af068393caecfa158c4df5f7fdc3ca2f7",
    "lua-language-server-3.15.0-darwin-arm64.tar.gz": "050f5f493f65112afc116e31281a9f73918546782d3696485dc052724838f58b",
    "lua-language-server-3.15.0-win32-x64.zip": "76a10c05e8c947a448f00a61acead4240484cd1e2e8c66d54401c67d99b77535",
}
DEFAULT_LUA_LS_VERSION = "3.15.0"
DEFAULT_LUA_LS_SHA256_BY_ASSET = {
    "lua-language-server-3.15.0-linux-x64.tar.gz": "4877b874c52fb7587707898da9026cc3a6c854d9bbab115ef49ac4e6a1b88007",
    "lua-language-server-3.15.0-linux-arm64.tar.gz": "7dff8edfed4f34cf6325ff384791287d95f9a8dd9615a5279c7c6af81cf8c45d",
    "lua-language-server-3.15.0-darwin-x64.tar.gz": "01d28a31e264434e51662814a68f584af068393caecfa158c4df5f7fdc3ca2f7",
    "lua-language-server-3.15.0-darwin-arm64.tar.gz": "050f5f493f65112afc116e31281a9f73918546782d3696485dc052724838f58b",
    "lua-language-server-3.15.0-win32-x64.zip": "76a10c05e8c947a448f00a61acead4240484cd1e2e8c66d54401c67d99b77535",
}


def _lua_ls_sha(version: str, asset_name: str) -> str | None:
    if version == INITIAL_LUA_LS_VERSION:
        return INITIAL_LUA_LS_SHA256_BY_ASSET.get(asset_name)
    if version == DEFAULT_LUA_LS_VERSION:
        return DEFAULT_LUA_LS_SHA256_BY_ASSET.get(asset_name)
    return None


def _lua_ls_install_dir(ls_resources_dir: str, version: str) -> Path:
    # legacy unversioned dir reserved for INITIAL; every other version goes into a versioned subdir
    if version == INITIAL_LUA_LS_VERSION:
        return Path(ls_resources_dir) / "lua"
    return Path(ls_resources_dir) / f"lua-{version}"


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
    def _get_lua_ls_path(solidlsp_settings: SolidLSPSettings | None = None) -> str | None:
        """Get the path to lua-language-server executable."""
        # First check if it's in PATH
        lua_ls = shutil.which("lua-language-server")
        if lua_ls:
            return lua_ls

        # Check common installation locations
        home = Path.home()
        possible_paths = [
            home / ".local" / "bin" / "lua-language-server",
            Path("/usr/local/bin/lua-language-server"),
            Path("/opt/lua-language-server/bin/lua-language-server"),
        ]

        if solidlsp_settings is not None:
            lua_settings = solidlsp_settings.get_ls_specific_settings(Language.LUA)
            lua_ls_version = lua_settings.get("lua_language_server_version", DEFAULT_LUA_LS_VERSION)
            ls_resource_dir = _lua_ls_install_dir(LuaLanguageServer.ls_resources_dir(solidlsp_settings), lua_ls_version)
            possible_paths.extend(
                [
                    ls_resource_dir / "bin" / "lua-language-server",
                    ls_resource_dir / "bin" / "lua-language-server.exe",
                ]
            )

        # Add Windows-specific paths
        if platform.system() == "Windows":
            possible_paths.extend(
                [
                    home / "AppData" / "Local" / "lua-language-server" / "bin" / "lua-language-server.exe",
                ]
            )

        for path in possible_paths:
            if path.exists():
                return str(path)

        return None

    @staticmethod
    def _download_lua_ls(solidlsp_settings: SolidLSPSettings) -> str:
        """Download and install lua-language-server if not present."""
        lua_settings = solidlsp_settings.get_ls_specific_settings(Language.LUA)
        lua_ls_version = lua_settings.get("lua_language_server_version", DEFAULT_LUA_LS_VERSION)
        system = platform.system()
        machine = platform.machine().lower()

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

        install_dir = _lua_ls_install_dir(LuaLanguageServer.ls_resources_dir(solidlsp_settings), lua_ls_version)
        install_dir.mkdir(parents=True, exist_ok=True)

        log.info("Downloading lua-language-server from %s", download_url)
        archive_type = "gztar" if download_name.endswith(".tar.gz") else "zip"
        FileUtils.download_and_extract_archive_verified(
            download_url,
            str(install_dir),
            archive_type,
            expected_sha256=_lua_ls_sha(lua_ls_version, download_name),
            allowed_hosts=LUA_LS_ALLOWED_HOSTS,
        )

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
    def _setup_runtime_dependency(solidlsp_settings: SolidLSPSettings) -> str:
        """
        Check if required Lua runtime dependencies are available.
        Downloads lua-language-server if not present.
        """
        lua_ls_path = LuaLanguageServer._get_lua_ls_path(solidlsp_settings)

        if not lua_ls_path:
            log.info("lua-language-server not found. Downloading...")
            lua_ls_path = LuaLanguageServer._download_lua_ls(solidlsp_settings)
            log.info("lua-language-server installed at: %s", lua_ls_path)

        return lua_ls_path

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        lua_ls_path = self._setup_runtime_dependency(solidlsp_settings)

        super().__init__(
            config, repository_root_path, ProcessLaunchInfo(cmd=lua_ls_path, cwd=repository_root_path), "lua", solidlsp_settings
        )
        self.request_id = 0

    @override
    def _document_symbols_cache_fingerprint(self) -> Hashable:
        normalize_symbol_name_version = 1
        return normalize_symbol_name_version

    @override
    def _normalize_symbol_name(self, symbol: RawDocumentSymbol, relative_file_path: str) -> str:
        original_name = symbol["name"]

        if symbol.get("kind") not in (SymbolKind.Function, SymbolKind.Method):
            return original_name

        if "." in original_name:
            return original_name.rsplit(".", 1)[-1]

        if ":" in original_name:
            return original_name.rsplit(":", 1)[-1]

        return original_name

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

        # Lua Language Server is typically ready immediately after initialization
        # (no need to wait for events)
