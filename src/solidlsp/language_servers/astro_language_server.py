"""
Astro Language Server implementation using @astrojs/language-server with companion TypeScript LS.
Operates in a dual-server setup: the Astro LS handles .astro files (parsing, document symbols),
while a companion TypeScript LS (configured with @astrojs/ts-plugin) handles definitions,
references and rename for .ts/.js files and cross-file resolution.

This mirrors the Vue and Svelte language servers, which use a self-contained companion server
held in ``self._ts_server`` rather than a shared companion base class.
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

from solidlsp import ls_types
from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command
from solidlsp.language_servers.typescript_language_server import (
    TypeScriptLanguageServer,
    prefer_non_node_modules_definition,
)
from solidlsp.ls import LanguageServerDependencyProvider, SolidLanguageServer
from solidlsp.ls_config import FilenameMatcher, Language, LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_utils import PathUtils
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class AstroTypeScriptServer(TypeScriptLanguageServer):
    """TypeScript LS configured with @astrojs/ts-plugin for Astro file support."""

    @classmethod
    @override
    def get_language_enum_instance(cls) -> Language:
        """Return TYPESCRIPT since this is a TypeScript language server variant.

        AstroTypeScriptServer is a companion server that uses TypeScript's language server
        with the Astro TypeScript plugin. It reports as TYPESCRIPT to maintain compatibility
        with the TypeScript language server infrastructure.
        """
        return Language.TYPESCRIPT

    def get_source_fn_matcher(self) -> FilenameMatcher:
        # Override with an Astro-specific matcher to ensure .astro files are included (they can be
        # discovered via references); otherwise references in .astro files would be filtered out.
        return Language.ASTRO.get_source_fn_matcher()

    class DependencyProvider(TypeScriptLanguageServer.DependencyProvider):
        """Dependency provider that returns a pre-resolved executable path.

        The Astro LS install (run by ``AstroLanguageServer._setup_runtime_dependencies``)
        already locates the ``typescript-language-server`` binary alongside the Astro
        language server, so the companion does not need to perform another install
        lookup -- it just returns the path it was constructed with.
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

        Astro files must be opened with language ID "astro" for the @astrojs/ts-plugin
        to process them correctly. The plugin is configured with "languages": ["astro"]
        in the initialization options. JSX/TSX use the react variants so tsserver does
        not truncate symbol ranges at the first multi-line JSX expression (see the base
        ``TypeScriptLanguageServer._get_language_id_for_file``); Astro projects commonly
        include .tsx/.jsx via React/Preact/Solid integrations.
        """
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext == ".astro":
            return "astro"
        elif ext == ".tsx":
            return "typescriptreact"
        elif ext == ".jsx":
            return "javascriptreact"
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
        astro_plugin_path: str,
        tsdk_path: str,
        ts_ls_executable_path: str,
    ):
        self._astro_plugin_path = astro_plugin_path
        self._custom_tsdk_path = tsdk_path
        # Stored as instance state so the override survives across concurrent
        # constructions of multiple AstroLanguageServer instances.
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


class AstroLanguageServer(SolidLanguageServer):
    """
    Language server for Astro components using @astrojs/language-server with companion TypeScript LS.

    You can pass the following entries in ls_specific_settings["astro"]:
        - astro_language_server_version: Version of @astrojs/language-server to install (default: "2.16.11")

    Note: TypeScript versions are configured via ls_specific_settings["typescript"]:
        - typescript_version: Version of TypeScript to install (default: "5.9.3")
        - typescript_language_server_version: Version of typescript-language-server to install (default: "5.1.3")
    """

    TS_SERVER_READY_TIMEOUT = 5.0
    ASTRO_SERVER_READY_TIMEOUT = 3.0

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        astro_lsp_executable_path, self.tsdk_path, self._ts_ls_cmd = self._setup_runtime_dependencies(config, solidlsp_settings)
        self._astro_ls_dir = os.path.join(self.ls_resources_dir(solidlsp_settings), "astro-lsp")
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=astro_lsp_executable_path, cwd=repository_root_path),
            "astro",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()
        self._ts_server: AstroTypeScriptServer | None = None
        self._ts_server_started = False
        self._astro_files_indexed = False
        self._indexed_astro_file_uris: list[str] = []
        self._ls_operational_ready_event = threading.Event()
        self._ls_operational_lock = threading.Lock()

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

            # index Astro files on the companion TypeScript server
            self._ensure_astro_files_indexed_on_ts_server()

            # publish operational readiness
            self._ls_operational_ready_event.set()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",
            "dist",
            "build",
            "coverage",
            ".astro",
        ]

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        # Inherited document-symbol requests open files on this primary server, so JSX/TSX must use
        # the react variants here too (see the companion's _get_language_id_for_file for rationale).
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext == ".astro":
            return "astro"
        elif ext == ".tsx":
            return "typescriptreact"
        elif ext == ".jsx":
            return "javascriptreact"
        elif ext in (".ts", ".mts", ".cts"):
            return "typescript"
        elif ext in (".js", ".mjs", ".cjs"):
            return "javascript"
        else:
            return "astro"

    def _is_typescript_file(self, file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        return ext in (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")

    def _find_all_astro_files(self) -> list[str]:
        astro_files = []
        repo_path = Path(self.repository_root_path)

        for astro_file in repo_path.rglob("*.astro"):
            try:
                relative_path = str(astro_file.relative_to(repo_path))
                if "node_modules" not in relative_path and not relative_path.startswith("."):
                    astro_files.append(relative_path)
            except Exception as e:
                log.debug(f"Error processing Astro file {astro_file}: {e}")

        return astro_files

    def _ensure_astro_files_indexed_on_ts_server(self) -> None:
        if self._astro_files_indexed:
            return

        assert self._ts_server is not None
        log.info("Indexing .astro files on TypeScript server for cross-file references")
        astro_files = self._find_all_astro_files()
        log.debug(f"Found {len(astro_files)} .astro files to index")

        # Prepare the TS server to track new $/progress notifications triggered
        # by the didOpen calls below. Must happen BEFORE opening files to avoid
        # a race where progress begins and ends before we start waiting.
        self._ts_server.expect_indexing()

        for astro_file in astro_files:
            try:
                with self._ts_server.open_file(astro_file) as file_buffer:
                    file_buffer.ref_count += 1
                    self._indexed_astro_file_uris.append(file_buffer.uri)
            except Exception as e:
                log.debug(f"Failed to open {astro_file} on TS server: {e}")

        self._astro_files_indexed = True
        log.info("Astro file indexing on TypeScript server complete, waiting for TS server to finish processing")

        self._wait_for_ts_indexing_complete()

    def _wait_for_ts_indexing_complete(self) -> None:
        """Wait for the companion TypeScript server to finish processing opened Astro files.

        Uses the $/progress tracking in TypeScriptLanguageServer: after Astro files are
        opened, tsserver sends "Initializing JS/TS language features..." progress.
        We wait for all progress tokens to complete, with a timeout fallback.
        """
        assert self._ts_server is not None
        timeout = TypeScriptLanguageServer.INDEXING_PROGRESS_TIMEOUT
        if self._ts_server.wait_for_indexing(timeout=timeout):
            log.info("TypeScript server finished indexing Astro files (signaled via $/progress)")
        else:
            log.warning(f"Timeout ({timeout}s) waiting for TypeScript server to finish indexing Astro files, proceeding anyway")

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
                new_item.update(item)
                new_item["absolutePath"] = str(abs_path)
                new_item["relativePath"] = str(rel_path)
                result.append(ls_types.Location(**new_item))  # type: ignore

        return result

    @override
    def request_references(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        self._ensure_ls_operational()
        return self._send_ts_references_request(relative_file_path, line=line, column=column)

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

        Only applicable to non-TypeScript files (i.e. .astro files) that have been
        indexed on the TypeScript server for cross-file reference support.
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
        astro_config = solidlsp_settings.get_ls_specific_settings(Language.ASTRO)
        astro_language_server_version = astro_config.get("astro_language_server_version", "2.16.11")
        # @astrojs/ts-plugin is NOT a dependency of @astrojs/language-server, so it must be installed
        # explicitly. Without it the companion tsserver has no .astro awareness and cross-file
        # resolution between .ts/.js and .astro files silently returns nothing.
        astro_ts_plugin_version = astro_config.get("astro_ts_plugin_version", "1.10.10")
        npm_registry = astro_config.get("npm_registry", typescript_config.get("npm_registry"))

        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="astro-language-server",
                    description="Astro language server package",
                    command=build_npm_install_command("@astrojs/language-server", astro_language_server_version, npm_registry),
                    platform_id="any",
                ),
                RuntimeDependency(
                    id="astro-ts-plugin",
                    description="Astro TypeScript plugin, gives the companion tsserver .astro awareness",
                    command=build_npm_install_command("@astrojs/ts-plugin", astro_ts_plugin_version, npm_registry),
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
                    description="TypeScript language server (for Astro companion TS forwarding)",
                    command=build_npm_install_command("typescript-language-server", typescript_language_server_version, npm_registry),
                    platform_id="any",
                ),
            ]
        )

        astro_ls_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), "astro-lsp")
        astro_executable_path = os.path.join(astro_ls_dir, "node_modules", ".bin", "astro-ls")
        ts_ls_executable_path = os.path.join(astro_ls_dir, "node_modules", ".bin", "typescript-language-server")

        if os.name == "nt":
            astro_executable_path += ".cmd"
            ts_ls_executable_path += ".cmd"

        tsdk_path = os.path.join(astro_ls_dir, "node_modules", "typescript", "lib")

        # Check if installation is needed based on executables AND version
        version_file = os.path.join(astro_ls_dir, ".installed_version")
        expected_version = (
            f"{astro_language_server_version}_{astro_ts_plugin_version}_{typescript_version}_{typescript_language_server_version}"
        )

        needs_install = False
        if not os.path.exists(astro_executable_path) or not os.path.exists(ts_ls_executable_path):
            log.info("Astro/TypeScript Language Server executables not found.")
            needs_install = True
        elif os.path.exists(version_file):
            with open(version_file) as f:
                installed_version = f.read().strip()
            if installed_version != expected_version:
                log.info(
                    f"Astro Language Server version mismatch: installed={installed_version}, expected={expected_version}. Reinstalling..."
                )
                needs_install = True
        else:
            # No version file exists, assume old installation needs refresh
            log.info("Astro Language Server version file not found. Reinstalling to ensure correct version...")
            needs_install = True

        if needs_install:
            log.info("Installing Astro/TypeScript Language Server dependencies...")
            deps.install(astro_ls_dir)
            # Write version marker file
            with open(version_file, "w") as f:
                f.write(expected_version)
            log.info("Astro language server dependencies installed successfully")

        if not os.path.exists(astro_executable_path):
            raise FileNotFoundError(
                f"astro-ls executable not found at {astro_executable_path}, something went wrong with the installation."
            )

        if not os.path.exists(ts_ls_executable_path):
            raise FileNotFoundError(
                f"typescript-language-server executable not found at {ts_ls_executable_path}, something went wrong with the installation."
            )

        return [astro_executable_path, "--stdio"], tsdk_path, ts_ls_executable_path

    def _create_base_initialize_params(self) -> dict:
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
            "initializationOptions": {
                "typescript": {
                    "tsdk": self.tsdk_path,
                },
            },
        }
        return initialize_params

    def _start_typescript_server(self) -> None:
        try:
            astro_ts_plugin_path = os.path.join(self._astro_ls_dir, "node_modules", "@astrojs", "ts-plugin")
            if not os.path.exists(astro_ts_plugin_path):
                log.warning(
                    "Astro TypeScript plugin not found at %s. The companion tsserver will lack .astro "
                    "awareness, so cross-file resolution between .ts/.js and .astro files will not work. "
                    "This usually means the @astrojs/ts-plugin install did not complete.",
                    astro_ts_plugin_path,
                )

            ts_config = LanguageServerConfig(
                code_language=Language.TYPESCRIPT,
                trace_lsp_communication=False,
            )

            log.info("Creating companion AstroTypeScriptServer")
            self._ts_server = AstroTypeScriptServer(
                config=ts_config,
                repository_root_path=self.repository_root_path,
                solidlsp_settings=self._solidlsp_settings,
                astro_plugin_path=astro_ts_plugin_path,
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

    def _cleanup_indexed_astro_files(self) -> None:
        if not self._indexed_astro_file_uris or self._ts_server is None:
            return

        log.debug(f"Cleaning up {len(self._indexed_astro_file_uris)} indexed Astro files")
        for uri in self._indexed_astro_file_uris:
            try:
                if uri in self._ts_server.open_file_buffers:
                    file_buffer = self._ts_server.open_file_buffers[uri]
                    file_buffer.ref_count -= 1

                    if file_buffer.ref_count == 0:
                        self._ts_server.server.notify.did_close_text_document({"textDocument": {"uri": uri}})
                        del self._ts_server.open_file_buffers[uri]
                        log.debug(f"Closed indexed Astro file: {uri}")
            except Exception as e:
                log.debug(f"Error closing indexed Astro file {uri}: {e}")

        self._indexed_astro_file_uris.clear()

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
                log.info("Astro language server ready signal detected")
                self.server_ready.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("workspace/configuration", configuration_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        # The companion is already running. If anything below fails, our caller never received an
        # initialised handle and therefore can't invoke stop() -- so we tear down the companion and
        # the partially-started Astro process here to avoid leaking Node processes.
        try:
            log.info("Starting Astro server process")
            self.server.start()
            initialize_params = self._create_initialize_params()

            log.info("Sending initialize request from LSP client to LSP server and awaiting response")
            init_response = self.server.send.initialize(initialize_params)
            log.debug(f"Received initialize response from Astro server: {init_response}")

            assert init_response["capabilities"]["textDocumentSync"] in [1, 2]

            self.server.notify.initialized({})

            log.info("Waiting for Astro language server to be ready...")
            if not self.server_ready.wait(timeout=self.ASTRO_SERVER_READY_TIMEOUT):
                log.info("Timeout waiting for Astro server ready signal, proceeding anyway")
                self.server_ready.set()
            else:
                log.info("Astro server initialization complete")
        except Exception:
            self._stop_typescript_server()
            try:
                self.server.stop()
            except Exception as e:
                log.warning("Error stopping Astro server during startup-failure cleanup: %s", e)
            raise

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 5.0

    @override
    def stop(self, shutdown_timeout: float = 5.0) -> None:
        # serialize shutdown with operational warm-up
        with self._ls_operational_lock:
            self.server_started = False
            self._ls_operational_ready_event.clear()
            self._cleanup_indexed_astro_files()
            self._stop_typescript_server()

        super().stop(shutdown_timeout)

    @override
    def _get_preferred_definition(self, definitions: list[ls_types.Location]) -> ls_types.Location:
        return prefer_non_node_modules_definition(definitions)
