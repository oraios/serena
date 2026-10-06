"""
Provides Astro-specific instantiation of the LanguageServer class using
@astrojs/language-server with a companion TypeScript language server (@astrojs/ts-plugin).

Operates in a dual-server setup: the Astro LS handles .astro files (AST parsing,
document symbols), while a companion TypeScript LS (configured with @astrojs/ts-plugin)
handles definitions, references, document symbols, and rename for .ts/.js files and
cross-file resolution between .ts/.js and .astro files.
"""

from __future__ import annotations

import logging
import os
import pathlib
import shutil
from collections.abc import Callable
from typing import Any

from overrides import override

from solidlsp import ls_types
from solidlsp.language_servers.common import (
    RuntimeDependency,
    RuntimeDependencyCollection,
    build_npm_install_command,
)
from solidlsp.language_servers.typescript_language_server import (
    TypeScriptLanguageServer,
    prefer_non_node_modules_definition,
)
from solidlsp.ls import (
    DocumentSymbols,
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    LSPFileBuffer,
    SolidLanguageServer,
)
from solidlsp.ls_config import FilenameMatcher, LanguageServerConfig, LanguageServerId
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

ASTRO_EXT = frozenset({".astro"})
TS_EXT = frozenset({".ts", ".tsx", ".mts", ".cts"})
JS_EXT = frozenset({".js", ".jsx", ".mjs", ".cjs"})
_MAX_FAILED_FILES_IN_ERROR = 10


class AstroCompanionPreparationError(RuntimeError):
    """Raised when the companion TypeScript server cannot be prepared deterministically."""


def _is_ts_file(uri: str) -> bool:
    return uri.lower().endswith(tuple(TS_EXT | JS_EXT))


def _is_astro_file(uri: str) -> bool:
    return uri.lower().endswith(tuple(ASTRO_EXT))


class AstroTypeScriptServer(TypeScriptLanguageServer):
    """Companion TypeScript language server for Astro projects.

    Loads ``@astrojs/ts-plugin`` so the TS graph becomes .astro-aware:
    cross-file rename, find-references, and go-to-definition from .ts/.js files
    into .astro consumers all work correctly through this companion.

    Spawned and owned by :class:`AstroLanguageServer`; not instantiated directly.
    """

    INDEXING_PROGRESS_TIMEOUT = 120.0
    SERVER_READY_TIMEOUT = 30.0

    class DependencyProvider(TypeScriptLanguageServer.DependencyProvider):
        """Returns the pre-installed typescript-language-server binary.

        The binary is installed by ``AstroLanguageServer.DependencyProvider``;
        this provider resolves the pre-known path without a separate install.
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
        astro_plugin_path: str,
        tsdk_path: str,
        ts_ls_executable_path: str,
    ) -> None:
        self._astro_plugin_path = astro_plugin_path
        self._custom_tsdk_path = tsdk_path
        self._explicit_ts_ls_executable = ts_ls_executable_path
        super().__init__(config, repository_root_path, solidlsp_settings)

    @override
    def get_source_fn_matcher(self) -> FilenameMatcher:
        # Include .astro so references returned by the plugin are not filtered out
        return LanguageServerId.ASTRO.get_source_fn_matcher()

    @override
    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(
            self._custom_settings,
            self._ls_resources_dir,
            self._explicit_ts_ls_executable,
        )

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        """.astro files map to 'astro' to activate the plugin; TS/JS as normal."""
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext in ASTRO_EXT:
            return "astro"
        if ext == ".tsx":
            return "typescriptreact"
        if ext == ".jsx":
            return "javascriptreact"
        if ext in TS_EXT:
            return "typescript"
        if ext in JS_EXT:
            return "javascript"
        return "typescript"

    @override
    def _create_base_initialize_params(self) -> dict:
        params = super()._create_base_initialize_params()
        params["initializationOptions"] = {
            "plugins": [
                {
                    "name": "@astrojs/ts-plugin",
                    "location": self._astro_plugin_path,
                    "languages": ["astro"],
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

    @override
    def _handle_server_ready_timeout(self, timeout: float) -> None:
        log.warning("Astro companion TypeScript server did not become ready within %.0fs; proceeding", timeout)
        self.server_ready.set()

    @override
    def _handle_project_indexing_timeout(self, timeout: float) -> None:
        log.warning(
            "Astro companion TypeScript server project indexing did not complete within %.0fs (%s)",
            timeout,
            self.describe_indexing_state(),
        )


class AstroLanguageServer(SolidLanguageServer):
    """
    Astro language server using @astrojs/language-server with companion TypeScript LS.
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
            if shutil.which("node") is None:
                raise SolidLSPException("node is not installed or isn't in PATH. Please install NodeJS and try again.")
            if shutil.which("npm") is None:
                raise SolidLSPException("npm is not installed or isn't in PATH. Please install npm and try again.")

            package_version = self._custom_settings.get("astro_language_server_version", "2.17.0")
            typescript_version = self._custom_settings.get("typescript_version", self._ts_settings.get("typescript_version", "5.9.3"))
            typescript_language_server_version = self._custom_settings.get(
                "typescript_language_server_version",
                self._ts_settings.get("typescript_language_server_version", "5.1.3"),
            )
            astro_ts_plugin_version = self._custom_settings.get("astro_ts_plugin_version", "1.10.10")
            npm_registry = self._custom_settings.get("npm_registry", self._ts_settings.get("npm_registry"))

            install_dir = os.path.join(self._ls_resources_dir, f"astro-lsp-{package_version}")
            executable_path = os.path.join(install_dir, "node_modules", ".bin", "astro-ls")
            ts_ls_executable = os.path.join(install_dir, "node_modules", ".bin", "typescript-language-server")
            if os.name == "nt":
                executable_path += ".cmd"
                ts_ls_executable += ".cmd"

            version_file = os.path.join(install_dir, ".installed_version")
            expected_version = f"{package_version}_{typescript_version}_{typescript_language_server_version}_{astro_ts_plugin_version}"
            needs_install = not os.path.exists(executable_path) or not os.path.exists(ts_ls_executable)
            if not needs_install:
                if os.path.exists(version_file):
                    with open(version_file) as fv:
                        if fv.read().strip() != expected_version:
                            needs_install = True
                else:
                    needs_install = True

            if needs_install:
                log.info(
                    "Installing @astrojs/language-server@%s + @astrojs/ts-plugin@%s + typescript@%s + typescript-language-server@%s ...",
                    package_version,
                    astro_ts_plugin_version,
                    typescript_version,
                    typescript_language_server_version,
                )
                runtime_deps = [
                    RuntimeDependency(
                        id="@astrojs/language-server",
                        description="Astro language server",
                        command=build_npm_install_command("@astrojs/language-server", package_version, npm_registry),
                        platform_id="any",
                    ),
                    RuntimeDependency(
                        id="@astrojs/ts-plugin",
                        description="Astro TypeScript plugin for cross-file code intelligence",
                        command=build_npm_install_command("@astrojs/ts-plugin", astro_ts_plugin_version, npm_registry),
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
                ]
                RuntimeDependencyCollection(runtime_deps).install(install_dir)
                with open(version_file, "w") as fv:
                    fv.write(expected_version)

            if not os.path.exists(executable_path):
                raise FileNotFoundError(
                    f"executable not found at {executable_path}; "
                    f"npm install of @astrojs/language-server@{package_version} did not produce the expected binary."
                )
            return executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "--stdio"]

    @override
    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        ts_settings = self._solidlsp_settings.get_ls_specific_settings(LanguageServerId.TYPESCRIPT)
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir, ts_settings)

    def __init__(self, config: LanguageServerConfig, repo_path: str, solidlsp_settings: SolidLSPSettings) -> None:
        resolved_root = os.path.abspath(repo_path)
        super().__init__(
            config,
            resolved_root,
            None,
            "astro",
            solidlsp_settings,
        )
        self.repo_path: str = resolved_root
        self.tsdk_path = self._get_tsdk_path()
        self._ts_server: AstroTypeScriptServer | None = None
        self._ts_server_started: bool = False
        self._astro_files_indexed: bool = False
        self._indexed_astro_file_uris: list[str] = []

    def _get_install_dir(self) -> str:
        version = self._custom_settings.get("astro_language_server_version", "2.17.0")
        return os.path.join(self._ls_resources_dir, f"astro-lsp-{version}")

    def _get_tsdk_path(self) -> str:
        tsdk_candidate = os.path.join(self._get_install_dir(), "node_modules", "typescript", "lib")
        if not os.path.isdir(tsdk_candidate):
            raise FileNotFoundError(
                f"TypeScript SDK not found at expected path: {tsdk_candidate}. Installation via DependencyProvider failed or version mismatch."
            )
        return tsdk_candidate

    def _get_ts_ls_executable(self) -> str:
        path = os.path.join(self._get_install_dir(), "node_modules", ".bin", "typescript-language-server")
        if os.name == "nt":
            path += ".cmd"
        return path

    def _get_astro_ts_plugin_path(self) -> str:
        return os.path.join(self._get_install_dir(), "node_modules", "@astrojs", "ts-plugin")

    def _find_all_astro_files(self) -> list[str]:
        astro_files = []
        repo = pathlib.Path(self.repo_path)
        for astro_file in repo.rglob("*.astro"):
            try:
                relative = str(astro_file.relative_to(repo))
                if "node_modules" not in relative and not relative.startswith("."):
                    astro_files.append(relative)
            except Exception as exc:
                log.debug("Error processing astro file %s: %s", astro_file, exc)
        return astro_files

    def _get_companion_indexing_timeout(self) -> float:
        ts_settings = self._solidlsp_settings.get_ls_specific_settings(LanguageServerId.TYPESCRIPT)
        timeout = self._custom_settings.get(
            "indexing_timeout",
            ts_settings.get("indexing_timeout", AstroTypeScriptServer.INDEXING_PROGRESS_TIMEOUT),
        )
        return float(timeout)

    def _ensure_astro_files_indexed_on_ts_server(self) -> None:
        if self._astro_files_indexed:
            return
        if self._ts_server is None:
            return

        log.info("Indexing .astro files on companion TypeScript server for cross-file awareness")
        astro_files = self._find_all_astro_files()
        log.debug("Found %d .astro files to index", len(astro_files))

        self._ts_server.expect_indexing()

        failed_astro_files = []
        first_open_error: Exception | None = None
        for astro_file in astro_files:
            try:
                with self._ts_server.open_file(astro_file) as file_buffer:
                    file_buffer.ref_count += 1
                    self._indexed_astro_file_uris.append(file_buffer.uri)
            except Exception as exc:
                log.debug("Failed to open %s on companion TS server: %s", astro_file, exc)
                if first_open_error is None:
                    first_open_error = exc
                failed_astro_files.append(astro_file)

        if failed_astro_files:
            shown_files = sorted(failed_astro_files)[:_MAX_FAILED_FILES_IN_ERROR]
            remainder = len(failed_astro_files) - len(shown_files)
            listing = ", ".join(shown_files) + (f" and {remainder} more" if remainder else "")
            raise AstroCompanionPreparationError(
                f"Failed to open {len(failed_astro_files)} Astro file(s) on companion TypeScript server: {listing}"
            ) from first_open_error

        self._astro_files_indexed = True
        log.info("Astro file indexing complete; waiting for companion TS server to finish processing")

        timeout = self._get_companion_indexing_timeout()
        if self._ts_server._wait_for_indexing_start_or_completion(timeout=timeout):
            log.info("Companion TypeScript server finished indexing .astro files")
        else:
            log.warning(
                "Companion TypeScript server did not finish indexing %d .astro files within %.0fs (%s); proceeding",
                len(astro_files),
                timeout,
                self._ts_server.describe_indexing_state(),
            )

    def _cleanup_indexed_astro_files(self) -> None:
        if not self._indexed_astro_file_uris or self._ts_server is None:
            return
        log.debug("Cleaning up %d indexed .astro files", len(self._indexed_astro_file_uris))
        for uri in self._indexed_astro_file_uris:
            try:
                if uri in self._ts_server.open_file_buffers:
                    file_buffer = self._ts_server.open_file_buffers[uri]
                    file_buffer.ref_count -= 1
                    if file_buffer.ref_count == 0:
                        self._ts_server.server.notify.did_close_text_document({"textDocument": {"uri": uri}})
                        del self._ts_server.open_file_buffers[uri]
            except Exception as exc:
                log.debug("Error closing indexed astro file %s: %s", uri, exc)
        self._indexed_astro_file_uris.clear()

    def _start_typescript_server(self) -> None:
        try:
            ts_config = LanguageServerConfig(
                ls_id=LanguageServerId.TYPESCRIPT,
                trace_lsp_communication=False,
            )
            log.info("Creating companion AstroTypeScriptServer")
            self._ts_server = AstroTypeScriptServer(
                config=ts_config,
                repository_root_path=self.repo_path,
                solidlsp_settings=self._solidlsp_settings,
                astro_plugin_path=self._get_astro_ts_plugin_path(),
                tsdk_path=self.tsdk_path,
                ts_ls_executable_path=self._get_ts_ls_executable(),
            )
            log.info("Starting companion AstroTypeScriptServer")
            self._ts_server.start()
            self._ts_server_started = True
            log.info("Companion AstroTypeScriptServer ready")
            self._ensure_astro_files_indexed_on_ts_server()
        except (TimeoutError, AstroCompanionPreparationError):
            log.exception("Failed to prepare companion AstroTypeScriptServer; aborting Astro server startup")
            self._stop_typescript_server()
            raise
        except Exception:
            log.exception("Error starting companion AstroTypeScriptServer; TS-side operations degrade to astro LS")
            self._ts_server = None
            self._ts_server_started = False

    def _stop_typescript_server(self) -> None:
        if self._ts_server is not None:
            self._cleanup_indexed_astro_files()
            try:
                log.info("Stopping companion AstroTypeScriptServer")
                self._ts_server.stop()
            except Exception as exc:
                log.warning("Error stopping companion AstroTypeScriptServer: %s", exc)
            finally:
                self._ts_server = None
                self._ts_server_started = False

    def _forward_edit_to_ts_server_if_needed(self, relative_file_path: str, edit_fn: Callable[[], object]) -> None:
        if self._ts_server is None or not self._ts_server_started:
            return

        absolute_file_path = os.path.abspath(os.path.join(self.repo_path, relative_file_path))
        uri = pathlib.Path(absolute_file_path).as_uri()
        if uri in self._ts_server.open_file_buffers:
            edit_fn()

    @override
    def insert_text_at_position(self, relative_file_path: str, line: int, column: int, text_to_be_inserted: str) -> ls_types.Position:
        result = super().insert_text_at_position(relative_file_path, line, column, text_to_be_inserted)
        self._forward_edit_to_ts_server_if_needed(
            relative_file_path,
            lambda: self._ts_server.insert_text_at_position(  # type: ignore[union-attr]
                relative_file_path, line, column, text_to_be_inserted
            ),
        )
        return result

    @override
    def delete_text_between_positions(
        self,
        relative_file_path: str,
        start: ls_types.Position,
        end: ls_types.Position,
    ) -> str:
        deleted_text = super().delete_text_between_positions(relative_file_path, start, end)
        self._forward_edit_to_ts_server_if_needed(
            relative_file_path,
            lambda: self._ts_server.delete_text_between_positions(  # type: ignore[union-attr]
                relative_file_path, start, end
            ),
        )
        return deleted_text

    def _create_base_initialize_params(self) -> dict:
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
                "typescript": {
                    "tsdk": self.tsdk_path,
                },
            },
        }
        return initialize_params

    def _start_server(self) -> None:
        def window_log_message(msg: dict) -> None:
            log.info("LSP: window/logMessage: %s", msg)

        def register_capability_handler(params: dict) -> None:
            if "registrations" not in params:
                raise SolidLSPException(f"Expected registrations in client/registerCapability params: {params}")

        def configuration_handler(params: dict) -> list:
            items = params.get("items", [])
            results = []
            for item in items:
                section = item.get("section", "") if isinstance(item, dict) else ""
                if section.endswith(".customData"):
                    results.append([])
                else:
                    results.append({})
            return results

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
        self.server.on_request("workspace/inlayHint/refresh", do_nothing)
        self.server.on_request("workspace/semanticTokens/refresh", do_nothing)
        self.server.start()

        init_params = self._create_initialize_params()
        init_response = self.server.send.initialize(init_params)

        if "documentSymbolProvider" not in init_response.get("capabilities", {}):
            raise SolidLSPException("Astro LSP did not advertise documentSymbolProvider")
        if "definitionProvider" not in init_response.get("capabilities", {}):
            raise SolidLSPException("Astro LSP did not advertise definitionProvider")

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
        symbol_refs = super().request_references(relative_file_path, line, column)

        if _is_ts_file(relative_file_path):
            if self._ts_server is not None:
                with self._ts_server.open_file(relative_file_path):
                    ts_refs = self._ts_server.request_references(relative_file_path, line, column)
                symbol_refs = self._deduplicate_reference_locations(symbol_refs, ts_refs)
        elif _is_astro_file(relative_file_path):
            if self._ts_server is not None:
                try:
                    with self._ts_server.open_file(relative_file_path):
                        ts_refs = self._ts_server.request_references(relative_file_path, line, column)
                    symbol_refs = self._deduplicate_reference_locations(symbol_refs, ts_refs)
                except Exception as exc:
                    log.debug("Companion TS references failed for %s: %s", relative_file_path, exc)

        return symbol_refs

    @override
    def request_rename_symbol_edit(self, relative_file_path: str, line: int, column: int, new_name: str) -> ls_types.WorkspaceEdit | None:
        if _is_ts_file(relative_file_path) and self._ts_server is not None:
            with self._ts_server.open_file(relative_file_path):
                return self._ts_server.request_rename_symbol_edit(relative_file_path, line, column, new_name)
        return super().request_rename_symbol_edit(relative_file_path, line, column, new_name)

    @override
    def request_definition(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        if _is_ts_file(relative_file_path) and self._ts_server is not None:
            with self._ts_server.open_file(relative_file_path):
                return self._ts_server.request_definition(relative_file_path, line, column)
        return super().request_definition(relative_file_path, line, column)

    @override
    def request_document_symbols(self, relative_file_path: str, file_buffer: LSPFileBuffer | None = None) -> DocumentSymbols:
        if _is_ts_file(relative_file_path) and self._ts_server is not None:
            return self._ts_server.request_document_symbols(relative_file_path)
        return super().request_document_symbols(relative_file_path, file_buffer)

    @override
    def request_text_document_diagnostics(
        self,
        relative_file_path: str,
        start_line: int = 0,
        end_line: int = -1,
        min_severity: int = 4,
    ) -> list[ls_types.Diagnostic]:
        if _is_ts_file(relative_file_path) and self._ts_server is not None:
            with self._ts_server.open_file(relative_file_path):
                return self._ts_server.request_text_document_diagnostics(relative_file_path, start_line, end_line, min_severity)
        return super().request_text_document_diagnostics(relative_file_path, start_line, end_line, min_severity)

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext in ASTRO_EXT:
            return "astro"
        if ext == ".tsx":
            return "typescriptreact"
        if ext == ".jsx":
            return "javascriptreact"
        if ext in TS_EXT:
            return "typescript"
        if ext in JS_EXT:
            return "javascript"
        return self.language_id

    @override
    def _get_preferred_definition(self, definitions: list[ls_types.Location]) -> ls_types.Location:
        return prefer_non_node_modules_definition(definitions)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "dist",
            "build",
            "coverage",
            ".astro",
        ]
