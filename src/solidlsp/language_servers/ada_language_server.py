"""
Provides Ada / SPARK specific instantiation of the LanguageServer class using
AdaCore's Ada Language Server (ALS).

ALS handles both Ada and SPARK code transparently — SPARK is identified by
pragmas/aspects in source rather than file extension, so a single
``Language.ADA`` covers both.
"""

import logging
import os
import pathlib
import threading
from typing import cast

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)

# Bumped on upgrades; install dir is namespaced by version so old caches stay valid.
DEFAULT_ALS_VERSION = "2026.2.202604091"
DEFAULT_ALS_SHA256_BY_PLATFORM = {
    "osx-arm64": "1d25ded29b6beafcb34c9d0084d52809d84577356e467bf92e8fef32fc4216c4",
    "osx-x64": "18d3277a25a6e08ce3ee7230c3e5ac20419d573cb8d8c883e7983f387a67d223",
    "linux-arm64": "65c57df715df90f7581ecd6a1d1884663376baaf38cedbab80d10060ff91b03d",
    "linux-x64": "2eb436a7c0e3740128cceaa15da9ff856fa75ef3fbb3e2e9d3a1bd17e15cb949",
    "win-x64": "bca024dc3643b2d91aebbb747398e2e6f183ad8cb2f149e24fe7a38cdb16ed8d",
}


def _als_sha(version: str, platform_key: str) -> str | None:
    if version == DEFAULT_ALS_VERSION:
        return DEFAULT_ALS_SHA256_BY_PLATFORM[platform_key]
    return None


# AdaCore's tarballs are downloaded directly from github.com release URLs;
# GitHub redirects asset downloads through release-assets/objects subdomains.
ALS_ALLOWED_HOSTS = (
    "github.com",
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
)

# Each AdaCore tarball nests the binary under integration/vscode/ada/{arch}/{os}/...
# alongside any bundled shared libraries (e.g. libgmp on macOS).
_BIN_RELPATH_BY_PLATFORM = {
    "osx-arm64": "integration/vscode/ada/arm64/darwin/ada_language_server",
    "osx-x64": "integration/vscode/ada/x64/darwin/ada_language_server",
    "linux-arm64": "integration/vscode/ada/arm64/linux/ada_language_server",
    "linux-x64": "integration/vscode/ada/x64/linux/ada_language_server",
    "win-x64": "integration/vscode/ada/x64/win32/ada_language_server.exe",
}

# AdaCore uses "darwin"/"win32" in asset names; remap from Serena's platform ids.
_ASSET_SUFFIX_BY_PLATFORM = {
    "osx-arm64": "darwin-arm64",
    "osx-x64": "darwin-x64",
    "linux-arm64": "linux-arm64",
    "linux-x64": "linux-x64",
    "win-x64": "win32-x64",
}


class AdaLanguageServer(SolidLanguageServer):
    """
    Provides Ada / SPARK specific instantiation of the LanguageServer class
    using AdaCore's Ada Language Server.

    You can pass the following entries in ``ls_specific_settings["ada"]``:
        - ls_path: Absolute path to a pre-installed ``ada_language_server``
          executable. If set, Serena does not download ALS and uses this
          binary directly. Useful for users who already have ALS available
          via Alire (``alr install ada_language_server``), GNAT Studio, or
          the Ada VS Code extension.
        - als_version: Override the pinned ALS version downloaded by Serena
          (default: the bundled Serena version). Setting this requires
          ``ls_path`` since custom-version SHA256 sums are unknown.
    """

    ALS_ALLOWED_HOSTS = ALS_ALLOWED_HOSTS

    # GNAT default output directories — pruned during workspace traversal.
    _IGNORED_DIRS = frozenset({"obj", "lib", ".obj", ".objects"})

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in self._IGNORED_DIRS

    @classmethod
    def _runtime_dependencies(cls, version: str) -> RuntimeDependencyCollection:
        base_url = f"https://github.com/AdaCore/ada_language_server/releases/download/{version}"
        return RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="ada-language-server",
                    description=f"Ada Language Server for {platform_key}",
                    url=f"{base_url}/als-{version}-{_ASSET_SUFFIX_BY_PLATFORM[platform_key]}.tar.gz",
                    platform_id=platform_key,
                    archive_type="gztar",
                    binary_name=_BIN_RELPATH_BY_PLATFORM[platform_key],
                    sha256=_als_sha(version, platform_key),
                    allowed_hosts=ALS_ALLOWED_HOSTS,
                )
                for platform_key in _BIN_RELPATH_BY_PLATFORM
            ]
        )

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """Setup runtime dependencies for ALS and return the path to the executable."""
            als_version = self._custom_settings.get("als_version", DEFAULT_ALS_VERSION)
            deps = AdaLanguageServer._runtime_dependencies(als_version)
            dependency = deps.get_single_dep_for_current_platform()

            install_dir = os.path.join(self._ls_resources_dir, f"als-{als_version}")
            als_executable_path = deps.binary_path(install_dir)
            if not os.path.exists(als_executable_path):
                log.info(
                    "Downloading and extracting ada_language_server from %s to %s",
                    dependency.url,
                    install_dir,
                )
                deps.install(install_dir)
            if not os.path.exists(als_executable_path):
                raise FileNotFoundError(f"Download failed? Could not find ada_language_server executable at {als_executable_path}")
            os.chmod(als_executable_path, 0o755)
            return als_executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            # ALS speaks LSP over stdio by default; no flags needed.
            return [core_path]

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates an AdaLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            "ada",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    def _get_initialize_params(self) -> InitializeParams:
        """Returns the initialization params for the Ada Language Server."""
        repository_absolute_path = self.repository_root_path
        root_uri = pathlib.Path(repository_absolute_path).as_uri()

        result = {
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "capabilities": {
                "workspace": {
                    "applyEdit": True,
                    "workspaceEdit": {"documentChanges": True},
                    "symbol": {"symbolKind": {"valueSet": list(range(1, 27))}},
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                },
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "general": {"positionEncodings": ["utf-16"]},
            },
            "initializationOptions": {},
            "trace": "off",
            "workspaceFolders": [{"uri": root_uri, "name": os.path.basename(repository_absolute_path)}],
        }
        return cast(InitializeParams, result)

    def _start_server(self) -> None:
        """Start the Ada Language Server process and complete the LSP handshake."""

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
        self.server.on_notification("window/showMessage", do_nothing)

        log.info("Starting ada_language_server process")
        self.server.start()

        initialize_params = self._get_initialize_params()
        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        capabilities = init_response["capabilities"]
        assert "textDocumentSync" in capabilities, "ALS must support textDocumentSync"
        assert "definitionProvider" in capabilities, "ALS must support textDocument/definition"
        assert "documentSymbolProvider" in capabilities, "ALS must support textDocument/documentSymbol"
        assert "referencesProvider" in capabilities, "ALS must support textDocument/references"

        self.server.notify.initialized({})
        self.server_ready.set()
