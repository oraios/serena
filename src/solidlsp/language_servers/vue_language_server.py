"""
Vue Language Server implementation using @vue/language-server (Volar) with companion TypeScript LS.
Operates in hybrid mode: Vue LS handles .vue files, TypeScript LS handles .ts/.js files.
"""

import logging
import os
import pathlib
import shutil
import threading
from collections.abc import Callable
from pathlib import Path, PurePath
from time import sleep
from typing import Any

from overrides import override

from solidlsp import ls_types
from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command
from solidlsp.language_servers.typescript_language_server import (
    TypeScriptLanguageServer,
    prefer_non_node_modules_definition,
)
from solidlsp.ls import LanguageServerDependencyProvider, LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import FilenameMatcher, Language, LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_types import Location
from solidlsp.ls_utils import PathUtils
from solidlsp.lsp_protocol_handler import lsp_types
from solidlsp.lsp_protocol_handler.lsp_types import DocumentSymbol, ExecuteCommandParams, InitializeParams, SymbolInformation
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class VueTypeScriptServer(TypeScriptLanguageServer):
    """TypeScript LS configured with @vue/typescript-plugin for Vue file support."""

    @classmethod
    @override
    def get_language_enum_instance(cls) -> Language:
        """Return TYPESCRIPT since this is a TypeScript language server variant.

        Note: VueTypeScriptServer is a companion server that uses TypeScript's language server
        with the Vue TypeScript plugin. It reports as TYPESCRIPT to maintain compatibility
        with the TypeScript language server infrastructure.
        """
        return Language.TYPESCRIPT

    def get_source_fn_matcher(self) -> FilenameMatcher:
        # must override with Vue-specific matcher to ensure .vue files are included (as they can be discovered via references,
        # for instance; otherwise, we may find references in .vue files but then filter the results out, because .vue files are ignored.)
        return Language.VUE.get_source_fn_matcher()

    class DependencyProvider(TypeScriptLanguageServer.DependencyProvider):
        """Dependency provider that returns a pre-resolved executable path.

        The Vue LS install (run by ``VueLanguageServer._setup_runtime_dependencies``)
        already locates the ``typescript-language-server`` binary alongside the Vue
        language server, so the companion does not need to perform another install
        lookup — it just returns the path it was constructed with.
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

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        """Return the correct language ID for files.

        Vue files must be opened with language ID "vue" for the @vue/typescript-plugin
        to process them correctly. The plugin is configured with "languages": ["vue"]
        in the initialization options.
        """
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext == ".vue":
            return "vue"
        elif ext in (".ts", ".tsx", ".mts", ".cts"):
            return "typescript"
        elif ext in (".js", ".jsx", ".mjs", ".cjs"):
            return "javascript"
        else:
            return "typescript"

    def __init__(
        self,
        config: LanguageServerConfig,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
        vue_plugin_path: str,
        tsdk_path: str,
        ts_ls_executable_path: str,
    ):
        self._vue_plugin_path = vue_plugin_path
        self._custom_tsdk_path = tsdk_path
        # Stored as instance state so the override survives across concurrent
        # constructions of multiple VueLanguageServer instances. The class
        # attribute pattern this replaces was racy: two parallel constructors
        # could see each other's value in the brief window between assignment
        # and reset.
        self._explicit_ts_ls_executable = ts_ls_executable_path
        super().__init__(config, repository_root_path, solidlsp_settings)

    @override
    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(
            self._custom_settings,
            self._ls_resources_dir,
            self._explicit_ts_ls_executable,
        )

    @override
    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        params = super()._get_initialize_params(repository_absolute_path)

        params["initializationOptions"] = {
            "plugins": [
                {
                    "name": "@vue/typescript-plugin",
                    "location": self._vue_plugin_path,
                    "languages": ["vue"],
                }
            ],
            "tsserver": {
                "path": self._custom_tsdk_path,
            },
        }

        if "workspace" in params["capabilities"]:
            params["capabilities"]["workspace"]["executeCommand"] = {"dynamicRegistration": True}

        return params

    @override
    def _start_server(self) -> None:
        def workspace_configuration_handler(params: dict) -> list:
            items = params.get("items", [])
            return [{} for _ in items]

        self.server.on_request("workspace/configuration", workspace_configuration_handler)
        super()._start_server()


class VueLanguageServer(SolidLanguageServer):
    """
    Language server for Vue Single File Components using @vue/language-server (Volar) with companion TypeScript LS.

    You can pass the following entries in ls_specific_settings["vue"]:
        - vue_language_server_version: Version of @vue/language-server to install (default: "3.1.5")

    Note: TypeScript versions are configured via ls_specific_settings["typescript"]:
        - typescript_version: Version of TypeScript to install (default: "5.9.3")
        - typescript_language_server_version: Version of typescript-language-server to install (default: "5.1.3")
    """

    TS_SERVER_READY_TIMEOUT = 5.0
    VUE_SERVER_READY_TIMEOUT = 3.0

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        vue_lsp_executable_path, self.tsdk_path, self._ts_ls_cmd = self._setup_runtime_dependencies(config, solidlsp_settings)
        self._vue_ls_dir = os.path.join(self.ls_resources_dir(solidlsp_settings), "vue-lsp")
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=vue_lsp_executable_path, cwd=repository_root_path),
            "vue",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()
        self._ts_server: VueTypeScriptServer | None = None
        self._ts_server_started = False
        self._vue_files_indexed = False
        self._indexed_vue_file_uris: list[str] = []
        self._ls_operational_ready_event = threading.Event()
        self._ls_operational_lock = threading.Lock()
        self._ls_operational_thread: threading.Thread | None = None

    def _warm_up_ls_operational_state(self) -> None:
        """Warm up the Vue language server operational state asynchronously."""
        # execute the operational warm-up
        try:
            self._ensure_ls_operational()
        except SolidLSPException:
            if not self.server_started:
                log.debug("Skipping Vue language server operational warm-up because the server is stopping")
                return
            log.exception("Error while warming up Vue language server operational state")
        except Exception:
            log.exception("Error while warming up Vue language server operational state")

    def _ensure_ls_operational(self) -> None:
        # short-circuit completed warm-up
        if self._ls_operational_ready_event.is_set():
            return

        # serialize the warm-up sequence
        with self._ls_operational_lock:
            # short-circuit repeated callers after waiting for the lock
            if self._ls_operational_ready_event.is_set():
                return

            # validate server availability
            if not self.server_started:
                raise SolidLSPException("Language Server not started")

            # wait for cross-file reference readiness
            if not self._has_waited_for_cross_file_references:
                sleep(self._get_wait_time_for_cross_file_referencing())
                self._has_waited_for_cross_file_references = True

            # index Vue files on the companion TypeScript server
            self._ensure_vue_files_indexed_on_ts_server()

            # publish operational readiness
            self._ls_operational_ready_event.set()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",
            "dist",
            "build",
            "coverage",
            ".nuxt",
            ".output",
        ]

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext == ".vue":
            return "vue"
        elif ext in (".ts", ".tsx", ".mts", ".cts"):
            return "typescript"
        elif ext in (".js", ".jsx", ".mjs", ".cjs"):
            return "javascript"
        else:
            return "vue"

    def _is_typescript_file(self, file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        return ext in (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")

    def _find_all_vue_files(self) -> list[str]:
        vue_files = []
        repo_path = Path(self.repository_root_path)

        for vue_file in repo_path.rglob("*.vue"):
            try:
                relative_path = str(vue_file.relative_to(repo_path))
                if "node_modules" not in relative_path and not relative_path.startswith("."):
                    vue_files.append(relative_path)
            except Exception as e:
                log.debug(f"Error processing Vue file {vue_file}: {e}")

        return vue_files

    def _ensure_vue_files_indexed_on_ts_server(self) -> None:
        if self._vue_files_indexed:
            return

        assert self._ts_server is not None
        log.info("Indexing .vue files on TypeScript server for cross-file references")
        vue_files = self._find_all_vue_files()
        log.debug(f"Found {len(vue_files)} .vue files to index")

        # Prepare the TS server to track new $/progress notifications triggered
        # by the didOpen calls below. Must happen BEFORE opening files to avoid
        # a race where progress begins and ends before we start waiting.
        self._ts_server.expect_indexing()

        for vue_file in vue_files:
            try:
                with self._ts_server.open_file(vue_file) as file_buffer:
                    file_buffer.ref_count += 1
                    self._indexed_vue_file_uris.append(file_buffer.uri)
            except Exception as e:
                log.debug(f"Failed to open {vue_file} on TS server: {e}")

        self._vue_files_indexed = True
        log.info("Vue file indexing on TypeScript server complete, waiting for TS server to finish processing")

        self._wait_for_ts_indexing_complete()

    def _wait_for_ts_indexing_complete(self) -> None:
        """Wait for the companion TypeScript server to finish processing opened Vue files.

        Uses the $/progress tracking in TypeScriptLanguageServer: after Vue files are
        opened, tsserver sends "Initializing JS/TS language features…" progress.
        We wait for all progress tokens to complete, with a timeout fallback.
        """
        assert self._ts_server is not None
        timeout = TypeScriptLanguageServer.INDEXING_PROGRESS_TIMEOUT
        if self._ts_server.wait_for_indexing(timeout=timeout):
            log.info("TypeScript server finished indexing Vue files (signaled via $/progress)")
        else:
            log.warning(f"Timeout ({timeout}s) waiting for TypeScript server to finish indexing Vue files, proceeding anyway")

    def _send_references_request(self, relative_file_path: str, line: int, column: int) -> list[lsp_types.Location] | None:
        uri = PathUtils.path_to_uri(os.path.join(self.repository_root_path, relative_file_path))
        request_params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": column},
            "context": {"includeDeclaration": False},
        }

        return self.server.send.references(request_params)  # type: ignore[arg-type]

    def _send_ts_references_request(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        assert self._ts_server is not None
        uri = PathUtils.path_to_uri(os.path.join(self.repository_root_path, relative_file_path))
        request_params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": column},
            "context": {"includeDeclaration": True},
        }

        with self._ts_server.open_file(relative_file_path):
            response = self._ts_server.handler.send.references(request_params)  # type: ignore[arg-type]

        result: list[ls_types.Location] = []
        if response is not None:
            for item in response:
                abs_path = PathUtils.uri_to_path(item["uri"])
                if not Path(abs_path).is_relative_to(self.repository_root_path):
                    log.debug(f"Found reference outside repository: {abs_path}, skipping")
                    continue

                rel_path = Path(abs_path).relative_to(self.repository_root_path)
                if self.is_ignored_path(str(rel_path)):
                    log.debug(f"Ignoring reference in {rel_path}")
                    continue

                new_item: dict = {}
                new_item.update(item)  # type: ignore[arg-type]
                new_item["absolutePath"] = str(abs_path)
                new_item["relativePath"] = str(rel_path)
                result.append(ls_types.Location(**new_item))  # type: ignore

        return result

    def request_file_references(self, relative_file_path: str) -> list:
        self._ensure_ls_operational()

        absolute_file_path = os.path.join(self.repository_root_path, relative_file_path)
        uri = PathUtils.path_to_uri(absolute_file_path)

        request_params = {"textDocument": {"uri": uri}}

        log.info(f"Sending volar/client/findFileReference request for {relative_file_path}")
        log.info(f"Request URI: {uri}")
        log.info(f"Request params: {request_params}")

        try:
            with self.open_file(relative_file_path):
                log.debug(f"Sending volar/client/findFileReference for {relative_file_path}")
                log.debug(f"Request params: {request_params}")

                response = self.server.send_request("volar/client/findFileReference", request_params)

                log.debug(f"Received response type: {type(response)}")

            log.info(f"Received file references response: {response}")
            log.info(f"Response type: {type(response)}")

            if response is None:
                log.debug(f"No file references found for {relative_file_path}")
                return []

            # Response should be an array of Location objects
            if not isinstance(response, list):
                log.warning(f"Unexpected response format from volar/client/findFileReference: {type(response)}")
                return []

            ret: list[Location] = []
            for item in response:
                if not isinstance(item, dict) or "uri" not in item:
                    log.debug(f"Skipping invalid location item: {item}")
                    continue

                abs_path = PathUtils.uri_to_path(item["uri"])  # type: ignore[arg-type]
                if not Path(abs_path).is_relative_to(self.repository_root_path):
                    log.warning(f"Found file reference outside repository: {abs_path}, skipping")
                    continue

                rel_path = Path(abs_path).relative_to(self.repository_root_path)
                if self.is_ignored_path(str(rel_path)):
                    log.debug(f"Ignoring file reference in {rel_path}")
                    continue

                new_item: dict = {}
                new_item.update(item)  # type: ignore[arg-type]
                new_item["absolutePath"] = str(abs_path)
                new_item["relativePath"] = str(rel_path)
                ret.append(Location(**new_item))  # type: ignore

            log.debug(f"Found {len(ret)} file references for {relative_file_path}")
            return ret

        except Exception as e:
            log.warning(f"Error requesting file references for {relative_file_path}: {e}")
            return []

    @override
    def request_references(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        self._ensure_ls_operational()
        symbol_refs = self._send_ts_references_request(relative_file_path, line=line, column=column)

        if relative_file_path.endswith(".vue"):
            log.info(f"Attempting to find file-level references for Vue component {relative_file_path}")
            file_refs = self.request_file_references(relative_file_path)
            log.info(f"file_refs result: {len(file_refs)} references found")

            seen = set()
            for ref in symbol_refs:
                key = (ref["uri"], ref["range"]["start"]["line"], ref["range"]["start"]["character"])
                seen.add(key)

            for file_ref in file_refs:
                key = (file_ref["uri"], file_ref["range"]["start"]["line"], file_ref["range"]["start"]["character"])
                if key not in seen:
                    symbol_refs.append(file_ref)
                    seen.add(key)

            log.info(f"Total references for {relative_file_path}: {len(symbol_refs)} (symbol refs + file refs, deduplicated)")

        return symbol_refs

    @override
    def request_definition(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        self._ensure_ls_operational()
        assert self._ts_server is not None
        with self._ts_server.open_file(relative_file_path):
            return self._ts_server.request_definition(relative_file_path, line, column)

    @override
    def request_rename_symbol_edit(self, relative_file_path: str, line: int, column: int, new_name: str) -> ls_types.WorkspaceEdit | None:
        self._ensure_ls_operational()
        assert self._ts_server is not None
        with self._ts_server.open_file(relative_file_path):
            return self._ts_server.request_rename_symbol_edit(relative_file_path, line, column, new_name)

    @override
    def request_text_document_diagnostics(
        self,
        relative_file_path: str,
        start_line: int = 0,
        end_line: int = -1,
        min_severity: int = 4,
    ) -> list[ls_types.Diagnostic]:
        self._ensure_ls_operational()
        assert self._ts_server is not None
        return self._ts_server.request_text_document_diagnostics(relative_file_path, start_line, end_line, min_severity)

    def _forward_edit_to_ts_server_if_needed(self, relative_file_path: str, edit_fn: Callable[[], object]) -> None:
        """
        Calls ``edit_fn`` on the TypeScript server if the file is open there.

        Only applicable to non-TypeScript files (i.e. .vue files) that have been
        indexed on the TypeScript server for cross-file reference support.

        :param relative_file_path: the relative path of the file that was edited
        :param edit_fn: callable that performs the corresponding edit on ``_ts_server``
        """
        if self._ts_server is None or not self._ts_server_started:
            return
        if self._is_typescript_file(relative_file_path):
            return

        absolute_file_path = str(PurePath(self.repository_root_path, relative_file_path))
        uri = pathlib.Path(absolute_file_path).as_uri()
        if uri in self._ts_server.open_file_buffers:
            edit_fn()

    @override
    def insert_text_at_position(self, relative_file_path: str, line: int, column: int, text_to_be_inserted: str) -> ls_types.Position:
        """
        Inserts text at the given position, forwarding the change to the TypeScript server if it has the file open.

        :param relative_file_path: the relative path of the file to edit
        :param line: the line number
        :param column: the column number
        :param text_to_be_inserted: the text to insert
        :return: updated cursor position
        """
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
        """
        Deletes text between the given positions, forwarding the change to the TypeScript server if it has the file open.

        :param relative_file_path: the relative path of the file to edit
        :param start: start position
        :param end: end position
        :return: deleted text
        """
        deleted_text = super().delete_text_between_positions(relative_file_path, start, end)
        self._forward_edit_to_ts_server_if_needed(
            relative_file_path,
            lambda: self._ts_server.delete_text_between_positions(  # type: ignore[union-attr]
                relative_file_path, start, end
            ),
        )
        return deleted_text

    @classmethod
    def _setup_runtime_dependencies(cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings) -> tuple[list[str], str, str]:
        is_node_installed = shutil.which("node") is not None
        assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
        is_npm_installed = shutil.which("npm") is not None
        assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."

        # Get TypeScript version settings from TypeScript language server settings
        typescript_config = solidlsp_settings.get_ls_specific_settings(Language.TYPESCRIPT)
        typescript_version = typescript_config.get("typescript_version", "5.9.3")
        typescript_language_server_version = typescript_config.get("typescript_language_server_version", "5.1.3")
        vue_config = solidlsp_settings.get_ls_specific_settings(Language.VUE)
        vue_language_server_version = vue_config.get("vue_language_server_version", "3.1.5")
        npm_registry = vue_config.get("npm_registry", typescript_config.get("npm_registry"))

        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="vue-language-server",
                    description="Vue language server package (Volar)",
                    command=build_npm_install_command("@vue/language-server", vue_language_server_version, npm_registry),
                    platform_id="any",
                ),
                RuntimeDependency(
                    id="typescript",
                    description="TypeScript (required for tsdk)",
                    command=build_npm_install_command("typescript", typescript_version, npm_registry),
                    platform_id="any",
                ),
                RuntimeDependency(
                    id="typescript-language-server",
                    description="TypeScript language server (for Vue LS 3.x tsserver forwarding)",
                    command=build_npm_install_command("typescript-language-server", typescript_language_server_version, npm_registry),
                    platform_id="any",
                ),
            ]
        )

        vue_ls_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), "vue-lsp")
        vue_executable_path = os.path.join(vue_ls_dir, "node_modules", ".bin", "vue-language-server")
        ts_ls_executable_path = os.path.join(vue_ls_dir, "node_modules", ".bin", "typescript-language-server")

        if os.name == "nt":
            vue_executable_path += ".cmd"
            ts_ls_executable_path += ".cmd"

        tsdk_path = os.path.join(vue_ls_dir, "node_modules", "typescript", "lib")

        # Check if installation is needed based on executables AND version
        version_file = os.path.join(vue_ls_dir, ".installed_version")
        expected_version = f"{vue_language_server_version}_{typescript_version}_{typescript_language_server_version}"

        needs_install = False
        if not os.path.exists(vue_executable_path) or not os.path.exists(ts_ls_executable_path):
            log.info("Vue/TypeScript Language Server executables not found.")
            needs_install = True
        elif os.path.exists(version_file):
            with open(version_file) as f:
                installed_version = f.read().strip()
            if installed_version != expected_version:
                log.info(
                    f"Vue Language Server version mismatch: installed={installed_version}, expected={expected_version}. Reinstalling..."
                )
                needs_install = True
        else:
            # No version file exists, assume old installation needs refresh
            log.info("Vue Language Server version file not found. Reinstalling to ensure correct version...")
            needs_install = True

        if needs_install:
            log.info("Installing Vue/TypeScript Language Server dependencies...")
            deps.install(vue_ls_dir)
            # Write version marker file
            with open(version_file, "w") as f:
                f.write(expected_version)
            log.info("Vue language server dependencies installed successfully")

        if not os.path.exists(vue_executable_path):
            raise FileNotFoundError(
                f"vue-language-server executable not found at {vue_executable_path}, something went wrong with the installation."
            )

        if not os.path.exists(ts_ls_executable_path):
            raise FileNotFoundError(
                f"typescript-language-server executable not found at {ts_ls_executable_path}, something went wrong with the installation."
            )

        return [vue_executable_path, "--stdio"], tsdk_path, ts_ls_executable_path

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
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
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
            "initializationOptions": {
                "vue": {
                    "hybridMode": True,
                },
                "typescript": {
                    "tsdk": self.tsdk_path,
                },
            },
        }
        return initialize_params  # type: ignore

    def _start_typescript_server(self) -> None:
        try:
            vue_ts_plugin_path = os.path.join(self._vue_ls_dir, "node_modules", "@vue", "typescript-plugin")

            ts_config = LanguageServerConfig(
                code_language=Language.TYPESCRIPT,
                trace_lsp_communication=False,
            )

            log.info("Creating companion VueTypeScriptServer")
            self._ts_server = VueTypeScriptServer(
                config=ts_config,
                repository_root_path=self.repository_root_path,
                solidlsp_settings=self._solidlsp_settings,
                vue_plugin_path=vue_ts_plugin_path,
                tsdk_path=self.tsdk_path,
                ts_ls_executable_path=self._ts_ls_cmd,
            )

            log.info("Starting companion TypeScript server")
            self._ts_server.start()

            log.info("Waiting for companion TypeScript server to be ready...")
            if not self._ts_server.server_ready.wait(timeout=self.TS_SERVER_READY_TIMEOUT):
                log.warning(
                    f"Timeout waiting for companion TypeScript server to be ready after {self.TS_SERVER_READY_TIMEOUT} seconds, proceeding anyway"
                )
                self._ts_server.server_ready.set()

            self._ts_server_started = True
            log.info("Companion TypeScript server ready")
        except Exception as e:
            log.error(f"Error starting TypeScript server: {e}")
            self._ts_server = None
            self._ts_server_started = False
            raise

    def _forward_tsserver_request(self, method: str, params: dict) -> Any:
        if self._ts_server is None:
            log.error("Cannot forward tsserver request - TypeScript server not started")
            return None

        try:
            execute_params: ExecuteCommandParams = {
                "command": "typescript.tsserverRequest",
                "arguments": [method, params, {"isAsync": True, "lowPriority": True}],
            }
            result = self._ts_server.handler.send.execute_command(execute_params)
            log.debug(f"TypeScript server raw response for {method}: {result}")

            if isinstance(result, dict) and "body" in result:
                return result["body"]
            return result
        except Exception as e:
            log.error(f"Error forwarding tsserver request {method}: {e}")
            return None

    def _cleanup_indexed_vue_files(self) -> None:
        if not self._indexed_vue_file_uris or self._ts_server is None:
            return

        log.debug(f"Cleaning up {len(self._indexed_vue_file_uris)} indexed Vue files")
        for uri in self._indexed_vue_file_uris:
            try:
                if uri in self._ts_server.open_file_buffers:
                    file_buffer = self._ts_server.open_file_buffers[uri]
                    file_buffer.ref_count -= 1

                    if file_buffer.ref_count == 0:
                        self._ts_server.server.notify.did_close_text_document({"textDocument": {"uri": uri}})
                        del self._ts_server.open_file_buffers[uri]
                        log.debug(f"Closed indexed Vue file: {uri}")
            except Exception as e:
                log.debug(f"Error closing indexed Vue file {uri}: {e}")

        self._indexed_vue_file_uris.clear()

    def _stop_typescript_server(self) -> None:
        if self._ts_server is not None:
            try:
                log.info("Stopping companion TypeScript server")
                self._ts_server.stop()
            except Exception as e:
                log.warning(f"Error stopping TypeScript server: {e}")
            finally:
                self._ts_server = None
                self._ts_server_started = False

    @override
    def _start_server(self) -> None:
        self._start_typescript_server()

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
            return

        def configuration_handler(params: dict) -> list:
            items = params.get("items", [])
            return [{} for _ in items]

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")
            message_text = msg.get("message", "")
            if "initialized" in message_text.lower() or "ready" in message_text.lower():
                log.info("Vue language server ready signal detected")
                self.server_ready.set()

        def tsserver_request_notification_handler(params: list) -> None:
            try:
                if params and len(params) > 0 and len(params[0]) >= 2:
                    request_id = params[0][0]
                    method = params[0][1]
                    method_params = params[0][2] if len(params[0]) > 2 else {}
                    log.debug(f"Received tsserver/request: id={request_id}, method={method}")

                    if method == "_vue:projectInfo":
                        file_path = method_params.get("file", "")
                        tsconfig_path = self._find_tsconfig_for_file(file_path)
                        result = {"configFileName": tsconfig_path} if tsconfig_path else None
                        response = [[request_id, result]]
                        self.server.notify.send_notification("tsserver/response", response)
                        log.debug(f"Sent tsserver/response for projectInfo: {tsconfig_path}")
                    else:
                        result = self._forward_tsserver_request(method, method_params)
                        response = [[request_id, result]]
                        self.server.notify.send_notification("tsserver/response", response)
                        log.debug(f"Forwarded tsserver/response for {method}: {result}")
                else:
                    log.warning(f"Unexpected tsserver/request params format: {params}")
            except Exception as e:
                log.error(f"Error handling tsserver/request: {e}")

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("workspace/configuration", configuration_handler)
        self.server.on_notification("tsserver/request", tsserver_request_notification_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Vue server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response from Vue server: {init_response}")

        assert init_response["capabilities"]["textDocumentSync"] in [1, 2]

        self.server.notify.initialized({})

        log.info("Waiting for Vue language server to be ready...")
        if not self.server_ready.wait(timeout=self.VUE_SERVER_READY_TIMEOUT):
            log.info("Timeout waiting for Vue server ready signal, proceeding anyway")
            self.server_ready.set()
        else:
            log.info("Vue server initialization complete")

        # kick off asynchronous operational warm-up
        self._ls_operational_ready_event.clear()
        self._ls_operational_thread = threading.Thread(
            target=self._warm_up_ls_operational_state,
            name="vue-ls-operational-warmup",
            daemon=True,
        )
        self._ls_operational_thread.start()

    def _find_tsconfig_for_file(self, file_path: str) -> str | None:
        if not file_path:
            tsconfig_path = os.path.join(self.repository_root_path, "tsconfig.json")
            return tsconfig_path if os.path.exists(tsconfig_path) else None

        current_dir = os.path.dirname(file_path)
        repo_root = os.path.abspath(self.repository_root_path)

        while current_dir and current_dir.startswith(repo_root):
            tsconfig_path = os.path.join(current_dir, "tsconfig.json")
            if os.path.exists(tsconfig_path):
                return tsconfig_path
            parent = os.path.dirname(current_dir)
            if parent == current_dir:
                break
            current_dir = parent

        tsconfig_path = os.path.join(repo_root, "tsconfig.json")
        return tsconfig_path if os.path.exists(tsconfig_path) else None

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 5.0

    @override
    def stop(self, shutdown_timeout: float = 5.0) -> None:
        # serialize shutdown with operational warm-up
        with self._ls_operational_lock:
            self.server_started = False
            self._ls_operational_ready_event.clear()
            self._cleanup_indexed_vue_files()
            self._stop_typescript_server()
            self._ls_operational_thread = None

        super().stop(shutdown_timeout)

    @override
    def _get_preferred_definition(self, definitions: list[ls_types.Location]) -> ls_types.Location:
        return prefer_non_node_modules_definition(definitions)

    @override
    def _request_document_symbols(
        self, relative_file_path: str, file_data: LSPFileBuffer | None
    ) -> list[SymbolInformation] | list[DocumentSymbol] | None:
        """
        Override to filter out shorthand property references in Vue files.

        In Vue, when using shorthand syntax in defineExpose like `defineExpose({ pressCount })`,
        the Vue LSP returns both:
        - The Variable definition (e.g., `const pressCount = ref(0)`)
        - A Property symbol for the shorthand reference (e.g., `pressCount` in defineExpose)

        This causes duplicate symbols with the same name, which breaks symbol lookup.
        We filter out Property symbols that have a matching Variable with the same name
        at a different location (the definition), keeping only the definition.
        """
        symbols = super()._request_document_symbols(relative_file_path, file_data)

        if symbols is None or len(symbols) == 0:
            return symbols

        # Only process DocumentSymbol format (hierarchical symbols with children)
        # SymbolInformation format doesn't have the same issue
        if not isinstance(symbols[0], dict) or "range" not in symbols[0]:
            return symbols

        return self._filter_shorthand_property_duplicates(symbols)

    @staticmethod
    def _filter_shorthand_property_duplicates(
        symbols: list[DocumentSymbol] | list[SymbolInformation],
    ) -> list[DocumentSymbol] | list[SymbolInformation]:
        """
        Filter out Property symbols that have a matching Variable symbol with the same name.

        This handles Vue's shorthand property syntax in defineExpose, where the same
        identifier appears as both a Variable definition and a Property reference.
        """
        VARIABLE_KIND = 13  # SymbolKind.Variable
        PROPERTY_KIND = 7  # SymbolKind.Property

        def filter_symbols(syms: list[dict]) -> list[dict]:
            # Collect all Variable symbol names with their line numbers
            variable_names: dict[str, set[int]] = {}
            for sym in syms:
                if sym.get("kind") == VARIABLE_KIND:
                    name = sym.get("name", "")
                    line = sym.get("range", {}).get("start", {}).get("line", -1)
                    if name not in variable_names:
                        variable_names[name] = set()
                    variable_names[name].add(line)

            # Filter: keep symbols that are either:
            # 1. Not a Property, or
            # 2. A Property without a matching Variable name at a different location
            filtered = []
            for sym in syms:
                name = sym.get("name", "")
                kind = sym.get("kind")
                line = sym.get("range", {}).get("start", {}).get("line", -1)

                # If it's a Property with a matching Variable name at a DIFFERENT line, skip it
                if kind == PROPERTY_KIND and name in variable_names:
                    # Check if there's a Variable definition at a different line
                    var_lines = variable_names[name]
                    if any(var_line != line for var_line in var_lines):
                        # This is a shorthand reference, skip it
                        log.debug(
                            f"Filtering shorthand property reference '{name}' at line {line} "
                            f"(Variable definition exists at line(s) {var_lines})"
                        )
                        continue

                # Recursively filter children
                children = sym.get("children", [])
                if children:
                    sym = dict(sym)  # Create a copy to avoid mutating the original
                    sym["children"] = filter_symbols(children)

                filtered.append(sym)

            return filtered

        return filter_symbols(list(symbols))  # type: ignore
