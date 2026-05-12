"""
Provides Svelte-specific instantiation of the LanguageServer class using
``svelte-language-server`` from Svelte Language Tools.
"""

from __future__ import annotations

import logging
import os
import pathlib
import shutil
from typing import Any, cast

from overrides import override

from solidlsp import ls_types
from solidlsp.language_servers.common import (
    RuntimeDependency,
    RuntimeDependencyCollection,
    build_npm_install_command,
)
from solidlsp.language_servers.typescript_language_server import TypeScriptLanguageServer
from solidlsp.ls import (
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    SolidLanguageServer,
)
from solidlsp.ls_config import FilenameMatcher, Language, LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)
TS_EXT = frozenset({".ts", ".tsx", ".mts", ".cts"})
JS_EXT = frozenset({".js", ".jsx", ".mjs", ".cjs"})
SVELTE_EXT = frozenset({".svelte"})


def _is_ts_file(uri: str) -> bool:
    return uri.lower().endswith(tuple(TS_EXT | JS_EXT))


def _is_svelte_file(uri: str) -> bool:
    return uri.lower().endswith(tuple(SVELTE_EXT))


class SvelteTypeScriptServer(TypeScriptLanguageServer):
    """Companion TypeScript language server for Svelte projects.

    Loads ``typescript-svelte-plugin`` so the TS graph becomes .svelte-aware:
    cross-file rename, find-references, and go-to-definition from .ts/.js files
    into .svelte consumers all work correctly through this companion.

    Spawned and owned by :class:`SvelteLanguageServer`; not instantiated directly.
    """

    class DependencyProvider(TypeScriptLanguageServer.DependencyProvider):
        """Returns the pre-installed typescript-language-server binary.

        The binary is installed by ``SvelteLanguageServer.DependencyProvider``;
        this provider just resolves the pre-known path without a separate install.
        """

        def __init__(
            self,
            custom_settings: SolidLSPSettings.CustomLSSettings,
            ls_resources_dir: str,
            explicit_executable_path: str,
        ) -> None:
            super().__init__(custom_settings, ls_resources_dir)
            self._explicit_executable_path = explicit_executable_path

        @override
        def _get_or_install_core_dependency(self) -> str:
            return self._explicit_executable_path

    def __init__(
        self,
        config: LanguageServerConfig,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
        svelte_plugin_path: str,
        tsdk_path: str,
        ts_ls_executable_path: str,
    ) -> None:
        self._svelte_plugin_path = svelte_plugin_path
        self._custom_tsdk_path = tsdk_path
        # store as instance state, not class attr, to avoid races across parallel instantiations
        self._explicit_ts_ls_executable = ts_ls_executable_path
        super().__init__(config, repository_root_path, solidlsp_settings)

    @classmethod
    @override
    def get_language_enum_instance(cls) -> Language:
        """Return TYPESCRIPT; companion uses the TypeScript LS infrastructure."""
        return Language.TYPESCRIPT

    @override
    def get_source_fn_matcher(self) -> FilenameMatcher:
        # include .svelte so references returned by the plugin are not filtered out
        return Language.SVELTE.get_source_fn_matcher()

    @override
    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(
            self._custom_settings,
            self._ls_resources_dir,
            self._explicit_ts_ls_executable,
        )

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        """.svelte files map to 'svelte' to activate the plugin; TS/JS as normal."""
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext in SVELTE_EXT:
            return "svelte"
        if ext in JS_EXT:
            return "javascript"
        return "typescript"

    @override
    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        params = super()._get_initialize_params(repository_absolute_path)
        params["initializationOptions"] = {
            "plugins": [
                {
                    "name": "typescript-svelte-plugin",
                    "location": self._svelte_plugin_path,
                    "languages": ["svelte"],
                }
            ],
            "tsserver": {"path": self._custom_tsdk_path},
        }
        return params

    @override
    def _start_server(self) -> None:
        def workspace_configuration_handler(params: dict) -> list:
            items = params.get("items", [])
            return [{} for _ in items]

        self.server.on_request("workspace/configuration", workspace_configuration_handler)
        super()._start_server()


class SvelteLanguageServer(SolidLanguageServer):
    """
    Svelte language server using ``svelte-language-server``.

    ``ls_specific_settings["svelte"]`` keys:
        * ``svelte_language_server_version``: version of ``svelte-language-server``
          to install (default: ``0.18.0``).
        * ``npm_registry``: optional alternative npm-compatible registry URL.
        * ``initialization_options_configuration``: optional dict merged into
          ``initializeParams.initializationOptions.configuration`` (same top-level keys as in
          Svelte Language Tools: ``svelte``, ``prettier``, ``typescript``, …).
    """

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def __init__(
            self,
            custom_settings: SolidLSPSettings.CustomLSSettings,
            ls_resources_dir: str,
            ts_settings: SolidLSPSettings.CustomLSSettings,
        ) -> None:
            super().__init__(custom_settings, ls_resources_dir)
            self._ts_settings = ts_settings

        def _get_or_install_core_dependency(self) -> str:
            assert shutil.which("node") is not None, "node is not installed or isn't in PATH. Please install NodeJS and try again."
            assert shutil.which("npm") is not None, "npm is not installed or isn't in PATH. Please install npm and try again."

            package_version = self._custom_settings.get("svelte_language_server_version", "0.18.0")
            npm_registry = self._custom_settings.get("npm_registry", self._ts_settings.get("npm_registry"))
            typescript_version = self._custom_settings.get("typescript_version", self._ts_settings.get("typescript_version", "6.0.3"))
            typescript_language_server_version = self._custom_settings.get(
                "typescript_language_server_version",
                self._ts_settings.get("typescript_language_server_version", "5.1.3"),
            )
            typescript_svelte_plugin_version = self._custom_settings.get("typescript_svelte_plugin_version", "0.3.52")

            # versioned install dir avoids silently reusing stale language-server binaries
            install_dir = os.path.join(self._ls_resources_dir, f"svelte-lsp-{package_version}")
            executable_path = os.path.join(install_dir, "node_modules", ".bin", "svelteserver")
            if os.name == "nt":
                executable_path += ".cmd"

            # version file encodes all four component versions; mismatch triggers reinstall
            version_file = os.path.join(install_dir, ".installed_version")
            expected_version = (
                f"{package_version}_{typescript_version}_{typescript_language_server_version}_{typescript_svelte_plugin_version}"
            )
            needs_install = not os.path.exists(executable_path)
            if not needs_install:
                if os.path.exists(version_file):
                    with open(version_file) as fv:
                        if fv.read().strip() != expected_version:
                            needs_install = True
                else:
                    # absent version file → old install that predates companion deps
                    needs_install = True

            if needs_install:
                log.info(
                    "Installing svelte-language-server@%s + typescript@%s + typescript-language-server@%s + typescript-svelte-plugin@%s ...",
                    package_version,
                    typescript_version,
                    typescript_language_server_version,
                    typescript_svelte_plugin_version,
                )
                runtime_deps = [
                    RuntimeDependency(
                        id="svelte-language-server",
                        description="Svelte language server",
                        command=build_npm_install_command("svelte-language-server", package_version, npm_registry),
                        platform_id="any",
                    ),
                    RuntimeDependency(
                        id="typescript",
                        description="TypeScript language service",
                        command=build_npm_install_command("typescript", typescript_version, npm_registry),
                        platform_id="any",
                    ),
                    RuntimeDependency(
                        id="typescript-language-server",
                        description="TypeScript language server (companion)",
                        command=build_npm_install_command("typescript-language-server", typescript_language_server_version, npm_registry),
                        platform_id="any",
                    ),
                    RuntimeDependency(
                        id="typescript-svelte-plugin",
                        description="TypeScript plugin for Svelte cross-file awareness",
                        command=build_npm_install_command("typescript-svelte-plugin", typescript_svelte_plugin_version, npm_registry),
                        platform_id="any",
                    ),
                ]
                RuntimeDependencyCollection(runtime_deps).install(install_dir)
                with open(version_file, "w") as fv:
                    fv.write(expected_version)

            if not os.path.exists(executable_path):
                raise FileNotFoundError(
                    f"executable not found at {executable_path}; "
                    f"npm install of svelte-language-server@{package_version} did not produce the expected binary."
                )
            return executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            # stdio suits SolidLSP's subprocess RPC; other hosts may use a different transport.
            return [core_path, "--stdio"]

    @override
    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        ts_settings = self._solidlsp_settings.get_ls_specific_settings(Language.TYPESCRIPT)
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir, ts_settings)

    def __init__(self, config: LanguageServerConfig, repo_path: str, solidlsp_settings: SolidLSPSettings):
        resolved_root = os.path.abspath(repo_path)
        super().__init__(
            config,
            resolved_root,
            None,
            "svelte",
            solidlsp_settings,
        )
        self.repo_path: str = resolved_root
        self.tsdk_path = self._get_tsdk_path()
        self._lsp_configuration: dict[str, Any] = {}
        self._ts_server: SvelteTypeScriptServer | None = None
        self._ts_server_started: bool = False
        self._svelte_files_indexed: bool = False
        self._indexed_svelte_file_uris: list[str] = []

    def _get_tsdk_path(self) -> str:
        """
        Compute the local typescript/lib path for the Svelte language server.
        Asserts if not found, since DependencyProvider guarantees install.
        """
        package_version = self._custom_settings.get("svelte_language_server_version", "0.18.0")
        install_dir = os.path.join(self._ls_resources_dir, f"svelte-lsp-{package_version}")
        tsdk_candidate = os.path.join(install_dir, "node_modules", "typescript", "lib")
        assert os.path.isdir(tsdk_candidate), (
            f"TypeScript SDK not found at expected path: {tsdk_candidate}. Installation via DependencyProvider failed or version mismatch."
        )
        return tsdk_candidate

    def _get_install_dir(self) -> str:
        """:return: versioned install directory for svelte-language-server and companion deps."""
        version = self._custom_settings.get("svelte_language_server_version", "0.18.0")
        return os.path.join(self._ls_resources_dir, f"svelte-lsp-{version}")

    def _get_ts_ls_executable(self) -> str:
        """:return: path to the typescript-language-server binary installed alongside the svelte LS."""
        path = os.path.join(self._get_install_dir(), "node_modules", ".bin", "typescript-language-server")
        if os.name == "nt":
            path += ".cmd"
        return path

    def _get_svelte_ts_plugin_path(self) -> str:
        """:return: path to the ``typescript-svelte-plugin`` package directory."""
        return os.path.join(self._get_install_dir(), "node_modules", "typescript-svelte-plugin")

    def _find_all_svelte_files(self) -> list[str]:
        """:return: relative paths of all .svelte files in the repo (excluding node_modules and dot-dirs)."""
        svelte_files = []
        repo = pathlib.Path(self.repo_path)
        for svelte_file in repo.rglob("*.svelte"):
            try:
                relative = str(svelte_file.relative_to(repo))
                if "node_modules" not in relative and not relative.startswith("."):
                    svelte_files.append(relative)
            except Exception as exc:
                log.debug("Error processing svelte file %s: %s", svelte_file, exc)
        return svelte_files

    def _ensure_svelte_files_indexed_on_ts_server(self) -> None:
        """Open all .svelte files on the companion TS server so the plugin includes them in the TS program.

        The ``typescript-svelte-plugin``'s ``getExternalFiles`` is called by tsserver when a project
        is set up, but only after the first file in that project is opened. Opening each .svelte file
        with languageId ``"svelte"`` causes tsserver to invoke the plugin's ``getScriptSnapshot``
        for those files, adding them to the project graph so cross-file rename and references work.
        """
        if self._svelte_files_indexed:
            return
        assert self._ts_server is not None

        log.info("Indexing .svelte files on companion TypeScript server for cross-file awareness")
        svelte_files = self._find_all_svelte_files()
        log.debug("Found %d .svelte files to index", len(svelte_files))

        # prepare progress tracking BEFORE opening files to avoid a race
        self._ts_server.expect_indexing()

        for svelte_file in svelte_files:
            try:
                with self._ts_server.open_file(svelte_file) as file_buffer:
                    file_buffer.ref_count += 1
                    self._indexed_svelte_file_uris.append(file_buffer.uri)
            except Exception as exc:
                log.debug("Failed to open %s on companion TS server: %s", svelte_file, exc)

        self._svelte_files_indexed = True
        log.info("Svelte file indexing complete; waiting for companion TS server to finish processing")

        timeout = TypeScriptLanguageServer.INDEXING_PROGRESS_TIMEOUT
        if self._ts_server.wait_for_indexing(timeout=timeout):
            log.info("Companion TypeScript server finished indexing .svelte files")
        else:
            log.warning("Timeout (%ss) waiting for companion TS server to index .svelte files; proceeding anyway", timeout)

    def _cleanup_indexed_svelte_files(self) -> None:
        """Decrement ref-counts for all .svelte files opened during indexing."""
        if not self._indexed_svelte_file_uris or self._ts_server is None:
            return
        log.debug("Cleaning up %d indexed .svelte files", len(self._indexed_svelte_file_uris))
        for uri in self._indexed_svelte_file_uris:
            try:
                if uri in self._ts_server.open_file_buffers:
                    file_buffer = self._ts_server.open_file_buffers[uri]
                    file_buffer.ref_count -= 1
                    if file_buffer.ref_count == 0:
                        self._ts_server.server.notify.did_close_text_document({"textDocument": {"uri": uri}})
                        del self._ts_server.open_file_buffers[uri]
            except Exception as exc:
                log.debug("Error closing indexed svelte file %s: %s", uri, exc)
        self._indexed_svelte_file_uris.clear()

    def _start_typescript_server(self) -> None:
        """Spawn the companion :class:`SvelteTypeScriptServer`, wait for ready, then index .svelte files."""
        try:
            ts_config = LanguageServerConfig(
                code_language=Language.TYPESCRIPT,
                trace_lsp_communication=False,
            )
            log.info("Creating companion SvelteTypeScriptServer")
            self._ts_server = SvelteTypeScriptServer(
                config=ts_config,
                repository_root_path=self.repo_path,
                solidlsp_settings=self._solidlsp_settings,
                svelte_plugin_path=self._get_svelte_ts_plugin_path(),
                tsdk_path=self.tsdk_path,
                ts_ls_executable_path=self._get_ts_ls_executable(),
            )
            log.info("Starting companion SvelteTypeScriptServer")
            self._ts_server.start()
            log.info("Waiting for companion SvelteTypeScriptServer to be ready ...")
            if not self._ts_server.server_ready.wait(timeout=30.0):
                log.warning("Timeout waiting for companion SvelteTypeScriptServer; proceeding anyway")
                self._ts_server.server_ready.set()
            self._ts_server_started = True
            log.info("Companion SvelteTypeScriptServer ready")
            self._ensure_svelte_files_indexed_on_ts_server()
        except Exception:
            log.exception("Error starting companion SvelteTypeScriptServer; TS-side operations degrade to svelte LS")
            self._ts_server = None
            self._ts_server_started = False

    def _stop_typescript_server(self) -> None:
        """Shut down the companion TypeScript server if running."""
        if self._ts_server is not None:
            self._cleanup_indexed_svelte_files()
            try:
                log.info("Stopping companion SvelteTypeScriptServer")
                self._ts_server.stop()
            except Exception as exc:
                log.warning("Error stopping companion SvelteTypeScriptServer: %s", exc)
            finally:
                self._ts_server = None
                self._ts_server_started = False

    def _wrap_notify_send_for_ts_js_mirror(self) -> None:
        """Mirror TS/JS didChange via ``$/onDidChangeTsOrJsFile`` so the server updates TS snapshots.

        Unlike upstream ``svelte-vscode`` (svelte-only documentSelector), Serena must also open and
        query TS/JS files directly through the same server instance. Standard sync notifications are
        therefore kept; ``$/onDidChangeTsOrJsFile`` is sent additionally for didChange so the svelte
        LS keeps its internal TS snapshot in sync with the open-buffer content.
        """
        _orig_notify_send = self.server.notify.send_notification

        def send_notification_wrapped(method: str, params: dict | None = None) -> None:
            _orig_notify_send(method, params)
            if method != "textDocument/didChange" or not params:
                return
            text_document = params.get("textDocument")
            if not text_document:
                return
            uri = text_document.get("uri")
            if not uri:
                return
            fb = self.open_file_buffers.get(uri)
            if fb is None or fb.language_id not in ("typescript", "javascript"):
                return
            changes = params.get("contentChanges")
            if changes is None:
                return
            _orig_notify_send("$/onDidChangeTsOrJsFile", {"uri": uri, "changes": changes})

        self.server.notify.send_notification = send_notification_wrapped  # type: ignore[method-assign]  # type: ignore[method-assign]  # type: ignore[method-assign]

    def _get_initialize_params(self) -> InitializeParams:
        """
        Returns the initialize params for the Svelte Language Server.

        Builds the full ``initializationOptions.configuration`` section mirroring all
        keys expected by ``svelte-language-server`` plugins (svelte, prettier, emmet,
        typescript, javascript, js/ts, css, less, scss, html). Caller-supplied overrides
        from ``initialization_options_configuration`` are deep-merged on top.
        The resulting dict is also stored as :attr:`_lsp_configuration` so
        ``workspace/configuration`` requests can be answered with real values.
        """
        root_uri = pathlib.Path(self.repo_path).as_uri()

        # base configuration mirroring all plugin-sections from svelte-vscode initializationOptions
        lsp_config: dict[str, Any] = {
            "svelte": {},
            "prettier": {},
            "emmet": {},
            "javascript": {"tsdk": self.tsdk_path},
            "typescript": {"tsdk": self.tsdk_path},
            "js/ts": {"tsdk": self.tsdk_path},
            "css": {},
            "less": {},
            "scss": {},
            "html": {},
        }

        # apply caller-supplied overrides (same top-level keys)
        for key, val in self._custom_settings.get("initialization_options_configuration", {}).items():
            if key in lsp_config and isinstance(lsp_config[key], dict) and isinstance(val, dict):
                lsp_config[key] = {**lsp_config[key], **val}
            else:
                lsp_config[key] = val

        self._lsp_configuration = lsp_config

        initialize_params: dict = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "signatureHelp": {"dynamicRegistration": True},
                    "codeAction": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                    "implementation": {"dynamicRegistration": True},
                    "typeDefinition": {"dynamicRegistration": True},
                    "diagnostic": {"dynamicRegistration": True},
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {
                    "applyEdit": True,
                    "configuration": True,
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {"dynamicRegistration": True, "relativePatternSupport": True},
                    "symbol": {"dynamicRegistration": True},
                    "diagnostics": {"refreshSupport": True},
                    "fileOperations": {"didRename": True},
                },
            },
            "initializationOptions": {
                "isTrusted": True,
                "dontFilterIncompleteCompletions": True,
                "configuration": lsp_config,
            },
            "processId": os.getpid(),
            "rootPath": self.repo_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(self.repo_path),
                }
            ],
        }
        return cast(InitializeParams, initialize_params)

    def _start_server(self) -> None:
        def window_log_message(msg: dict) -> None:
            log.info("LSP: window/logMessage: %s", msg)

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params

        def configuration_handler(params: dict) -> list:
            items = params.get("items", [])
            result = []
            for item in items:
                section = item.get("section", "") if isinstance(item, dict) else ""
                result.append(self._lsp_configuration.get(section, {}))
            return result

        def workspace_apply_edit_handler(_params: dict) -> dict[str, Any]:
            return {"applied": False}

        def work_done_progress_create(_params: dict) -> dict:
            return {}

        def do_nothing(_params: dict) -> None:
            pass

        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("window/workDoneProgress/create", work_done_progress_create)
        self.server.on_request("workspace/applyEdit", workspace_apply_edit_handler)
        self.server.on_request("workspace/configuration", configuration_handler)
        self.server.on_request("workspace/diagnostic/refresh", do_nothing)
        self.server.on_request("workspace/inlayHints/refresh", do_nothing)
        self.server.on_request("workspace/semanticTokens/refresh", do_nothing)
        self._wrap_notify_send_for_ts_js_mirror()
        self.server.start()

        init_params = self._get_initialize_params()
        init_response = self.server.send.initialize(init_params)

        assert "documentSymbolProvider" in init_response["capabilities"], "Svelte LSP did not advertise documentSymbolProvider"
        assert "definitionProvider" in init_response["capabilities"], "Svelte LSP did not advertise definitionProvider"

        self.server.notify.initialized({})
        self._start_typescript_server()

    @staticmethod
    def _deduplicate_reference_locations(a: list[ls_types.Location], b: list[ls_types.Location]) -> list[ls_types.Location]:
        seen = set()

        for loc in a:
            start = loc["range"]["start"]
            seen.add((loc["uri"], start["line"], start["character"]))

        deduped_refs = list(a)

        for loc in b:
            start = loc["range"]["start"]
            key = (loc["uri"], start["line"], start["character"])

            if key not in seen:
                seen.add(key)
                deduped_refs.append(loc)

        return deduped_refs

    @override
    def stop(self, shutdown_timeout: float = 5.0) -> None:
        self._stop_typescript_server()
        super().stop(shutdown_timeout)

    @override
    def request_references(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        """Combine references from svelte LS and companion TS server.

        For .svelte files: svelte LS + ``$/getComponentReferences``.
        For .ts/.js files: companion TS server (svelte-plugin-aware) merged with
        svelte LS ``$/getFileReferences`` to maximise cross-file coverage.
        Falls back to svelte-LS-only behaviour when companion is unavailable.
        """
        symbol_refs = super().request_references(relative_file_path, line, column)
        normalize_helper = self.ReferencesLocationRequest(self, relative_file_path, line, column)

        if _is_ts_file(relative_file_path):
            # augment with svelte LS file-level references
            raw = self.server.send_request("$/getFileReferences", cast(Any, self._resolve_file_uri(relative_file_path)))
            file_refs = normalize_helper.normalize_response(raw if isinstance(raw, list) else [])
            symbol_refs = self._deduplicate_reference_locations(symbol_refs, file_refs)

            # augment with companion TS server (typescript-svelte-plugin gives .svelte awareness)
            if self._ts_server is not None:
                with self._ts_server.open_file(relative_file_path):
                    ts_refs = self._ts_server.request_references(relative_file_path, line, column)
                symbol_refs = self._deduplicate_reference_locations(symbol_refs, ts_refs)

        elif _is_svelte_file(relative_file_path):
            raw = self.server.send_request("$/getComponentReferences", cast(Any, self._resolve_file_uri(relative_file_path)))
            comp_refs = normalize_helper.normalize_response(raw if isinstance(raw, list) else [])
            symbol_refs = self._deduplicate_reference_locations(symbol_refs, comp_refs)

        return symbol_refs

    @override
    def request_rename_symbol_edit(self, relative_file_path: str, line: int, column: int, new_name: str) -> ls_types.WorkspaceEdit | None:
        """Delegate TS/JS renames to the companion so the svelte plugin handles cross-file edits.

        Falls back to the svelte LS when the companion is unavailable or when the file is .svelte.
        """
        if _is_ts_file(relative_file_path) and self._ts_server is not None:
            with self._ts_server.open_file(relative_file_path):
                return self._ts_server.request_rename_symbol_edit(relative_file_path, line, column, new_name)
        return super().request_rename_symbol_edit(relative_file_path, line, column, new_name)

    @override
    def request_definition(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        """Delegate TS/JS go-to-definition to the companion for .svelte-aware resolution.

        Falls back to the svelte LS when the companion is unavailable or when the file is .svelte.
        """
        if _is_ts_file(relative_file_path) and self._ts_server is not None:
            with self._ts_server.open_file(relative_file_path):
                return self._ts_server.request_definition(relative_file_path, line, column)
        return super().request_definition(relative_file_path, line, column)

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext in TS_EXT:
            return "typescript"
        if ext in JS_EXT:
            return "javascript"
        return self.language_id

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["dist", "build", "coverage"]
