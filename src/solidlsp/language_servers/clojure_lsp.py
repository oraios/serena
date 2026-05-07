"""
Provides Clojure specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Clojure.
"""

import logging
import os
import pathlib
import re
import shutil
import subprocess
import threading
from typing import cast

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_CLOJURE_LSP_VERSION = "2026.02.20-16.08.58"
INITIAL_CLOJURE_LSP_SHA256_BY_PLATFORM = {
    "osx-arm64": "a14d4db074f665378214e2dc888472e186c228dfa065c777b0534bfda5571669",
    "osx-x64": "5507434c27104ab816e096d3336d8191641de8a65b57d76afb585d07167a3cf2",
    "linux-arm64": "f8f09fa07dd4b6743b5c57270ccf1ee5cdbc5fca09dbca8b6a3b22705b5da4e1",
    "linux-x64": "52e8bf4fd4cf171df0a3077c8bb5a3bf598d4c621e94b4876dab943a61267309",
    "win-x64": "817b1271288817c954fb9e595278b1f25003827ce31f8785f253dc4ac911041f",
}
DEFAULT_CLOJURE_LSP_VERSION = "2026.02.20-16.08.58"
DEFAULT_CLOJURE_LSP_SHA256_BY_PLATFORM = {
    "osx-arm64": "a14d4db074f665378214e2dc888472e186c228dfa065c777b0534bfda5571669",
    "osx-x64": "5507434c27104ab816e096d3336d8191641de8a65b57d76afb585d07167a3cf2",
    "linux-arm64": "f8f09fa07dd4b6743b5c57270ccf1ee5cdbc5fca09dbca8b6a3b22705b5da4e1",
    "linux-x64": "52e8bf4fd4cf171df0a3077c8bb5a3bf598d4c621e94b4876dab943a61267309",
    "win-x64": "817b1271288817c954fb9e595278b1f25003827ce31f8785f253dc4ac911041f",
}


def _clojure_lsp_sha(version: str, platform_key: str) -> str | None:
    if version == INITIAL_CLOJURE_LSP_VERSION:
        return INITIAL_CLOJURE_LSP_SHA256_BY_PLATFORM[platform_key]
    if version == DEFAULT_CLOJURE_LSP_VERSION:
        return DEFAULT_CLOJURE_LSP_SHA256_BY_PLATFORM[platform_key]
    return None


CLOJURE_LSP_ALLOWED_HOSTS = (
    "github.com",
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
)


def run_command(cmd: list, capture_output: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, stdout=subprocess.PIPE if capture_output else None, stderr=subprocess.STDOUT if capture_output else None, text=True, check=True
    )


def verify_clojure_cli() -> None:
    install_msg = "Please install the official Clojure CLI from:\n  https://clojure.org/guides/getting_started"
    if shutil.which("clojure") is None:
        raise FileNotFoundError("`clojure` not found.\n" + install_msg)

    help_proc = run_command(["clojure", "--help"])
    if "-Aaliases" not in help_proc.stdout:
        raise RuntimeError("Detected a Clojure executable, but it does not support '-Aaliases'.\n" + install_msg)

    spath_proc = run_command(["clojure", "-Spath"], capture_output=False)
    if spath_proc.returncode != 0:
        raise RuntimeError("`clojure -Spath` failed; please upgrade to Clojure CLI ≥ 1.10.")


class ClojureLSP(SolidLanguageServer):
    """
    Provides a clojure-lsp specific instantiation of the LanguageServer class.

    You can pass the following entries in ``ls_specific_settings["clojure"]``:
        - clojure_lsp_version: Override the pinned clojure-lsp version downloaded
          by Serena (default: the bundled Serena version).
        - source_paths: Explicit list of source paths (repo-root-relative) to
          inject into clojure-lsp's ``initializationOptions``. Skips both the
          ``.lsp/config.edn`` lookup and the project-tree scan.
        - config_edn_path: Path to a ``config.edn`` file whose ``:source-paths``
          entry should be parsed and injected. Skips the project-tree scan but
          is itself skipped if ``source_paths`` is also set.

    Source-path resolution order (first match wins):
        1. ``source_paths`` setting (explicit override)
        2. ``config_edn_path`` setting (explicit config file)
        3. ``<repo>/.lsp/config.edn`` exists → trust it (clojure-lsp reads it
           natively, so we inject nothing)
        4. Walk the repo for ``deps.edn`` / ``project.clj`` / ``shadow-cljs.edn``
           / ``bb.edn`` and synthesise a source-paths list from their declared
           ``:paths`` / ``:extra-paths`` / ``:source-paths``.
    """

    CLOJURE_LSP_ALLOWED_HOSTS = CLOJURE_LSP_ALLOWED_HOSTS

    # Files that mark a directory as the root of a Clojure (sub-)project. Used both to detect
    # multi-module monorepos when synthesising clojure-lsp's `source-paths` and to walk the
    # tree extracting declared paths.
    _PROJECT_DESCRIPTOR_FILENAMES = ("deps.edn", "project.clj", "shadow-cljs.edn", "bb.edn")

    # Best-effort EDN extraction (full EDN parsing would be overkill for discovery hints):
    # matches `:paths […]`, `:extra-paths […]` and `:source-paths […]` followed by a vector of strings.
    _PATHS_VECTOR_RE = re.compile(r":(?:extra-paths|source-paths|paths)\s*\[([^\]]*)\]")
    _QUOTED_STRING_RE = re.compile(r'"([^"]+)"')

    # Clojure-specific directories worth pruning
    _IGNORED_DIRS = frozenset({".clj-kondo", ".lsp", ".cpcache", "node_modules", "target", "out", "dist"})

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in self._IGNORED_DIRS

    @staticmethod
    def _parse_project_descriptor_paths(descriptor_path: str) -> list[str]:
        """Extracts source-path string entries from a Clojure project descriptor (best-effort).

        :param descriptor_path: absolute path to a `deps.edn`, `project.clj`, `shadow-cljs.edn` or `bb.edn`
        :return: the path strings declared under `:paths`, `:extra-paths` or `:source-paths` keys,
            in the order they appear; relative to the descriptor's own directory
        """
        try:
            text = pathlib.Path(descriptor_path).read_text(encoding="utf-8")
        except OSError as e:
            log.debug(f"Could not read project descriptor {descriptor_path}: {e}")
            return []

        declared: list[str] = []
        for vector_match in ClojureLSP._PATHS_VECTOR_RE.finditer(text):
            declared.extend(ClojureLSP._QUOTED_STRING_RE.findall(vector_match.group(1)))
        return declared

    def _collect_source_paths(self) -> list[str]:
        """Walks the repo to discover all declared Clojure source paths across modules.

        Workaround for a clojure-lsp limitation: it discovers source paths only from the
        descriptor at the workspace root and does not recurse for sub-module descriptors,
        even when additional ``workspaceFolders`` are advertised. For multi-module monorepos
        this means references in sibling modules are silently missed until the user happens
        to open one of their files. We pass the union of declared paths to clojure-lsp via
        ``initializationOptions["source-paths"]`` — equivalent to what users of such monorepos
        otherwise have to write manually in ``.lsp/config.edn``.

        :return: deduplicated, repo-root-relative, forward-slash-normalised source paths from
            every project descriptor found in the tree (pruning via :py:meth:`is_ignored_dirname`);
            falls back to ``["src"]`` if nothing is discovered, matching the clojure-lsp default
        """
        repository_absolute_path = self.repository_root_path
        discovered: list[str] = []
        for dirpath, dirnames, filenames in os.walk(repository_absolute_path):
            # prune ignored dirs at the parent level so we never descend into node_modules,
            # target, .git etc. — much cheaper than scandir-ing them and filtering after
            dirnames[:] = [d for d in dirnames if not self.is_ignored_dirname(d)]

            # for each descriptor at this level, resolve declared paths back to the repo root
            module_rel = os.path.relpath(dirpath, repository_absolute_path)
            for descriptor in self._PROJECT_DESCRIPTOR_FILENAMES:
                if descriptor in filenames:
                    for declared_path in self._parse_project_descriptor_paths(os.path.join(dirpath, descriptor)):
                        if module_rel == ".":
                            resolved = declared_path
                        else:
                            resolved = os.path.normpath(os.path.join(module_rel, declared_path))
                        discovered.append(resolved.replace(os.sep, "/"))

        return list(set(discovered)) or ["src"]

    @classmethod
    def _runtime_dependencies(cls, version: str) -> RuntimeDependencyCollection:
        clojure_lsp_releases = f"https://github.com/clojure-lsp/clojure-lsp/releases/download/{version}"
        return RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="clojure-lsp",
                    url=f"{clojure_lsp_releases}/clojure-lsp-native-macos-aarch64.zip",
                    platform_id="osx-arm64",
                    archive_type="zip",
                    binary_name="clojure-lsp",
                    sha256=_clojure_lsp_sha(version, "osx-arm64"),
                    allowed_hosts=CLOJURE_LSP_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="clojure-lsp",
                    url=f"{clojure_lsp_releases}/clojure-lsp-native-macos-amd64.zip",
                    platform_id="osx-x64",
                    archive_type="zip",
                    binary_name="clojure-lsp",
                    sha256=_clojure_lsp_sha(version, "osx-x64"),
                    allowed_hosts=CLOJURE_LSP_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="clojure-lsp",
                    url=f"{clojure_lsp_releases}/clojure-lsp-native-linux-aarch64.zip",
                    platform_id="linux-arm64",
                    archive_type="zip",
                    binary_name="clojure-lsp",
                    sha256=_clojure_lsp_sha(version, "linux-arm64"),
                    allowed_hosts=CLOJURE_LSP_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="clojure-lsp",
                    url=f"{clojure_lsp_releases}/clojure-lsp-native-linux-amd64.zip",
                    platform_id="linux-x64",
                    archive_type="zip",
                    binary_name="clojure-lsp",
                    sha256=_clojure_lsp_sha(version, "linux-x64"),
                    allowed_hosts=CLOJURE_LSP_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="clojure-lsp",
                    url=f"{clojure_lsp_releases}/clojure-lsp-native-windows-amd64.zip",
                    platform_id="win-x64",
                    archive_type="zip",
                    binary_name="clojure-lsp.exe",
                    sha256=_clojure_lsp_sha(version, "win-x64"),
                    allowed_hosts=CLOJURE_LSP_ALLOWED_HOSTS,
                ),
            ]
        )

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a ClojureLSP instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            "clojure",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()
        self.resolve_main_method_available = threading.Event()
        self.service_ready_event = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """Setup runtime dependencies for clojure-lsp and return the path to the executable."""
            verify_clojure_cli()
            clojure_lsp_version = self._custom_settings.get("clojure_lsp_version", DEFAULT_CLOJURE_LSP_VERSION)
            deps = ClojureLSP._runtime_dependencies(clojure_lsp_version)
            dependency = deps.get_single_dep_for_current_platform()

            # legacy unversioned dir reserved for INITIAL; every other version goes into a versioned subdir
            install_dir = (
                self._ls_resources_dir
                if clojure_lsp_version == INITIAL_CLOJURE_LSP_VERSION
                else os.path.join(self._ls_resources_dir, f"clojure-lsp-{clojure_lsp_version}")
            )
            clojurelsp_executable_path = deps.binary_path(install_dir)
            if not os.path.exists(clojurelsp_executable_path):
                log.info(
                    f"Downloading and extracting clojure-lsp from {dependency.url} to {install_dir}",
                )
                deps.install(install_dir)
            if not os.path.exists(clojurelsp_executable_path):
                raise FileNotFoundError(f"Download failed? Could not find clojure-lsp executable at {clojurelsp_executable_path}")
            os.chmod(clojurelsp_executable_path, 0o755)
            return clojurelsp_executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path]

    def _resolve_source_paths(self) -> list[str] | None:
        """Determines whether to inject ``source-paths`` into clojure-lsp's init options.

        :return: the list of repo-root-relative source paths to inject, or ``None`` to inject
            nothing (because clojure-lsp will read the project's own ``.lsp/config.edn`` natively).
            See the class docstring for the precedence order.
        """
        # explicit user override of source paths wins outright
        explicit_paths = self._custom_settings.get("source_paths")
        if explicit_paths:
            log.info(f"clojure-lsp source-paths from user setting 'source_paths': {explicit_paths}")
            return list(explicit_paths)

        # user-supplied config.edn path: parse and extract source paths from it
        explicit_config_edn = self._custom_settings.get("config_edn_path")
        if explicit_config_edn:
            parsed = self._parse_project_descriptor_paths(explicit_config_edn)
            log.info(f"clojure-lsp source-paths from user setting 'config_edn_path' ({explicit_config_edn}): {parsed}")
            return parsed or None

        # repo-local .lsp/config.edn: clojure-lsp will read it natively, so we leave it alone
        # to avoid clobbering hand-tuned configs in projects like penpot
        repo_config_edn = pathlib.Path(self.repository_root_path) / ".lsp" / "config.edn"
        if repo_config_edn.is_file():
            log.info(f"clojure-lsp will read project's own {repo_config_edn} (no source-paths injection)")
            return None

        # fall back to scanning for project descriptors; this is the workaround for clojure-lsp's
        # lack of recursion into sub-module deps.edn files in multi-module monorepos
        scanned = self._collect_source_paths()
        log.info(f"clojure-lsp source-paths scanned from project descriptors: {scanned}")
        return scanned

    def _get_initialize_params(self) -> InitializeParams:
        """Returns the init params for clojure-lsp."""
        repository_absolute_path = self.repository_root_path
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        source_paths = self._resolve_source_paths()

        initialization_options: dict = {"dependency-scheme": "jar", "text-document-sync-kind": "incremental"}
        if source_paths is not None:
            initialization_options["source-paths"] = source_paths

        result = {  # type: ignore
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "capabilities": {
                "workspace": {
                    "applyEdit": True,
                    "workspaceEdit": {"documentChanges": True},
                    "symbol": {"symbolKind": {"valueSet": list(range(1, 27))}},
                    "workspaceFolders": True,
                },
                "textDocument": {
                    "synchronization": {"didSave": True},
                    "publishDiagnostics": {"relatedInformation": True, "tagSupport": {"valueSet": [1, 2]}},
                    "definition": {"linkSupport": True},
                    "references": {},
                    "hover": {"contentFormat": ["markdown", "plaintext"]},
                    "documentSymbol": {
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},  #
                    },
                },
                "general": {"positionEncodings": ["utf-16"]},
            },
            "initializationOptions": initialization_options,
            "trace": "off",
            "workspaceFolders": [{"uri": root_uri, "name": os.path.basename(repository_absolute_path)}],
        }
        return cast(InitializeParams, result)

    def _start_server(self) -> None:
        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
                    self.resolve_main_method_available.set()
            return

        def lang_status_handler(params: dict) -> None:
            # TODO: Should we wait for
            # server -> client: {'jsonrpc': '2.0', 'method': 'language/status', 'params': {'type': 'ProjectStatus', 'message': 'OK'}}
            # Before proceeding?
            if params["type"] == "ServiceReady" and params["message"] == "ServiceReady":
                self.service_ready_event.set()

        def execute_client_command_handler(params: dict) -> list:
            return []

        def do_nothing(params: dict) -> None:
            return

        def check_experimental_status(params: dict) -> None:
            if params["quiescent"] is True:
                self.server_ready.set()

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("language/status", lang_status_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        log.info("Starting clojure-lsp server process")
        self.server.start()

        initialize_params = self._get_initialize_params()

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        assert init_response["capabilities"]["textDocumentSync"]["change"] == 2  # type: ignore
        assert "completionProvider" in init_response["capabilities"]
        # Clojure-lsp completion provider capabilities are more flexible than other servers'
        completion_provider = init_response["capabilities"]["completionProvider"]
        assert completion_provider["resolveProvider"] is True
        assert "triggerCharacters" in completion_provider
        self.server.notify.initialized({})
        # after initialize, Clojure-lsp is ready to serve
        self.server_ready.set()
