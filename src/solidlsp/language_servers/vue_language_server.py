"""
Vue Language Server implementation using @vue/language-server (Volar) with companion TypeScript LS.
Operates in hybrid mode: Vue LS handles .vue files, TypeScript LS handles .ts/.js files.
"""

import logging
import os
import pathlib
import shutil
import threading
from pathlib import Path
from time import sleep
from typing import Any

from overrides import override

from solidlsp import ls_types
from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection
from solidlsp.language_servers.typescript_language_server import (
    TypeScriptLanguageServer,
    prefer_non_node_modules_definition,
)
from solidlsp.ls import LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
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

    _pending_ts_ls_executable: list[str] | None = None

    @classmethod
    @override
    def get_language_enum_instance(cls) -> Language:
        """Return TYPESCRIPT since this is a TypeScript language server variant.

        Note: VueTypeScriptServer is a companion server that uses TypeScript's language server
        with the Vue TypeScript plugin. It reports as TYPESCRIPT to maintain compatibility
        with the TypeScript language server infrastructure.
        """
        return Language.TYPESCRIPT

    @classmethod
    @override
    def _setup_runtime_dependencies(cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings) -> list[str]:
        if cls._pending_ts_ls_executable is not None:
            return cls._pending_ts_ls_executable
        return ["typescript-language-server", "--stdio"]

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
        ts_ls_executable_path: list[str],
    ):
        self._vue_plugin_path = vue_plugin_path
        self._custom_tsdk_path = tsdk_path
        VueTypeScriptServer._pending_ts_ls_executable = ts_ls_executable_path
        super().__init__(config, repository_root_path, solidlsp_settings)
        VueTypeScriptServer._pending_ts_ls_executable = None

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
    # Windows requires more time due to slower I/O and process operations.
    VUE_INDEXING_WAIT_TIME = 4.0 if os.name == "nt" else 2.0

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

        for vue_file in vue_files:
            try:
                with self._ts_server.open_file(vue_file) as file_buffer:
                    file_buffer.ref_count += 1
                    self._indexed_vue_file_uris.append(file_buffer.uri)
            except Exception as e:
                log.debug(f"Failed to open {vue_file} on TS server: {e}")

        self._vue_files_indexed = True
        log.info("Vue file indexing on TypeScript server complete")

        sleep(self._get_vue_indexing_wait_time())
        log.debug("Wait period after Vue file indexing complete")

    def _get_vue_indexing_wait_time(self) -> float:
        return self.VUE_INDEXING_WAIT_TIME

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
        if not self.server_started:
            log.error("request_file_references called before Language Server started")
            raise SolidLSPException("Language Server not started")

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
        if not self.server_started:
            log.error("request_references called before Language Server started")
            raise SolidLSPException("Language Server not started")

        if not self._has_waited_for_cross_file_references:
            sleep(self._get_wait_time_for_cross_file_referencing())
            self._has_waited_for_cross_file_references = True

        self._ensure_vue_files_indexed_on_ts_server()
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
        if not self.server_started:
            log.error("request_definition called before Language Server started")
            raise SolidLSPException("Language Server not started")

        assert self._ts_server is not None
        with self._ts_server.open_file(relative_file_path):
            return self._ts_server.request_definition(relative_file_path, line, column)

    @override
    def request_rename_symbol_edit(self, relative_file_path: str, line: int, column: int, new_name: str) -> ls_types.WorkspaceEdit | None:
        if not self.server_started:
            log.error("request_rename_symbol_edit called before Language Server started")
            raise SolidLSPException("Language Server not started")

        assert self._ts_server is not None
        with self._ts_server.open_file(relative_file_path):
            return self._ts_server.request_rename_symbol_edit(relative_file_path, line, column, new_name)

    @classmethod
    def _setup_runtime_dependencies(
        cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings
    ) -> tuple[list[str], str, list[str]]:
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

        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="vue-language-server",
                    description="Vue language server package (Volar)",
                    command=["npm", "install", "--prefix", "./", f"@vue/language-server@{vue_language_server_version}"],
                    platform_id="any",
                ),
                RuntimeDependency(
                    id="typescript",
                    description="TypeScript (required for tsdk)",
                    command=["npm", "install", "--prefix", "./", f"typescript@{typescript_version}"],
                    platform_id="any",
                ),
                RuntimeDependency(
                    id="typescript-language-server",
                    description="TypeScript language server (for Vue LS 3.x tsserver forwarding)",
                    command=[
                        "npm",
                        "install",
                        "--prefix",
                        "./",
                        f"typescript-language-server@{typescript_language_server_version}",
                    ],
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

        return [vue_executable_path, "--stdio"], tsdk_path, [ts_ls_executable_path, "--stdio"]

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
                    "inlayHint": {"dynamicRegistration": True},
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
                self.completions_available.set()

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
            self.completions_available.set()
        else:
            log.info("Vue server initialization complete")

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
        self._cleanup_indexed_vue_files()
        self._stop_typescript_server()
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

    def _filter_shorthand_property_duplicates(
        self, symbols: list[DocumentSymbol] | list[SymbolInformation]
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
