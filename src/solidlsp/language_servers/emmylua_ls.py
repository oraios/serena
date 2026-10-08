"""
Provides an experimental Lua language server implementation using the Rust-based EmmyLua Analyzer (``emmylua_ls``).

The backend is deliberately separate from the default Lua Language Server so projects can
select it explicitly with ``language: lua_emmylua``.

You can pass the following entries in ``ls_specific_settings["lua_emmylua"]``:
    - ls_path: Use a custom ``emmylua_ls`` executable instead of the managed download.
    - emmylua_ls_version: Override the pinned EmmyLua Analyzer version downloaded by Serena
      (default: the bundled Serena version). Custom versions are not checksum-verified.
"""
# SPDX-License-Identifier: MIT

import logging
import os
import re
from collections.abc import Hashable
from typing import ClassVar

from overrides import override

from solidlsp.dependency_provider import (
    DownloadedDependency,
    DownloadedDependencyHashDatabase,
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
)
from solidlsp.ls import RawDocumentSymbol, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_types import SymbolKind
from solidlsp.ls_utils import FileUtils, PlatformId, PlatformUtils
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

EMMYLUA_LS_ALLOWED_HOSTS = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")

# NOTE: after bumping DEFAULT_EMMYLUA_LS_VERSION, re-run scripts/update_downloaded_dependency_hashes.py
# and commit the resulting changes to src/solidlsp/resources/downloaded_dependency_hashes.json; a stale
# hash database means unverified downloads locally and a CI failure.
DEFAULT_EMMYLUA_LS_VERSION = "0.25.1"

# EmmyLua Analyzer publishes one archive per platform: (asset name, archive type)
EMMYLUA_LS_ASSET_BY_PLATFORM_ID: dict[PlatformId, tuple[str, FileUtils.ArchiveType]] = {
    PlatformId.LINUX_x64: ("emmylua_ls-linux-x64-glibc.2.17.tar.gz", "gztar"),
    PlatformId.LINUX_arm64: ("emmylua_ls-linux-aarch64-glibc.2.17.tar.gz", "gztar"),
    PlatformId.OSX_x64: ("emmylua_ls-darwin-x64.tar.gz", "gztar"),
    PlatformId.OSX_arm64: ("emmylua_ls-darwin-arm64.tar.gz", "gztar"),
    PlatformId.WIN_x64: ("emmylua_ls-win32-x64.zip", "zip"),
    PlatformId.WIN_arm64: ("emmylua_ls-win32-arm64.zip", "zip"),
}


class EmmyLuaLanguageServer(SolidLanguageServer):
    """
    Experimental Lua language server backend using the Rust-based EmmyLua Analyzer (``emmylua_ls``).

    It is independent of the default Lua backend (``LuaLanguageServer``) and is selected
    explicitly via ``language: lua_emmylua``.
    """

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        """Downloads the pinned (or user-selected) ``emmylua_ls`` release for the current platform."""

        _SUPPORTED_PLATFORM_IDS: ClassVar[frozenset[PlatformId]] = frozenset(EMMYLUA_LS_ASSET_BY_PLATFORM_ID)

        @classmethod
        def _create_dep_emmylua_ls(cls, platform_id: PlatformId, emmylua_ls_version: str | None = None) -> DownloadedDependency:
            """
            :param platform_id: the platform for which to create the dependency
            :param emmylua_ls_version: the version to download; if None, use the pinned default version.
                Custom versions cannot be checksum-verified by design, as their hashes are not pinned.
            """
            emmylua_ls_version = emmylua_ls_version or DEFAULT_EMMYLUA_LS_VERSION
            asset_name, archive_type = EMMYLUA_LS_ASSET_BY_PLATFORM_ID[platform_id]
            return DownloadedDependency(
                url=f"https://github.com/EmmyLuaLs/emmylua-analyzer-rust/releases/download/{emmylua_ls_version}/{asset_name}",
                archive_type=archive_type,
                allowed_hosts=EMMYLUA_LS_ALLOWED_HOSTS,
                verified=emmylua_ls_version == DEFAULT_EMMYLUA_LS_VERSION,
            )

        @classmethod
        def update_dep_hashes(cls) -> None:
            deps = [cls._create_dep_emmylua_ls(platform_id) for platform_id in EMMYLUA_LS_ASSET_BY_PLATFORM_ID]
            with DownloadedDependencyHashDatabase.get_instance().update_context() as db:
                for dep in deps:
                    db.update(dep)

        def _get_or_install_core_dependency(self) -> str:
            """Return the managed ``emmylua_ls`` executable, downloading the release asset if necessary."""
            platform_id = PlatformUtils.get_platform_id()
            if platform_id not in self._SUPPORTED_PLATFORM_IDS:
                raise RuntimeError(
                    f"emmylua_ls is not available for platform {platform_id.value}. Install a compatible binary from "
                    "https://github.com/EmmyLuaLs/emmylua-analyzer-rust/releases and set "
                    "ls_specific_settings.lua_emmylua.ls_path."
                )

            emmylua_ls_version = self._custom_settings.get("emmylua_ls_version") or DEFAULT_EMMYLUA_LS_VERSION
            install_dir = os.path.join(self._ls_resources_dir, f"emmylua_ls-{emmylua_ls_version}-{platform_id.value}")
            executable_name = "emmylua_ls.exe" if platform_id.is_windows() else "emmylua_ls"
            executable_path = os.path.join(install_dir, executable_name)

            if not os.path.exists(executable_path):
                log.info("Downloading emmylua_ls %s for %s", emmylua_ls_version, platform_id.value)
                os.makedirs(install_dir, exist_ok=True)
                self._create_dep_emmylua_ls(platform_id, emmylua_ls_version).download_to(install_dir)

            if not os.path.exists(executable_path):
                raise FileNotFoundError(f"emmylua_ls executable not found at {executable_path} after installation")

            if not platform_id.is_windows():
                os.chmod(executable_path, 0o755)

            log.info("emmylua_ls binary ready at: %s", executable_path)
            return executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            # emmylua_ls communicates via stdio by default
            return [core_path]

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(config, repository_root_path, None, "lua", solidlsp_settings)

    @override
    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For Lua projects, we should ignore:
        # - .luarocks: package manager cache
        # - lua_modules: local dependencies
        # - node_modules: if the project has JavaScript components
        return super().is_ignored_dirname(dirname) or dirname in [".luarocks", "lua_modules", "node_modules", "build", "dist", ".cache"]

    @override
    def _document_symbols_cache_fingerprint(self) -> Hashable:
        normalize_symbol_name_version = 1
        return normalize_symbol_name_version

    @override
    def _normalize_symbol_name(self, symbol: RawDocumentSymbol, relative_file_path: str) -> str:
        """
        emmylua_ls reports module members with their qualifier (e.g. ``calculator.add`` or ``Animal:speak``).
        Serena expects the bare name, since the enclosing module/class is conveyed by the symbol hierarchy.
        """
        original_name = symbol["name"]

        if symbol.get("kind") not in (SymbolKind.Function, SymbolKind.Method):
            return original_name

        # strip any qualifier, e.g. "calculator.add", "Animal:speak" or "utils.Logger:new"
        return re.split(r"[.:]", original_name)[-1] or original_name

    def _create_base_initialize_params(self) -> dict:
        """Returns the server-specific initialize params for emmylua_ls."""
        return {
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
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"],
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
            "initializationOptions": {},
        }

    def _start_server(self) -> None:
        """Start the emmylua_ls process and perform the LSP handshake."""

        def register_capability_handler(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info("LSP: window/logMessage: %s", msg)

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting emmylua_ls server process")
        self.server.start()

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(self._create_initialize_params())

        # Verify the capabilities Serena relies on (explicit raises, since `assert` is stripped with `python -O`)
        capabilities = init_response["capabilities"]
        for required_capability in ("textDocumentSync", "definitionProvider", "documentSymbolProvider", "referencesProvider"):
            if required_capability not in capabilities:
                raise SolidLSPException(f"emmylua_ls did not advertise the required capability '{required_capability}'")

        self.server.notify.initialized({})
