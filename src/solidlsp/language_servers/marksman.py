"""
Provides Markdown specific instantiation of the LanguageServer class using marksman.
Contains various configurations and settings specific to Markdown.
"""

import logging
import os
import pathlib
from collections.abc import Hashable

from overrides import override

from solidlsp.ls import (
    DocumentSymbols,
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    LSPFileBuffer,
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_types import SymbolKind, UnifiedSymbolInformation
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)

MARKSMAN_ALLOWED_HOSTS = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_MARKSMAN_VERSION = "2024-12-18"
INITIAL_MARKSMAN_SHA256_BY_PLATFORM = {
    "linux-x64": "b9cb666c643dfd9b699811fdfc445ed4c56be65c1d878c21d46847f0d7b0e475",
    "linux-arm64": "b8d6972a56f3f9b7bbbf7c77ef8998e3b66fa82fb03c01398e224144486c9e73",
    "osx-x64": "7e18803966231a33ee107d0d26f69b41f2f0dc1332c52dd9729c2e29fb77be83",
    "osx-arm64": "7e18803966231a33ee107d0d26f69b41f2f0dc1332c52dd9729c2e29fb77be83",
    "win-x64": "39de9df039c8b0d627ac5918a9d8792ad20fc49e2461d1f5c906975c016799ec",
}
DEFAULT_MARKSMAN_VERSION = "2024-12-18"
DEFAULT_MARKSMAN_SHA256_BY_PLATFORM = {
    "linux-x64": "b9cb666c643dfd9b699811fdfc445ed4c56be65c1d878c21d46847f0d7b0e475",
    "linux-arm64": "b8d6972a56f3f9b7bbbf7c77ef8998e3b66fa82fb03c01398e224144486c9e73",
    "osx-x64": "7e18803966231a33ee107d0d26f69b41f2f0dc1332c52dd9729c2e29fb77be83",
    "osx-arm64": "7e18803966231a33ee107d0d26f69b41f2f0dc1332c52dd9729c2e29fb77be83",
    "win-x64": "39de9df039c8b0d627ac5918a9d8792ad20fc49e2461d1f5c906975c016799ec",
}


def _marksman_sha(version: str, platform_key: str) -> str | None:
    if version == INITIAL_MARKSMAN_VERSION:
        return INITIAL_MARKSMAN_SHA256_BY_PLATFORM[platform_key]
    if version == DEFAULT_MARKSMAN_VERSION:
        return DEFAULT_MARKSMAN_SHA256_BY_PLATFORM[platform_key]
    return None


class Marksman(SolidLanguageServer):
    """
    Provides Markdown specific instantiation of the LanguageServer class using marksman.

    You can pass the following entries in ``ls_specific_settings["markdown"]``:
        - marksman_version: Override the pinned Marksman release tag downloaded by
          Serena (default: the bundled Serena version).
    """

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        @classmethod
        def _runtime_dependencies(cls, version: str) -> RuntimeDependencyCollection:
            marksman_releases = f"https://github.com/artempyanykh/marksman/releases/download/{version}"
            return RuntimeDependencyCollection(
                [
                    RuntimeDependency(
                        id="marksman",
                        url=f"{marksman_releases}/marksman-linux-x64",
                        platform_id="linux-x64",
                        archive_type="binary",
                        binary_name="marksman",
                        sha256=_marksman_sha(version, "linux-x64"),
                        allowed_hosts=MARKSMAN_ALLOWED_HOSTS,
                    ),
                    RuntimeDependency(
                        id="marksman",
                        url=f"{marksman_releases}/marksman-linux-arm64",
                        platform_id="linux-arm64",
                        archive_type="binary",
                        binary_name="marksman",
                        sha256=_marksman_sha(version, "linux-arm64"),
                        allowed_hosts=MARKSMAN_ALLOWED_HOSTS,
                    ),
                    RuntimeDependency(
                        id="marksman",
                        url=f"{marksman_releases}/marksman-macos",
                        platform_id="osx-x64",
                        archive_type="binary",
                        binary_name="marksman",
                        sha256=_marksman_sha(version, "osx-x64"),
                        allowed_hosts=MARKSMAN_ALLOWED_HOSTS,
                    ),
                    RuntimeDependency(
                        id="marksman",
                        url=f"{marksman_releases}/marksman-macos",
                        platform_id="osx-arm64",
                        archive_type="binary",
                        binary_name="marksman",
                        sha256=_marksman_sha(version, "osx-arm64"),
                        allowed_hosts=MARKSMAN_ALLOWED_HOSTS,
                    ),
                    RuntimeDependency(
                        id="marksman",
                        url=f"{marksman_releases}/marksman.exe",
                        platform_id="win-x64",
                        archive_type="binary",
                        binary_name="marksman.exe",
                        sha256=_marksman_sha(version, "win-x64"),
                        allowed_hosts=MARKSMAN_ALLOWED_HOSTS,
                    ),
                ]
            )

        def _get_or_install_core_dependency(self) -> str:
            """Setup runtime dependencies for marksman and return the command to start the server."""
            marksman_version = self._custom_settings.get("marksman_version", DEFAULT_MARKSMAN_VERSION)
            deps = self._runtime_dependencies(marksman_version)
            dependency = deps.get_single_dep_for_current_platform()

            # legacy unversioned dir reserved for INITIAL; every other version goes into a versioned subdir
            marksman_ls_dir = (
                self._ls_resources_dir
                if marksman_version == INITIAL_MARKSMAN_VERSION
                else os.path.join(self._ls_resources_dir, f"marksman-{marksman_version}")
            )
            marksman_executable_path = deps.binary_path(marksman_ls_dir)
            if not os.path.exists(marksman_executable_path):
                log.info(
                    f"Downloading marksman from {dependency.url} to {marksman_ls_dir}",
                )
                deps.install(marksman_ls_dir)
            if not os.path.exists(marksman_executable_path):
                raise FileNotFoundError(f"Download failed? Could not find marksman executable at {marksman_executable_path}")
            os.chmod(marksman_executable_path, 0o755)
            return marksman_executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "server"]

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a Marksman instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            "markdown",
            solidlsp_settings,
        )

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["node_modules", ".obsidian", ".vitepress", ".vuepress"]

    def _document_symbols_cache_fingerprint(self) -> Hashable | None:
        request_document_symbols_override_version = 1
        return request_document_symbols_override_version

    @override
    def request_document_symbols(self, relative_file_path: str, file_buffer: LSPFileBuffer | None = None) -> DocumentSymbols:
        """Override to remap Marksman's heading symbol kinds from String to Namespace.

        Marksman LSP returns all markdown headings (h1-h6) with SymbolKind.String (15).
        This is problematic because String (15) >= Variable (13), so headings are
        classified as "low-level" and filtered out of symbol overviews.
        Remapping to Namespace (3) fixes this and is semantically appropriate
        (headings are named sections containing other content).
        """
        document_symbols = super().request_document_symbols(relative_file_path, file_buffer=file_buffer)

        # NOTE: When changing this method, also update the cache fingerprint method above

        def remap_heading_kinds(symbol: UnifiedSymbolInformation) -> None:
            if symbol["kind"] == SymbolKind.String:
                symbol["kind"] = SymbolKind.Namespace
            for child in symbol.get("children", []):
                remap_heading_kinds(child)

        for sym in document_symbols.root_symbols:
            remap_heading_kinds(sym)

        return document_symbols

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Marksman Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params: InitializeParams = {  # type: ignore
            "processId": os.getpid(),
            "locale": "en",
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},  # type: ignore[arg-type]
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},  # type: ignore[list-item]
                    "codeAction": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }
        return initialize_params

    def _start_server(self) -> None:
        """
        Starts the Marksman Language Server and waits for it to be ready.
        """

        def register_capability_handler(_params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(_params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting marksman server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to marksman server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response from marksman server: {init_response}")

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]

        self.server.notify.initialized({})

        # marksman is typically ready immediately after initialization
        log.info("Marksman server initialization complete")
