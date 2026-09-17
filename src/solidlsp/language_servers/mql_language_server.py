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
import shutil
import threading
import time

import requests
from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)

# GitHub redirects release asset downloads through these subdomains.
MQL_ALLOWED_HOSTS = (
    "github.com",
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
)

# Max wall-clock time to wait for the server's dynamic capability registrations
# (client/registerCapability) after the initialized notification.
MQL_CAPABILITY_REGISTRATION_TIMEOUT_S = 10.0

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir once it diverges from INITIAL.
# At introduction both point to v2.2.0 with identical asset digests.
INITIAL_MQL_VERSION = "v2.2.0"
INITIAL_MQL_SHA256_BY_PLATFORM = {
    # sha256 values from the v2.2.0 release assets (GitHub release API + CHECKSUMS.txt, cross-verified)
    "linux-x64": "3fb345abf9e639881b54943ec3959909abe9085a09b39006b8b112c2f774e709",
    "osx-x64": "bce990fdd20a480f0b662ffa94cf5eaeb93211aee57f828ca9ef5c038799d507",
    "osx-arm64": "6ebeecb5373cddab6ddd20b53b2838e972f7fd77094be2a77940570fac5d4a47",
    "win-x64": "725bb43748b5a34da084297cdabdc533132266124bbcb2912bf18ead631bc1c2",
}
DEFAULT_MQL_VERSION = "v2.2.0"
DEFAULT_MQL_SHA256_BY_PLATFORM = INITIAL_MQL_SHA256_BY_PLATFORM
# Historical DEFAULT digests (kept forever, mirroring the INITIAL scheme: a user who
# overrides to any formerly-pinned version still gets hash verification). Empty at
# introduction; populated when a future DEFAULT bump supersedes a shipped version.
HISTORICAL_MQL_SHA256_BY_VERSION: dict[str, dict[str, str]] = {}


def _mql_sha(version: str, platform_key: str) -> str | None:
    if version == INITIAL_MQL_VERSION:
        return INITIAL_MQL_SHA256_BY_PLATFORM[platform_key]
    if version == DEFAULT_MQL_VERSION:
        return DEFAULT_MQL_SHA256_BY_PLATFORM[platform_key]
    historical = HISTORICAL_MQL_SHA256_BY_VERSION.get(version)
    if historical is not None:
        return historical[platform_key]
    return None


def _fetch_release_checksums(version: str) -> dict[str, str]:
    """Fetches the ``CHECKSUMS.txt`` asset of a release as a ``{asset basename: sha256}`` map.

    Every mql-language-server release ships a ``CHECKSUMS.txt`` with one
    ``<sha256>  ./<asset basename>`` line per asset (comment lines starting with
    ``#`` are ignored). Used to verify custom ``mql_version`` overrides that have
    no locally pinned digest; callers must treat a missing/failed fetch as
    unverifiable rather than skipping integrity checks silently.
    """
    url = f"https://github.com/davalillo/mql-language-server/releases/download/{version}/CHECKSUMS.txt"
    response: requests.Response | None = None
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        checksums: dict[str, str] = {}
        for raw_line in response.text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) != 2:
                continue
            sha, filename = parts
            checksums[filename.lstrip("./")] = sha
        return checksums
    except requests.RequestException as ex:
        raise SolidLSPException(f"Could not fetch CHECKSUMS.txt for mql-language-server {version}: {ex}") from ex
    finally:
        if response is not None:
            response.close()


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
          downloaded by Serena (default: the bundled version). Custom versions
          are verified against the release's own CHECKSUMS.txt; if that file
          cannot be fetched, the install is refused.
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
    def _resolve_override_digests(cls, version: str) -> dict[str, str | None]:
        """Resolves per-platform digests for a custom version via its CHECKSUMS.txt.

        Returns a full platform→digest map; platforms missing from the checksum file
        get ``None`` (and their download will be refused by the verified chain).
        A failed or missing CHECKSUMS.txt raises, refusing the install.
        """
        checksums = _fetch_release_checksums(version)
        return {platform_key: checksums.get(basename) for platform_key, basename in _ASSET_BASENAME_BY_PLATFORM.items()}

    @classmethod
    def _runtime_dependencies(cls, version: str, sha256_by_platform: dict[str, str | None] | None = None) -> RuntimeDependencyCollection:
        base_url = f"https://github.com/davalillo/mql-language-server/releases/download/{version}"
        if sha256_by_platform is None:
            sha256_by_platform = {platform_key: _mql_sha(version, platform_key) for platform_key in _ASSET_BASENAME_BY_PLATFORM}
        return RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="mql-lsp-server",
                    description=f"mql-language-server for {platform_key}",
                    url=f"{base_url}/{_ASSET_BASENAME_BY_PLATFORM[platform_key]}",
                    platform_id=platform_key,
                    archive_type="binary",
                    binary_name="mql-lsp-server.exe" if platform_key == "win-x64" else "mql-lsp-server",
                    sha256=sha256_by_platform[platform_key],
                    allowed_hosts=MQL_ALLOWED_HOSTS,
                )
                for platform_key in _ASSET_BASENAME_BY_PLATFORM
            ]
        )

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        @staticmethod
        def _install_dir_name(version: str) -> str:
            """Gets the install directory name for a version.

            The legacy unversioned dir is reserved for INITIAL (see the version
            pinning convention atop the module); every other version gets a
            versioned subdir so that a DEFAULT bump never silently reuses stale
            binaries.
            """
            return "mql-lsp" if version == INITIAL_MQL_VERSION else f"mql-lsp-{version}"

        @staticmethod
        def _prune_stale_install_dirs(ls_resources_dir: str, active_dir_name: str) -> None:
            """Removes other MQL install directories left behind by earlier version bumps.

            Each mql-lsp-server binary is ~80 MB, so superseded versions are deleted
            instead of accumulating on disk. Failures are logged but never propagate:
            pruning is opportunistic and must not break server startup.
            """
            try:
                for entry in os.listdir(ls_resources_dir):
                    if entry == active_dir_name or not (entry == "mql-lsp" or entry.startswith("mql-lsp-")):
                        continue
                    stale_dir = os.path.join(ls_resources_dir, entry)
                    if not os.path.isdir(stale_dir):
                        continue
                    log.info("Pruning stale mql-lsp-server install directory: %s", stale_dir)
                    shutil.rmtree(stale_dir, ignore_errors=True)
            except OSError as ex:
                log.warning("Could not prune stale mql-lsp-server install directories: %s", ex)

        def _get_or_install_core_dependency(self) -> str:
            """Resolve the pinned mql-language-server version and return the executable path."""
            version = self._custom_settings.get("mql_version", DEFAULT_MQL_VERSION)
            deps = MqlLanguageServer._runtime_dependencies(version)
            dependency = deps.get_single_dep_for_current_platform()

            install_dir = os.path.join(self._ls_resources_dir, self._install_dir_name(version))
            executable_path = deps.binary_path(install_dir)
            if not os.path.exists(executable_path):
                if dependency.sha256 is None:
                    # custom ``mql_version`` override: no locally pinned digest, so verify
                    # against the release's own CHECKSUMS.txt (single fetch, host-allowed).
                    # A failed/missing checksum file aborts the install instead of
                    # downloading the binary unverified.
                    sha256_by_platform = MqlLanguageServer._resolve_override_digests(version)
                    deps = MqlLanguageServer._runtime_dependencies(version, sha256_by_platform)
                    dependency = deps.get_single_dep_for_current_platform()
                log.info("Downloading mql-lsp-server from %s to %s", dependency.url, install_dir)
                deps.install(install_dir)
            if not os.path.exists(executable_path):
                raise FileNotFoundError(f"Download failed? Could not find mql-lsp-server executable at {executable_path}")
            if platform.system() != "Windows":
                os.chmod(executable_path, 0o755)

            # active version is guaranteed present, so superseded installs can go
            self._prune_stale_install_dirs(self._ls_resources_dir, self._install_dir_name(version))
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
        deadline = time.monotonic() + MQL_CAPABILITY_REGISTRATION_TIMEOUT_S
        while not required.issubset(set(capability_names)) and time.monotonic() < deadline:
            time.sleep(0.1)
        missing = required - set(capability_names)
        if missing:
            # raise instead of assert: an assert would vanish under `python -O` and
            # leave the server half-alive; start() cleans up the process on raise
            raise SolidLSPException(
                f"mql-lsp-server did not register required capabilities "
                f"within {MQL_CAPABILITY_REGISTRATION_TIMEOUT_S:.0f}s: {sorted(missing)}"
            )

        self.server_ready.set()
