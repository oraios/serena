"""
Svelte / SvelteKit Language Server implementation using svelte-language-server with companion TypeScript LS.
Operates in hybrid mode: Svelte LS handles .svelte files, TypeScript LS (with typescript-svelte-plugin) handles
.ts/.js files and provides cross-file references between TypeScript and Svelte.
"""

import logging
import os
import pathlib
import shutil
import threading
from collections.abc import Callable
from pathlib import Path, PurePath
from time import sleep

from overrides import override

from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command
from solidlsp.language_servers.typescript_language_server import (
    TypeScriptLanguageServer,
    prefer_non_node_modules_definition,
)
from solidlsp.ls import LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import FilenameMatcher, Language, LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_types import Location
from solidlsp.ls_utils import PathUtils
from solidlsp.lsp_protocol_handler import lsp_types
from solidlsp.lsp_protocol_handler.lsp_types import DocumentSymbol, InitializeParams, SymbolInformation
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class SvelteTypeScriptServer(TypeScriptLanguageServer):
    """TypeScript LS configured with typescript-svelte-plugin for Svelte file support."""

    @classmethod
    @override
    def get_language_enum_instance(cls) -> Language:
        """Return TYPESCRIPT since this is a TypeScript language server variant.

        :return: Language.TYPESCRIPT, as this companion server operates as a TypeScript LS
            with the Svelte plugin injected.
        """
        return Language.TYPESCRIPT

    def get_source_fn_matcher(self) -> FilenameMatcher:
        # must include .svelte files so that references discovered in .svelte files are not filtered out
        return Language.SVELTE.get_source_fn_matcher()

    class DependencyProvider(TypeScriptLanguageServer.DependencyProvider):
        override_ts_ls_executable: str | None = None

        def _get_or_install_core_dependency(self) -> str:
            if self.override_ts_ls_executable is not None:
                return self.override_ts_ls_executable
            return super()._get_or_install_core_dependency()

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        """Return the correct language ID for files.

        :param relative_file_path: relative path of the file
        :return: language ID string for the LSP textDocument/open call
        """
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext == ".svelte":
            return "svelte"
        elif ext in (".ts", ".mts", ".cts"):
            return "typescript"
        elif ext in (".js", ".mjs", ".cjs"):
            return "javascript"
        else:
            return "typescript"

    def __init__(
        self,
        config: LanguageServerConfig,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
        svelte_plugin_path: str,
        tsdk_path: str,
        ts_ls_executable_path: str,
    ):
        self._svelte_plugin_path = svelte_plugin_path
        self._custom_tsdk_path = tsdk_path
        SvelteTypeScriptServer.DependencyProvider.override_ts_ls_executable = ts_ls_executable_path
        super().__init__(config, repository_root_path, solidlsp_settings)
        SvelteTypeScriptServer.DependencyProvider.override_ts_ls_executable = None

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


class SvelteLanguageServer(SolidLanguageServer):
    """
    Language server for Svelte / SvelteKit using svelte-language-server (svelteserver) with companion TypeScript LS.

    You can pass the following entries in ls_specific_settings["svelte"]:
        - svelte_language_server_version: Version of svelte-language-server to install (default: "0.17.30")
        - typescript_svelte_plugin_version: Version of typescript-svelte-plugin to install (default: "0.3.51")

    Note: TypeScript versions are configured via ls_specific_settings["typescript"]:
        - typescript_version: Version of TypeScript to install (default: "5.9.3")
        - typescript_language_server_version: Version of typescript-language-server to install (default: "5.1.3")
    """

    TS_SERVER_READY_TIMEOUT = 5.0
    SVELTE_SERVER_READY_TIMEOUT = 5.0

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        svelte_lsp_cmd, self.tsdk_path, self._ts_ls_cmd = self._setup_runtime_dependencies(config, solidlsp_settings)
        self._svelte_ls_dir = os.path.join(self.ls_resources_dir(solidlsp_settings), "svelte-lsp")
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=svelte_lsp_cmd, cwd=repository_root_path),
            "svelte",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self._ts_server: SvelteTypeScriptServer | None = None
        self._ts_server_started = False
        self._svelte_files_indexed = False
        self._indexed_svelte_file_uris: list[str] = []
        self._ls_operational_ready_event = threading.Event()
        self._ls_operational_lock = threading.Lock()
        self._ls_operational_thread: threading.Thread | None = None

    def _warm_up_ls_operational_state(self) -> None:
        """Warm up the Svelte language server operational state asynchronously."""
        try:
            self._ensure_ls_operational()
        except SolidLSPException:
            if not self.server_started:
                log.debug("Skipping Svelte language server operational warm-up because the server is stopping")
                return
            log.exception("Error while warming up Svelte language server operational state")
        except Exception:
            log.exception("Error while warming up Svelte language server operational state")

    def _ensure_ls_operational(self) -> None:
        # short-circuit completed warm-up
        if self._ls_operational_ready_event.is_set():
            return

        # serialize the warm-up sequence
        with self._ls_operational_lock:
            if self._ls_operational_ready_event.is_set():
                return

            # validate server availability
            if not self.server_started:
                raise SolidLSPException("Language Server not started")

            # wait for cross-file reference readiness
            if not self._has_waited_for_cross_file_references:
                sleep(self._get_wait_time_for_cross_file_referencing())
                self._has_waited_for_cross_file_references = True

            # index Svelte files on the companion TypeScript server
            self._ensure_svelte_files_indexed_on_ts_server()

            # publish operational readiness
            self._ls_operational_ready_event.set()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",
            ".svelte-kit",
            "build",
            "dist",
            ".vercel",
            ".netlify",
            ".output",
        ]

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext == ".svelte":
            return "svelte"
        elif ext in (".ts", ".tsx", ".mts", ".cts"):
            return "typescript"
        elif ext in (".js", ".jsx", ".mjs", ".cjs"):
            return "javascript"
        else:
            return "svelte"

    def _is_typescript_file(self, file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        return ext in (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")

    def _find_all_svelte_files(self) -> list[str]:
        svelte_files = []
        repo_path = Path(self.repository_root_path)

        for svelte_file in repo_path.rglob("*.svelte"):
            try:
                relative_path = str(svelte_file.relative_to(repo_path))
                if not self.is_ignored_path(relative_path):
                    svelte_files.append(relative_path)
            except Exception as e:
                log.debug(f"Error processing Svelte file {svelte_file}: {e}")

        return svelte_files

    def _ensure_svelte_files_indexed_on_ts_server(self) -> None:
        if self._svelte_files_indexed:
            return

        assert self._ts_server is not None
        log.info("Indexing .svelte files on TypeScript server for cross-file references")
        svelte_files = self._find_all_svelte_files()
        log.debug(f"Found {len(svelte_files)} .svelte files to index")

        # prepare progress tracking before opening files to avoid a race
        self._ts_server.expect_indexing()

        for svelte_file in svelte_files:
            try:
                with self._ts_server.open_file(svelte_file) as file_buffer:
                    file_buffer.ref_count += 1
                    self._indexed_svelte_file_uris.append(file_buffer.uri)
            except Exception as e:
                log.debug(f"Failed to open {svelte_file} on TS server: {e}")

        self._svelte_files_indexed = True
        log.info("Svelte file indexing on TypeScript server complete, waiting for TS server to finish processing")

        self._wait_for_ts_indexing_complete()

    def _wait_for_ts_indexing_complete(self) -> None:
        """Wait for the companion TypeScript server to finish processing opened Svelte files.

        :raises: nothing; on timeout, logs a warning and continues.
        """
        assert self._ts_server is not None
        timeout = TypeScriptLanguageServer.INDEXING_PROGRESS_TIMEOUT
        if self._ts_server.wait_for_indexing(timeout=timeout):
            log.info("TypeScript server finished indexing Svelte files (signaled via $/progress)")
        else:
            log.warning(f"Timeout ({timeout}s) waiting for TypeScript server to finish indexing Svelte files, proceeding anyway")

    def _send_ts_references_request(self, relative_file_path: str, line: int, column: int) -> list[Location]:
        assert self._ts_server is not None
        uri = PathUtils.path_to_uri(os.path.join(self.repository_root_path, relative_file_path))
        request_params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": column},
            "context": {"includeDeclaration": True},
        }

        with self._ts_server.open_file(relative_file_path):
            response = self._ts_server.handler.send.references(request_params)  # type: ignore[arg-type]

        result: list[Location] = []
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
                result.append(Location(**new_item))  # type: ignore

        return result

    @override
    def request_references(self, relative_file_path: str, line: int, column: int) -> list[lsp_types.Location]:
        self._ensure_ls_operational()
        return self._send_ts_references_request(relative_file_path, line=line, column=column)

    @override
    def request_definition(self, relative_file_path: str, line: int, column: int) -> list[lsp_types.Location]:
        self._ensure_ls_operational()
        assert self._ts_server is not None
        with self._ts_server.open_file(relative_file_path):
            return self._ts_server.request_definition(relative_file_path, line, column)

    @override
    def request_rename_symbol_edit(self, relative_file_path: str, line: int, column: int, new_name: str) -> lsp_types.WorkspaceEdit | None:
        self._ensure_ls_operational()
        assert self._ts_server is not None
        with self._ts_server.open_file(relative_file_path):
            return self._ts_server.request_rename_symbol_edit(relative_file_path, line, column, new_name)

    def _forward_edit_to_ts_server_if_needed(self, relative_file_path: str, edit_fn: Callable[[], object]) -> None:
        """
        Calls ``edit_fn`` on the TypeScript server if the file is open there.

        Only applicable to non-TypeScript files (i.e. .svelte files) that have been
        indexed on the TypeScript server for cross-file reference support.

        :param relative_file_path: relative path of the file that was edited
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
    def insert_text_at_position(self, relative_file_path: str, line: int, column: int, text_to_be_inserted: str) -> lsp_types.Position:
        """
        Inserts text at the given position, forwarding the change to the TypeScript server if it has the file open.

        :param relative_file_path: relative path of the file to edit
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
        start: lsp_types.Position,
        end: lsp_types.Position,
    ) -> str:
        """
        Deletes text between the given positions, forwarding the change to the TypeScript server if it has the file open.

        :param relative_file_path: relative path of the file to edit
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

        # get version settings
        typescript_config = solidlsp_settings.get_ls_specific_settings(Language.TYPESCRIPT)
        typescript_version = typescript_config.get("typescript_version", "6.0.2")
        typescript_language_server_version = typescript_config.get("typescript_language_server_version", "5.1.3")
        svelte_config = solidlsp_settings.get_ls_specific_settings(Language.SVELTE)
        svelte_language_server_version = svelte_config.get("svelte_language_server_version", "0.17.30")
        typescript_svelte_plugin_version = svelte_config.get("typescript_svelte_plugin_version", "0.3.51")
        npm_registry = svelte_config.get("npm_registry", typescript_config.get("npm_registry"))

        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="svelte-language-server",
                    description="Svelte language server package (svelteserver)",
                    command=build_npm_install_command("svelte-language-server", svelte_language_server_version, npm_registry),
                    platform_id="any",
                ),
                RuntimeDependency(
                    id="typescript-svelte-plugin",
                    description="TypeScript plugin for Svelte cross-file references",
                    command=build_npm_install_command("typescript-svelte-plugin", typescript_svelte_plugin_version, npm_registry),
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
                    description="TypeScript language server (companion TS LS for Svelte)",
                    command=build_npm_install_command("typescript-language-server", typescript_language_server_version, npm_registry),
                    platform_id="any",
                ),
            ]
        )

        svelte_ls_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), "svelte-lsp")
        svelte_executable_path = os.path.join(svelte_ls_dir, "node_modules", ".bin", "svelteserver")
        ts_ls_executable_path = os.path.join(svelte_ls_dir, "node_modules", ".bin", "typescript-language-server")

        if os.name == "nt":
            svelte_executable_path += ".cmd"
            ts_ls_executable_path += ".cmd"

        tsdk_path = os.path.join(svelte_ls_dir, "node_modules", "typescript", "lib")

        # check if installation is needed based on executables AND version
        version_file = os.path.join(svelte_ls_dir, ".installed_version")
        expected_version = f"{svelte_language_server_version}_{typescript_svelte_plugin_version}_{typescript_version}_{typescript_language_server_version}"

        needs_install = False
        if not os.path.exists(svelte_executable_path) or not os.path.exists(ts_ls_executable_path):
            log.info("Svelte/TypeScript Language Server executables not found.")
            needs_install = True
        elif os.path.exists(version_file):
            with open(version_file) as f:
                installed_version = f.read().strip()
            if installed_version != expected_version:
                log.info(f"Svelte Language Server version mismatch: installed={installed_version}, expected={expected_version}. Reinstalling...")
                needs_install = True
        else:
            log.info("Svelte Language Server version file not found. Reinstalling to ensure correct version...")
            needs_install = True

        if needs_install:
            log.info("Installing Svelte/TypeScript Language Server dependencies...")
            deps.install(svelte_ls_dir)
            with open(version_file, "w") as f:
                f.write(expected_version)
            log.info("Svelte language server dependencies installed successfully")

        if not os.path.exists(svelte_executable_path):
            raise FileNotFoundError(
                f"svelteserver executable not found at {svelte_executable_path}, something went wrong with the installation."
            )

        if not os.path.exists(ts_ls_executable_path):
            raise FileNotFoundError(
                f"typescript-language-server executable not found at {ts_ls_executable_path}, something went wrong with the installation."
            )

        return [svelte_executable_path, "--stdio"], tsdk_path, ts_ls_executable_path

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
                "configuration": {
                    "svelte": {"plugin": {}},
                    "typescript": {"tsdk": self.tsdk_path},
                    "javascript": {},
                }
            },
        }
        return initialize_params  # type: ignore

    def _start_typescript_server(self) -> None:
        try:
            svelte_ts_plugin_path = os.path.join(self._svelte_ls_dir, "node_modules", "typescript-svelte-plugin")

            ts_config = LanguageServerConfig(
                code_language=Language.TYPESCRIPT,
                trace_lsp_communication=False,
            )

            log.info("Creating companion SvelteTypeScriptServer")
            self._ts_server = SvelteTypeScriptServer(
                config=ts_config,
                repository_root_path=self.repository_root_path,
                solidlsp_settings=self._solidlsp_settings,
                svelte_plugin_path=svelte_ts_plugin_path,
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

    def _cleanup_indexed_svelte_files(self) -> None:
        if not self._indexed_svelte_file_uris or self._ts_server is None:
            return

        log.debug(f"Cleaning up {len(self._indexed_svelte_file_uris)} indexed Svelte files")
        for uri in self._indexed_svelte_file_uris:
            try:
                if uri in self._ts_server.open_file_buffers:
                    file_buffer = self._ts_server.open_file_buffers[uri]
                    file_buffer.ref_count -= 1

                    if file_buffer.ref_count == 0:
                        self._ts_server.server.notify.did_close_text_document({"textDocument": {"uri": uri}})
                        del self._ts_server.open_file_buffers[uri]
                        log.debug(f"Closed indexed Svelte file: {uri}")
            except Exception as e:
                log.debug(f"Error closing indexed Svelte file {uri}: {e}")

        self._indexed_svelte_file_uris.clear()

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
                log.info("Svelte language server ready signal detected")
                self.server_ready.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("workspace/configuration", configuration_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Svelte server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response from Svelte server: {init_response}")

        self.server.notify.initialized({})

        log.info("Waiting for Svelte language server to be ready...")
        if not self.server_ready.wait(timeout=self.SVELTE_SERVER_READY_TIMEOUT):
            log.info("Timeout waiting for Svelte server ready signal, proceeding anyway")
            self.server_ready.set()
        else:
            log.info("Svelte server initialization complete")

        # kick off asynchronous operational warm-up
        self._ls_operational_ready_event.clear()
        self._ls_operational_thread = threading.Thread(
            target=self._warm_up_ls_operational_state,
            name="svelte-ls-operational-warmup",
            daemon=True,
        )
        self._ls_operational_thread.start()

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 5.0

    @override
    def stop(self, shutdown_timeout: float = 5.0) -> None:
        # serialize shutdown with operational warm-up
        with self._ls_operational_lock:
            self.server_started = False
            self._ls_operational_ready_event.clear()
            self._cleanup_indexed_svelte_files()
            self._stop_typescript_server()
            self._ls_operational_thread = None

        super().stop(shutdown_timeout)

    @override
    def _get_preferred_definition(self, definitions: list[lsp_types.Location]) -> lsp_types.Location:
        return prefer_non_node_modules_definition(definitions)

    @override
    def _request_document_symbols(
        self, relative_file_path: str, file_data: LSPFileBuffer | None
    ) -> list[SymbolInformation] | list[DocumentSymbol] | None:
        # delegate plain TS/JS files to the companion TypeScript server; the svelte-language-server
        # only handles .svelte files for document symbols
        if self._is_typescript_file(relative_file_path) and self._ts_server is not None:
            with self._ts_server.open_file(relative_file_path):
                return self._ts_server._request_document_symbols(relative_file_path, None)
        return super()._request_document_symbols(relative_file_path, file_data)
