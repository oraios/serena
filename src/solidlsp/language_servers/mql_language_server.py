"""
Provides MQL4/MQL5 specific instantiation of the LanguageServer class using
davalillo's mql-language-server.

A single server instance covers all MetaTrader dialects: ``LanguageServerId.MQL``
routes .mq4 (MQL4), .mq5 (MQL5), and .mqh (MQL5 include) files; the language id
sent to the server is chosen per file (mql4/mql5).
"""

import logging
import os
import platform
import threading
import time

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)

# GitHub redirects release asset downloads through these subdomains.
MQL_ALLOWED_HOSTS = (
    "github.com",
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
)

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
# At introduction both point to v2.0.0 with identical asset digests.
INITIAL_MQL_VERSION = "v2.0.0"
INITIAL_MQL_SHA256_BY_PLATFORM = {
    # sha256 values from the v2.0.0 release assets (GitHub release API + CHECKSUMS.txt)
    "linux-x64": "be0c1014dec89236570a6dcbe024c9a74337276f99f7274c86128e845447560c",
    "osx-x64": "034769254b17ed0dd837abb5507f11303656b3d6dfe1b95ef94ed15c74285810",
    "osx-arm64": "f7a0038aaf9d8df2bbdf1e3331bd21cb93c1e13108fe6de20ff68cc7e7ed8718",
    "win-x64": "dd11026e033fd2f703c4ca27fe6b730acc7283f1512dd165a546c59b270e730c",
}
DEFAULT_MQL_VERSION = "v2.0.1"
DEFAULT_MQL_SHA256_BY_PLATFORM = {
    # sha256 values from the v2.0.1 release CHECKSUMS.txt (GitHub release v2.0.1)
    "linux-x64": "493d4f900876653afe10bbcdfd769c4ddab9761e0bc2fb5cbff91338aa88e156",
    "osx-x64": "15f50e6305e051a9b01688c4904175503dfccd332e8166d824695af8542b6795",
    "osx-arm64": "2d9a5dd0a1a0a72bbf49a1ea77fc2c03cebb4d4983d55859dd7cafdd9590e265",
    "win-x64": "a3f4ef432fde7d9cd357b59fb0e60dc3c9530cb6ca31c6da4935eba8e50f0cdb",
}


def _mql_sha(version: str, platform_key: str) -> str | None:
    if version == INITIAL_MQL_VERSION:
        return INITIAL_MQL_SHA256_BY_PLATFORM[platform_key]
    if version == DEFAULT_MQL_VERSION:
        return DEFAULT_MQL_SHA256_BY_PLATFORM[platform_key]
    return None


# Release asset basenames per Serena platform id.
_ASSET_BASENAME_BY_PLATFORM = {
    "linux-x64": "mql-lsp-server-linux-x64",
    "osx-x64": "mql-lsp-server-osx-x64",
    "osx-arm64": "mql-lsp-server-osx-arm64",
    "win-x64": "mql-lsp-server-win-x64.exe",
}


class MqlLanguageServer(SolidLanguageServer):
    """
    Provides MQL4/MQL5 specific instantiation of the LanguageServer class
    using davalillo's mql-language-server.

    You can pass the following entries in ``ls_specific_settings["mql"]``:
        - mql_version: Override the pinned mql-language-server version
          downloaded by Serena (default: the bundled version). Custom-version
          SHA256 sums are unknown, so verification is skipped for them.
    """

    @override
    def _supports_pull_diagnostics(self) -> bool:
        # The underlying mql-lsp-server binary is push-only: it never registers the
        # `diagnosticProvider` capability and never answers ``textDocument/diagnostic``
        # requests. Sending the pull request leaves it pending forever, which deadlocks
        # the request pipe and wedges the whole MCP server. Force the
        # published-diagnostics path instead.
        return False

    @classmethod
    def _runtime_dependencies(cls, version: str) -> RuntimeDependencyCollection:
        base_url = f"https://github.com/davalillo/mql-language-server/releases/download/{version}"
        return RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="mql-lsp-server",
                    description=f"mql-language-server for {platform_key}",
                    url=f"{base_url}/{_ASSET_BASENAME_BY_PLATFORM[platform_key]}",
                    platform_id=platform_key,
                    archive_type="binary",
                    binary_name="mql-lsp-server.exe" if platform_key == "win-x64" else "mql-lsp-server",
                    sha256=_mql_sha(version, platform_key),
                    allowed_hosts=MQL_ALLOWED_HOSTS,
                )
                for platform_key in _ASSET_BASENAME_BY_PLATFORM
            ]
        )

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """Resolve the pinned mql-language-server version and return the executable path."""
            version = self._custom_settings.get("mql_version", DEFAULT_MQL_VERSION)
            deps = MqlLanguageServer._runtime_dependencies(version)
            dependency = deps.get_single_dep_for_current_platform()

            # legacy unversioned dir reserved for INITIAL; every other version gets a versioned subdir
            # so that a DEFAULT bump never silently reuses stale binaries
            # (at introduction INITIAL == DEFAULT, so the default install targets the
            # legacy dir — matching upstream marksman behavior at its own introduction)
            install_dir = (
                os.path.join(self._ls_resources_dir, "mql-lsp")
                if version == INITIAL_MQL_VERSION
                else os.path.join(self._ls_resources_dir, f"mql-lsp-{version}")
            )
            executable_path = deps.binary_path(install_dir)
            if not os.path.exists(executable_path):
                log.info("Downloading mql-lsp-server from %s to %s", dependency.url, install_dir)
                deps.install(install_dir)
            if not os.path.exists(executable_path):
                raise FileNotFoundError(f"Download failed? Could not find mql-lsp-server executable at {executable_path}")
            if platform.system() != "Windows":
                os.chmod(executable_path, 0o755)
            return executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            # the server speaks LSP over stdio by default; no flags needed
            return [core_path]

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates an MqlLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            "mql",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        """
        Maps file extensions to the server's language ids: MQL4 sources use
        ``mql4``, MQL5 sources and .mqh includes use ``mql5`` (MQL5 is the
        syntactic superset shared with include files).
        """
        if relative_file_path.lower().endswith(".mq4"):
            return "mql4"
        return "mql5"

    def _create_base_initialize_params(self) -> dict:
        """
        Returns the initialization params for the mql-language-server.
        """
        return {
            "capabilities": {
                "workspace": {
                    "applyEdit": True,
                    "workspaceEdit": {"documentChanges": True},
                    "symbol": {
                        "dynamicRegistration": False,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                },
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
                },
                "general": {"positionEncodings": ["utf-16"]},
            },
            "initializationOptions": {},
            "trace": "off",
        }

    def _start_server(self) -> None:
        """Start the mql-lsp-server process and complete the LSP handshake."""
        # the server sends no experimental/serverStatus notifications; readiness
        # is gated on the dynamically registered feature capabilities instead

        # dynamic registration server: the documentSymbol/definition/references/etc.
        # providers are advertised via client/registerCapability after `initialized`
        # (msl-style), so the top-level capabilities dict is empty and must not be asserted on
        capability_names: list[str] = []

        def register_capability_handler(params: dict) -> None:
            capability_names.extend(r.get("method", "") for r in params.get("registrations", []))

        def window_log_message(msg: dict) -> None:
            log.info("LSP: window/logMessage: %s", msg)

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("window/showMessage", do_nothing)

        log.info("Starting mql-lsp-server process")
        self.server.start()

        initialize_params = self._create_initialize_params()
        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        self.server.send.initialize(initialize_params)

        self.server.notify.initialized({})

        # the server registers its feature providers asynchronously after `initialized`;
        # wait for the Serena-relevant ones before reporting readiness
        required = {"textDocument/documentSymbol", "textDocument/definition", "textDocument/references", "textDocument/hover"}
        deadline = time.monotonic() + 10.0
        while not required.issubset(set(capability_names)) and time.monotonic() < deadline:
            time.sleep(0.1)
        missing = required - set(capability_names)
        assert not missing, f"mql-lsp-server did not register required capabilities within 10s: {sorted(missing)}"

        self.server_ready.set()
