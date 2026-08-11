"""
Provides Bazel/Starlark-specific instantiation of the LanguageServer class, using the
starpls language server (https://github.com/withered-magic/starpls).
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

# How to refresh the pinned SHA256s when bumping DEFAULT_STARPLS_VERSION:
#   gh release view <tag> --repo withered-magic/starpls --json assets \
#     --jq '.assets[] | select(.name | test("^starpls-(darwin|linux|windows)-[a-z0-9]+(\\.exe)?$")) | {name, digest}'
#   The `digest` field is `sha256:<hex>` — copy the hex portion into DEFAULT_STARPLS_SHA256_BY_PLATFORM
#   keyed by the Serena PlatformId (osx-arm64, osx-x64, linux-arm64, linux-x64, win-x64).
#   Note: upstream publishes no win-arm64 asset.
DEFAULT_STARPLS_VERSION = "v0.1.22"
DEFAULT_STARPLS_SHA256_BY_PLATFORM = {
    "osx-arm64": "675b7be4554e6c219b6774a6b814ec21061096e08ecdd8b8aeeaf3913eb20a4e",
    "osx-x64": "97967f041d950c1055664a8f1afc36b01c6793b2fb3af488fd20139720d32131",
    "linux-arm64": "55877ec4c3ff03e1d90d59c76f69a3a144b6c29688747c8ac4d77993e2eef1ad",
    "linux-x64": "7c661cdde0d1c026665086d07523d825671e29056276681616bb32d0273c5eab",
    "win-x64": "87626a4226ed2f3f0f9e573501731bbe225a53cf009df845ec547ee984a1857e",
}


def _starpls_sha(version: str, platform_key: str) -> str | None:
    if version == DEFAULT_STARPLS_VERSION:
        return DEFAULT_STARPLS_SHA256_BY_PLATFORM.get(platform_key)
    return None


STARPLS_ALLOWED_HOSTS = (
    "github.com",
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
)


class StarplsLanguageServer(SolidLanguageServer):
    """
    Provides a Bazel/Starlark-specific instantiation of the language server, driven by ``starpls``.

    Handles BUILD / BUILD.bazel / MODULE.bazel / WORKSPACE(.bazel|.bzlmod) files as well as
    ``.bzl`` and ``.star`` files; starpls determines the Starlark dialect from the file path
    server-side, so a uniform LSP language id suffices.

    Recognised entries in ``ls_specific_settings["starlark"]``:
        - ``ls_path``: Absolute path to a pre-installed ``starpls`` binary. Bypasses Serena's
          auto-download mechanism.
        - ``starpls_version``: Override the pinned starpls release tag downloaded by Serena
          (default: the version bundled with this Serena release). Non-default versions skip
          SHA256 verification.
        - ``bazel_path``: Path to the ``bazel`` (or bazelisk) executable that starpls uses to
          resolve external repositories (``@repo//...`` labels). If unset, starpls probes
          ``bazel`` on PATH; if that fails, startup continues gracefully — main-workspace
          label resolution (``//...``) works without bazel.

    Note: starpls (as of v0.1.22) resolves ``textDocument/references`` only within the file
    the request is made in; go-to-definition works across files (including through ``load()``).
    """

    STARPLS_ALLOWED_HOSTS = STARPLS_ALLOWED_HOSTS

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # Bazel creates convenience symlinks (bazel-bin, bazel-out, bazel-testlogs,
        # bazel-<workspacename>) at the workspace root that point into the output base.
        # Serena's directory scanner follows symlinks, so without this rule a traversal
        # would leak into Bazel's (potentially huge) output tree.
        return super().is_ignored_dirname(dirname) or dirname.startswith("bazel-")

    @classmethod
    def _runtime_dependencies(cls, version: str) -> RuntimeDependencyCollection:
        starpls_releases = f"https://github.com/withered-magic/starpls/releases/download/{version}"
        return RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="starpls",
                    url=f"{starpls_releases}/starpls-darwin-arm64",
                    platform_id="osx-arm64",
                    archive_type="binary",
                    binary_name="starpls",
                    sha256=_starpls_sha(version, "osx-arm64"),
                    allowed_hosts=STARPLS_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="starpls",
                    url=f"{starpls_releases}/starpls-darwin-amd64",
                    platform_id="osx-x64",
                    archive_type="binary",
                    binary_name="starpls",
                    sha256=_starpls_sha(version, "osx-x64"),
                    allowed_hosts=STARPLS_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="starpls",
                    url=f"{starpls_releases}/starpls-linux-aarch64",
                    platform_id="linux-arm64",
                    archive_type="binary",
                    binary_name="starpls",
                    sha256=_starpls_sha(version, "linux-arm64"),
                    allowed_hosts=STARPLS_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="starpls",
                    url=f"{starpls_releases}/starpls-linux-amd64",
                    platform_id="linux-x64",
                    archive_type="binary",
                    binary_name="starpls",
                    sha256=_starpls_sha(version, "linux-x64"),
                    allowed_hosts=STARPLS_ALLOWED_HOSTS,
                ),
                # NOTE: upstream publishes no windows-arm64 asset; win-arm64 users must
                # provide ls_path (get_single_dep_for_current_platform raises otherwise).
                RuntimeDependency(
                    id="starpls",
                    url=f"{starpls_releases}/starpls-windows-amd64.exe",
                    platform_id="win-x64",
                    archive_type="binary",
                    binary_name="starpls.exe",
                    sha256=_starpls_sha(version, "win-x64"),
                    allowed_hosts=STARPLS_ALLOWED_HOSTS,
                ),
            ]
        )

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """Creates a StarplsLanguageServer instance.

        Not meant to be instantiated directly — use :meth:`SolidLanguageServer.create` instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            "starlark",  # uniform languageId; starpls derives the dialect from the file path
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        """Resolves a ``starpls`` executable, downloading the pinned release if it isn't cached yet."""

        def _get_or_install_core_dependency(self) -> str:
            starpls_version = self._custom_settings.get("starpls_version", DEFAULT_STARPLS_VERSION)
            deps = StarplsLanguageServer._runtime_dependencies(starpls_version)
            dependency = deps.get_single_dep_for_current_platform()

            install_dir = os.path.join(self._ls_resources_dir, f"starpls-{starpls_version}")
            starpls_executable_path = deps.binary_path(install_dir)
            if not os.path.exists(starpls_executable_path):
                log.info(f"Downloading starpls from {dependency.url} to {install_dir}")
                deps.install(install_dir)
            if not os.path.exists(starpls_executable_path):
                raise FileNotFoundError(f"Download failed? Could not find starpls executable at {starpls_executable_path}")
            os.chmod(starpls_executable_path, 0o755)
            return starpls_executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            # starpls speaks LSP over stdio via the `server` subcommand.
            cmd = [core_path, "server"]
            bazel_path = self._custom_settings.get("bazel_path")
            if bazel_path:
                cmd += ["--bazel_path", str(bazel_path)]
            return cmd

    @override
    def _supports_pull_diagnostics(self) -> bool:
        # starpls does not implement `textDocument/diagnostic`; diagnostics arrive via
        # `textDocument/publishDiagnostics` (push), which the base class collects.
        return False

    def _create_base_initialize_params(self) -> dict:
        """Returns the init params for starpls (it only consumes ``capabilities``)."""
        return {
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "publishDiagnostics": {"relatedInformation": True},
                    "definition": {"linkSupport": True, "dynamicRegistration": True},
                    "declaration": {"linkSupport": True, "dynamicRegistration": True},
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
                    "signatureHelp": {"dynamicRegistration": True},
                },
                "window": {"workDoneProgress": True},
                "general": {"positionEncodings": ["utf-16"]},
            },
            "initializationOptions": {},
            "trace": "off",
        }

    def _start_server(self) -> None:
        def register_capability_handler(params: dict) -> None:
            return

        def work_done_progress_create_handler(params: dict) -> None:
            # starpls creates progress tokens when fetching external Bazel repositories;
            # an unanswered server->client request could block its event loop.
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def window_show_message(msg: dict) -> None:
            # Includes the non-fatal "Failed to fetch Bazel configuration!" notice when
            # bazel is unavailable — informational for Serena's purposes.
            log.info(f"LSP: window/showMessage: {msg}")

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("window/workDoneProgress/create", work_done_progress_create_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("window/showMessage", window_show_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting starpls server process")
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
        # starpls serves requests immediately after the initialized notification
        # (requests received during its Bazel probe are queued, not dropped)
        self.server_ready.set()
