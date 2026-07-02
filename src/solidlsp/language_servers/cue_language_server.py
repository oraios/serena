"""
Provides CUE-specific instantiation of the LanguageServer class, using the LSP mode of the
``cue`` CLI (``cue lsp``) from the official CUE distribution.
"""

from __future__ import annotations

import logging
import os
import threading

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)

# How to refresh the pinned SHA256s when bumping DEFAULT_CUE_VERSION:
#   gh release view <tag> --repo cue-lang/cue --json assets \
#     --jq '.assets[] | select(.name | test("(darwin|linux|windows)_(amd64|arm64)")) | {name, digest}'
#   The `digest` field is `sha256:<hex>` — copy the hex portion into DEFAULT_CUE_SHA256_BY_PLATFORM
#   keyed by the Serena PlatformId (osx-arm64, osx-x64, linux-arm64, linux-x64, win-x64, win-arm64).
DEFAULT_CUE_VERSION = "v0.16.1"
DEFAULT_CUE_SHA256_BY_PLATFORM = {
    "osx-arm64": "a72b0cddb377c52d1b003bed9a335d893b70cd75a182cd5e3fee8bae30ddb6d6",
    "osx-x64": "97b0d78e4c5ee49ff72145fd6ef4f4bab0bb332d55f29660de3fec2af5ec96a9",
    "linux-arm64": "3cc715a9e969f87b93c4fa34cfaef5388b93e96efa20b248e8ad6826abd25a83",
    "linux-x64": "5d644c1305a2b86504c8dcd2ec829cf5b4999efc2cf51ee375624e0455f774ae",
    "win-x64": "2f24123f458229fcf283db534bd86692ad1074da806defee0f0cc62976c0397c",
    "win-arm64": "e0c15ce53f73e8609b0e8ce6507298f3474b334ac5eb0c826c9497a811fd0cce",
}


def _cue_sha(version: str, platform_key: str) -> str | None:
    if version == DEFAULT_CUE_VERSION:
        return DEFAULT_CUE_SHA256_BY_PLATFORM.get(platform_key)
    return None


CUE_ALLOWED_HOSTS = (
    "github.com",
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
)


class CueLanguageServer(SolidLanguageServer):
    """
    Provides a CUE-specific instantiation of the language server, driven by ``cue lsp`` from the
    official CUE CLI distribution.

    Recognised entries in ``ls_specific_settings["cue"]``:
        - ``ls_path``: Absolute path to a pre-installed ``cue`` binary. Bypasses Serena's
          auto-download mechanism; useful when the user already has ``cue`` on ``$PATH``
          (e.g. via ``brew install cue`` or ``go install``).
        - ``cue_version``: Override the pinned cue version downloaded by Serena
          (default: the bundled Serena version). Setting this to a version other than
          ``DEFAULT_CUE_VERSION`` skips SHA256 verification (checksums for arbitrary
          versions are unknown), so pair it with ``ls_path`` if integrity matters.
    """

    CUE_ALLOWED_HOSTS = CUE_ALLOWED_HOSTS

    # Directories worth pruning for CUE projects. cue.mod/gen/ contains generated Go->CUE
    # bindings that shouldn't be traversed for symbolic operations; cue.mod/pkg/ holds
    # fetched module dependencies (analogous to node_modules / vendor).
    _IGNORED_DIRS = frozenset({"cue.mod/gen", "cue.mod/pkg"})

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in self._IGNORED_DIRS

    @classmethod
    def _runtime_dependencies(cls, version: str) -> RuntimeDependencyCollection:
        """Builds the platform-specific runtime dependency set for the given cue release.

        :param version: the cue release tag (e.g. ``v0.16.1``); the leading ``v`` is stripped when
            constructing the archive filename, since cue releases embed the bare version there.
        """
        version_no_v = version.lstrip("v")
        cue_releases = f"https://github.com/cue-lang/cue/releases/download/{version}"
        return RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="cue",
                    url=f"{cue_releases}/cue_v{version_no_v}_darwin_arm64.tar.gz",
                    platform_id="osx-arm64",
                    archive_type="gztar",
                    binary_name="cue",
                    sha256=_cue_sha(version, "osx-arm64"),
                    allowed_hosts=CUE_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="cue",
                    url=f"{cue_releases}/cue_v{version_no_v}_darwin_amd64.tar.gz",
                    platform_id="osx-x64",
                    archive_type="gztar",
                    binary_name="cue",
                    sha256=_cue_sha(version, "osx-x64"),
                    allowed_hosts=CUE_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="cue",
                    url=f"{cue_releases}/cue_v{version_no_v}_linux_arm64.tar.gz",
                    platform_id="linux-arm64",
                    archive_type="gztar",
                    binary_name="cue",
                    sha256=_cue_sha(version, "linux-arm64"),
                    allowed_hosts=CUE_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="cue",
                    url=f"{cue_releases}/cue_v{version_no_v}_linux_amd64.tar.gz",
                    platform_id="linux-x64",
                    archive_type="gztar",
                    binary_name="cue",
                    sha256=_cue_sha(version, "linux-x64"),
                    allowed_hosts=CUE_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="cue",
                    url=f"{cue_releases}/cue_v{version_no_v}_windows_amd64.zip",
                    platform_id="win-x64",
                    archive_type="zip",
                    binary_name="cue.exe",
                    sha256=_cue_sha(version, "win-x64"),
                    allowed_hosts=CUE_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="cue",
                    url=f"{cue_releases}/cue_v{version_no_v}_windows_arm64.zip",
                    platform_id="win-arm64",
                    archive_type="zip",
                    binary_name="cue.exe",
                    sha256=_cue_sha(version, "win-arm64"),
                    allowed_hosts=CUE_ALLOWED_HOSTS,
                ),
            ]
        )

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """Creates a CueLanguageServer instance.

        Not meant to be instantiated directly — use :meth:`SolidLanguageServer.create` instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            "cue",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        """Resolves a ``cue`` executable, downloading the pinned release if it isn't cached yet."""

        def _get_or_install_core_dependency(self) -> str:
            cue_version = self._custom_settings.get("cue_version", DEFAULT_CUE_VERSION)
            deps = CueLanguageServer._runtime_dependencies(cue_version)
            dependency = deps.get_single_dep_for_current_platform()

            install_dir = os.path.join(self._ls_resources_dir, f"cue-{cue_version}")
            cue_executable_path = deps.binary_path(install_dir)
            if not os.path.exists(cue_executable_path):
                log.info(f"Downloading and extracting cue from {dependency.url} to {install_dir}")
                deps.install(install_dir)
            if not os.path.exists(cue_executable_path):
                raise FileNotFoundError(f"Download failed? Could not find cue executable at {cue_executable_path}")
            os.chmod(cue_executable_path, 0o755)
            return cue_executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            # cue's LSP mode is activated via the `lsp` subcommand; it speaks LSP over stdio.
            return [core_path, "lsp"]

    def _create_base_initialize_params(self) -> dict:
        """Returns the init params for ``cue lsp``."""
        result = {
            "capabilities": {
                "workspace": {
                    "applyEdit": True,
                    "workspaceEdit": {"documentChanges": True},
                    "symbol": {"symbolKind": {"valueSet": list(range(1, 27))}},
                    "workspaceFolders": True,
                    "configuration": True,
                },
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "publishDiagnostics": {"relatedInformation": True, "tagSupport": {"valueSet": [1, 2]}},
                    "definition": {"linkSupport": True, "dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "hover": {"contentFormat": ["markdown", "plaintext"], "dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {"snippetSupport": False, "documentationFormat": ["markdown", "plaintext"]},
                    },
                },
                "general": {"positionEncodings": ["utf-16"]},
            },
            "initializationOptions": {},
            "trace": "off",
        }
        return result

    def _start_server(self) -> None:
        def register_capability_handler(params: dict) -> None:
            return

        def workspace_configuration_handler(params: dict) -> list[dict]:
            # cue lsp asks the client for its configuration shortly after initialization
            # and will not start servicing requests until it gets a reply. We return an
            # empty object per requested item — cue's defaults are fine for our use.
            items = params.get("items", []) if isinstance(params, dict) else []
            return [{} for _ in items]

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(params: dict) -> None:
            return

        # wire up notification/request handlers before starting the process
        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("workspace/configuration", workspace_configuration_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting cue lsp server process")
        self.server.start()

        initialize_params = self._create_initialize_params()

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # sanity-check the server advertises the core capabilities we rely on
        capabilities = init_response["capabilities"]
        assert "textDocumentSync" in capabilities
        assert "definitionProvider" in capabilities
        assert "documentSymbolProvider" in capabilities
        assert "referencesProvider" in capabilities

        self.server.notify.initialized({})
        # cue lsp is ready to serve immediately after the initialized notification
        self.server_ready.set()
