"""
Angular Language Server integration for Serena.

Architecture (tri-server, modeled on the Vue LS dual-server pattern but with
an additional HTML companion because ngserver does not implement
``textDocument/documentSymbol`` for any file type):

    ngserver (parent process, this class)
        - handles .html templates: definition, references, hover, completion,
          rename on template expressions (@if/@for/{{ }}/[prop]/(event))
        - handles .ts references (ngserver aggregates template + TS usages in
          one pass; typescript-language-server alone misses template usages
          and often returns partial cross-file .ts references on Angular
          projects where files aren't pre-opened)
        - exposes Angular-specific custom requests
          (IsInAngularProject, GetComponentsWithTemplateFile, ...)
        - DOES NOT implement ``textDocument/documentSymbol`` at all — returns
          -32601 for every .html and we do not route documentSymbol to it.

    AngularTypeScriptServer (companion process, subclass of TypeScriptLanguageServer)
        - handles .ts/.tsx/.cts/.mts documentSymbol, definition, hover, rename
        - the @angular/language-service plugin is loaded into the companion
          typescript-language-server via initializationOptions.plugins, which
          makes tsserver Angular-aware for completions/hover on inline
          templates. (Note: template *references* on .ts symbols are
          empirically incomplete here; see ngserver routing above.)

    VsCodeHtmlLanguageServer (companion process)
        - handles .html ``textDocument/documentSymbol`` only: returns the
          structural element tree (``<section>``, ``<app-*>``, ``<mat-*>``…)
          which ngserver refuses to provide. Angular template directives like
          ``@if``/``@for`` are passed through as text content, which is fine —
          this companion is only for structural outline.

Routing:
    request_document_symbols(.ts)   -> companion TS server
    request_document_symbols(.html) -> companion HTML server
    request_definition(.ts)         -> companion TS server
    request_definition(.html)       -> ngserver
    request_references(.ts)         -> ngserver
    request_references(.html)       -> ngserver
    request_hover(.ts)              -> companion TS server
    request_hover(.html)            -> ngserver
    request_rename_symbol_edit      -> companion TS server (.ts), ngserver (.html)

Hard project requirements (failure modes if violated):
    * tsconfig.json at the repository root (or above any opened .ts file).
    * @angular/core resolvable from that tsconfig, i.e. ``npm install`` has been
      run in the project. Without it, ngserver's `isInAngularProject` returns
      false for every file and template features silently return empty.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import shutil
import threading

from overrides import override

from solidlsp import ls_types
from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command
from solidlsp.language_servers.typescript_language_server import (
    TypeScriptLanguageServer,
    prefer_non_node_modules_definition,
)
from solidlsp.language_servers.vscode_html_language_server import VsCodeHtmlLanguageServer
from solidlsp.ls import LanguageServerDependencyProvider, LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import FilenameMatcher, Language, LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import DocumentSymbol, InitializeParams, SymbolInformation
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# Angular installs four interdependent npm packages into a single ``node_modules`` (npm
# hoists them so ngserver's plugin resolution works); the install-dir name encodes all
# four versions so a bump of any single one routes to a fresh subdir.
DEFAULT_ANGULAR_LANGUAGE_SERVER_VERSION = "21.2.10"
DEFAULT_ANGULAR_LANGUAGE_SERVICE_VERSION = "21.2.10"
DEFAULT_TYPESCRIPT_VERSION = "5.9.3"
DEFAULT_TYPESCRIPT_LANGUAGE_SERVER_VERSION = "5.1.3"
NGSERVER_BIN = "ngserver"
TSLS_BIN = "typescript-language-server"


class AngularTypeScriptServer(TypeScriptLanguageServer):
    """
    Companion TypeScript Language Server configured with @angular/language-service
    loaded as a tsserver plugin. The plugin makes tsserver understand Angular
    decorators, inline templates, templateUrl/styleUrls navigation, and
    cross-file references that span Angular templates.
    """

    @classmethod
    @override
    def get_language_enum_instance(cls) -> Language:
        return Language.TYPESCRIPT

    def get_source_fn_matcher(self) -> FilenameMatcher:
        # Use the Angular matcher so .html template files aren't filtered out of
        # reference / search results when the companion is asked about them.
        return Language.ANGULAR.get_source_fn_matcher()

    class DependencyProvider(TypeScriptLanguageServer.DependencyProvider):
        """Dependency provider that returns a pre-resolved executable path.

        The Angular LS install (run by ``AngularLanguageServer._setup_runtime_dependencies``)
        already locates the ``typescript-language-server`` binary alongside ngserver,
        so the companion does not need to perform another install lookup — it just
        returns the path it was constructed with.
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
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext in (".ts", ".tsx", ".mts", ".cts"):
            return "typescript"
        if ext in (".js", ".jsx", ".mjs", ".cjs"):
            return "javascript"
        if ext in (".html", ".htm"):
            return "html"
        return "typescript"

    def __init__(
        self,
        config: LanguageServerConfig,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
        angular_plugin_path: str,
        tsdk_path: str,
        ts_ls_executable_path: str,
    ):
        self._angular_plugin_path = angular_plugin_path
        self._custom_tsdk_path = tsdk_path
        # Stored as instance state so the override survives across concurrent
        # constructions of multiple AngularLanguageServer instances. The class
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
        # Load @angular/language-service as a tsserver plugin via typescript-language-server's
        # initializationOptions.plugins API (the same API Vue uses for @vue/typescript-plugin).
        params["initializationOptions"] = {
            "plugins": [
                {
                    "name": "@angular/language-service",
                    "location": self._angular_plugin_path,
                    "languages": ["html"],
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


class AngularLanguageServer(SolidLanguageServer):
    """
    Angular Language Server — dual-process orchestration of ngserver + a companion
    typescript-language-server with the @angular/language-service plugin loaded.

    ``ls_specific_settings["angular"]`` keys:
        * ``angular_language_server_version``: version of ``@angular/language-server``
          (default: ``21.2.10``).
        * ``angular_language_service_version``: version of ``@angular/language-service``
          (default: matches the language-server version).
        * ``typescript_version``: TypeScript version installed for the companion
          (default: ``5.9.3``).
        * ``typescript_language_server_version``: typescript-language-server version
          (default: ``5.1.3``).
        * ``npm_registry``: optional alternative npm registry URL.
    """

    NG_SERVER_READY_TIMEOUT = 10.0
    TS_SERVER_READY_TIMEOUT = 10.0
    HTML_SERVER_READY_TIMEOUT = 10.0

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        ng_executable, self._tsdk_path, self._ts_ls_executable, self._angular_plugin_path, self._install_dir = (
            self._setup_runtime_dependencies(config, solidlsp_settings)
        )
        ng_cmd = [
            ng_executable,
            "--stdio",
            "--tsProbeLocations",
            os.path.join(self._install_dir, "node_modules"),
            "--ngProbeLocations",
            os.path.join(self._install_dir, "node_modules"),
        ]
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=ng_cmd, cwd=repository_root_path),
            "angular",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self._ts_server: AngularTypeScriptServer | None = None
        self._ts_server_started = False
        self._html_server: VsCodeHtmlLanguageServer | None = None
        self._html_server_started = False

    @classmethod
    @override
    def supports_implementation_request(cls) -> bool:
        # Angular templates and components are TypeScript code under the hood — ngserver
        # delegates to tsserver, which supports textDocument/implementation for class
        # members and interfaces (e.g. resolving an Angular lifecycle hook on a component
        # back to its OnInit/OnDestroy interface declaration).
        return True

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",
            "dist",
            "build",
            "coverage",
            ".angular",
            ".nx",
        ]

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext in (".ts", ".tsx", ".mts", ".cts"):
            return "typescript"
        if ext in (".js", ".jsx", ".mjs", ".cjs"):
            return "javascript"
        if ext in (".html", ".htm"):
            return "html"
        return "typescript"

    @staticmethod
    def _is_typescript_file(file_path: str) -> bool:
        return os.path.splitext(file_path)[1].lower() in (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")

    @staticmethod
    def _is_html_template_file(file_path: str) -> bool:
        return os.path.splitext(file_path)[1].lower() in (".html", ".htm")

    @classmethod
    def _setup_runtime_dependencies(
        cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings
    ) -> tuple[str, str, str, str, str]:
        """
        Install the Angular LS stack into the managed ls_resources_dir.

        :return: tuple of (ngserver_path, tsdk_path, ts_ls_executable_path, angular_plugin_path, install_dir)
        """
        assert shutil.which("node") is not None, "node is not installed or isn't in PATH. Please install NodeJS and try again."
        assert shutil.which("npm") is not None, "npm is not installed or isn't in PATH. Please install npm and try again."

        ng_settings = solidlsp_settings.get_ls_specific_settings(Language.ANGULAR)
        ts_settings = solidlsp_settings.get_ls_specific_settings(Language.TYPESCRIPT)
        ls_version = ng_settings.get("angular_language_server_version", DEFAULT_ANGULAR_LANGUAGE_SERVER_VERSION)
        svc_version = ng_settings.get("angular_language_service_version", DEFAULT_ANGULAR_LANGUAGE_SERVICE_VERSION)
        ts_version = ng_settings.get("typescript_version", ts_settings.get("typescript_version", DEFAULT_TYPESCRIPT_VERSION))
        tsls_version = ng_settings.get(
            "typescript_language_server_version",
            ts_settings.get("typescript_language_server_version", DEFAULT_TYPESCRIPT_LANGUAGE_SERVER_VERSION),
        )
        npm_registry = ng_settings.get("npm_registry", ts_settings.get("npm_registry"))

        # Fully-versioned subdir so a bump of any single package cannot silently reuse
        # stale companions in a shared node_modules.
        ls_dirname = f"angular-lsp-{ls_version}-{svc_version}-{ts_version}-{tsls_version}"
        install_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), ls_dirname)
        ng_executable = os.path.join(install_dir, "node_modules", ".bin", NGSERVER_BIN)
        ts_ls_executable = os.path.join(install_dir, "node_modules", ".bin", TSLS_BIN)
        if os.name == "nt":
            ng_executable += ".cmd"
            ts_ls_executable += ".cmd"

        tsdk_path = os.path.join(install_dir, "node_modules", "typescript", "lib")
        angular_plugin_path = os.path.join(install_dir, "node_modules", "@angular", "language-service")

        if not (os.path.exists(ng_executable) and os.path.exists(ts_ls_executable)):
            log.info(
                "Installing Angular LS stack: ngserver=%s, language-service=%s, typescript=%s, typescript-language-server=%s",
                ls_version,
                svc_version,
                ts_version,
                tsls_version,
            )
            deps = RuntimeDependencyCollection(
                [
                    RuntimeDependency(
                        id="typescript",
                        description="typescript (tsserver runtime, used by ngserver and the companion TS LS)",
                        command=build_npm_install_command("typescript", ts_version, npm_registry),
                        platform_id="any",
                    ),
                    RuntimeDependency(
                        id="@angular/language-service",
                        description="Angular language service tsserver plugin",
                        command=build_npm_install_command("@angular/language-service", svc_version, npm_registry),
                        platform_id="any",
                    ),
                    RuntimeDependency(
                        id="@angular/language-server",
                        description="Angular language server (ngserver binary)",
                        command=build_npm_install_command("@angular/language-server", ls_version, npm_registry),
                        platform_id="any",
                    ),
                    RuntimeDependency(
                        id="typescript-language-server",
                        description="typescript-language-server (companion LS for .ts operations)",
                        command=build_npm_install_command("typescript-language-server", tsls_version, npm_registry),
                        platform_id="any",
                    ),
                ]
            )
            deps.install(install_dir)

        for path, label in (
            (ng_executable, NGSERVER_BIN),
            (ts_ls_executable, TSLS_BIN),
            (angular_plugin_path, "@angular/language-service"),
            (os.path.join(tsdk_path, "tsserverlibrary.js"), "typescript/lib/tsserverlibrary.js"),
        ):
            if not os.path.exists(path):
                raise FileNotFoundError(f"Expected {label} at {path} after install, but it was not found.")

        return ng_executable, tsdk_path, ts_ls_executable, angular_plugin_path, install_dir

    def _start_typescript_server(self) -> None:
        try:
            ts_config = LanguageServerConfig(code_language=Language.TYPESCRIPT, trace_lsp_communication=False)
            log.info("Creating companion AngularTypeScriptServer")
            self._ts_server = AngularTypeScriptServer(
                config=ts_config,
                repository_root_path=self.repository_root_path,
                solidlsp_settings=self._solidlsp_settings,
                angular_plugin_path=self._angular_plugin_path,
                tsdk_path=self._tsdk_path,
                ts_ls_executable_path=self._ts_ls_executable,
            )
            log.info("Starting companion TypeScript server")
            self._ts_server.start()
            log.info("Waiting for companion TypeScript server to be ready...")
            if not self._ts_server.server_ready.wait(timeout=self.TS_SERVER_READY_TIMEOUT):
                log.warning("Companion TS server ready timeout (%s s); proceeding anyway", self.TS_SERVER_READY_TIMEOUT)
                self._ts_server.server_ready.set()
            self._ts_server_started = True
            log.info("Companion TypeScript server ready")
        except Exception:
            log.exception("Error starting companion TypeScript server")
            self._ts_server = None
            self._ts_server_started = False
            raise

    def _stop_typescript_server(self) -> None:
        if self._ts_server is not None:
            try:
                log.info("Stopping companion TypeScript server")
                self._ts_server.stop()
            except Exception as e:
                log.warning(f"Error stopping companion TypeScript server: {e}")
            finally:
                self._ts_server = None
                self._ts_server_started = False

    def _start_html_server(self) -> None:
        """Spawn vscode-html-language-server as a tertiary companion.

        ngserver does not implement ``textDocument/documentSymbol`` (returns
        -32601 for every .html file — both plain HTML and Angular templates).
        The HTML companion provides the structural element outline the user
        expects from documentSymbol on .html files. Failure to start it is
        non-fatal: we log and fall back to returning an empty list.
        """
        try:
            html_config = LanguageServerConfig(code_language=Language.HTML, trace_lsp_communication=False)
            log.info("Creating companion VsCodeHtmlLanguageServer")
            self._html_server = VsCodeHtmlLanguageServer(
                config=html_config,
                repository_root_path=self.repository_root_path,
                solidlsp_settings=self._solidlsp_settings,
            )
            log.info("Starting companion HTML server")
            self._html_server.start()
            if not self._html_server.server_ready.wait(timeout=self.HTML_SERVER_READY_TIMEOUT):
                log.warning("Companion HTML server ready timeout (%s s); proceeding anyway", self.HTML_SERVER_READY_TIMEOUT)
                self._html_server.server_ready.set()
            self._html_server_started = True
            log.info("Companion HTML server ready")
        except Exception:
            log.exception("Error starting companion HTML server; .html documentSymbol will return []")
            self._html_server = None
            self._html_server_started = False

    def _stop_html_server(self) -> None:
        if self._html_server is not None:
            try:
                log.info("Stopping companion HTML server")
                self._html_server.stop()
            except Exception as e:
                log.warning(f"Error stopping companion HTML server: {e}")
            finally:
                self._html_server = None
                self._html_server_started = False

    def _find_angular_core_install(self) -> str | None:
        """Walk up from ``repository_root_path`` looking for ``node_modules/@angular/core``.

        Handles monorepo layouts (Nx, yarn/pnpm workspaces) where ``node_modules`` is
        hoisted to a workspace root above the activated sub-package. Stops walking at:
        the filesystem root, a mount-point change, or a ``package.json`` that declares
        ``"workspaces"`` (the workspace root — no need to look further).

        :return: absolute path to the discovered ``@angular/core/package.json``, or None.
        """
        cur = pathlib.Path(self.repository_root_path).resolve()
        try:
            start_dev = cur.stat().st_dev
        except OSError:
            start_dev = None
        steps = 0
        for parent in [cur, *cur.parents]:
            # Stop *before* probing across a mount-point change: a different
            # st_dev typically means we've crossed a container/volume boundary
            # and node_modules over there is unrelated.
            if start_dev is not None:
                try:
                    if parent.stat().st_dev != start_dev:
                        log.debug("Stopping @angular/core probe at %s after %d step(s) (mount-point change)", parent, steps)
                        break
                except OSError:
                    break
            steps += 1
            candidate = parent / "node_modules" / "@angular" / "core" / "package.json"
            if candidate.exists():
                log.debug("Found @angular/core after %d step(s) at %s", steps, candidate)
                return str(candidate)
            workspace_pkg = parent / "package.json"
            if workspace_pkg.exists():
                try:
                    with open(workspace_pkg, encoding="utf-8") as f:
                        if "workspaces" in json.load(f):
                            log.debug("Stopping @angular/core probe at workspace root %s after %d step(s)", parent, steps)
                            break
                except (OSError, ValueError) as e:
                    log.debug("Could not parse %s as JSON dict (%s); ignoring as workspace marker", workspace_pkg, e)
        else:
            log.debug("@angular/core probe walked %d ancestor(s) without finding an install or a workspace root", steps)
        return None

    def _check_angular_core_in_project(self) -> None:
        """Warn loudly if the project does not appear to have @angular/core installed."""
        found = self._find_angular_core_install()
        if found is None:
            log.warning(
                "Angular language server activated but @angular/core was not found in any "
                "node_modules from %s upward. ngserver will report files as 'not in an "
                "Angular project' and template-aware features will be disabled. Run "
                "`npm install` in the workspace root to enable Angular features.",
                self.repository_root_path,
            )
        else:
            log.debug("Found @angular/core at %s", found)

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        params: dict = {
            "locale": "en",
            "capabilities": {
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
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "initializationOptions": {
                "ngProbeLocations": [os.path.join(self._install_dir, "node_modules")],
                "tsProbeLocations": [os.path.join(self._install_dir, "node_modules")],
                "forceStrictTemplates": False,
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
        }
        return params  # type: ignore[return-value]

    @override
    def _start_server(self) -> None:
        self._check_angular_core_in_project()
        # Start the companion TS server first so .ts operations are immediately available.
        self._start_typescript_server()
        # Start the HTML companion so .html documentSymbol works on first call.
        self._start_html_server()

        def do_nothing(_params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def angular_project_loading_finish(_params: dict) -> None:
            log.info("Angular project loading finished")
            self.server_ready.set()

        # Standard LSP boilerplate
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_request("client/registerCapability", lambda _params: None)
        self.server.on_request("workspace/configuration", lambda _params: [{}])

        # Angular-specific notifications (custom protocol from ngserver)
        self.server.on_notification("angular/projectLoadingStart", do_nothing)
        self.server.on_notification("angular/projectLoadingFinish", angular_project_loading_finish)
        self.server.on_notification("angular/projectLanguageService", do_nothing)

        # Companions are already running. If anything below fails, our caller never
        # received an initialised handle and therefore can't invoke stop() — so we
        # tear down both companions and any partially-started ngserver process here
        # to avoid leaking Node processes.
        try:
            log.info("Starting Angular language server (ngserver)")
            self.server.start()
            init_params = self._get_initialize_params(self.repository_root_path)
            init_response = self.server.send.initialize(init_params)
            log.debug("Angular LS initialize response: %s", init_response)
            self.server.notify.initialized({})
            # ngserver loads the Angular compiler asynchronously after `initialized`. Wait briefly
            # for projectLoadingFinish, then proceed regardless — operations queue inside ngserver.
            # ngserver eagerly resolves the project once projectLoadingFinish fires; we previously
            # ran a proactive .ts didOpen/didClose pass but empirical testing on real Angular
            # projects (181 .ts / 85 .html) showed it added ~4s to cold start without improving
            # first-query correctness or latency, so it has been removed.
            if not self.server_ready.wait(timeout=self.NG_SERVER_READY_TIMEOUT):
                log.info("Timeout waiting for ngserver project load; proceeding anyway")
                self.server_ready.set()
        except Exception:
            self._stop_typescript_server()
            self._stop_html_server()
            try:
                self.server.stop()
            except Exception as e:
                log.warning("Error stopping ngserver during startup-failure cleanup: %s", e)
            raise

    @override
    def stop(self, shutdown_timeout: float = 5.0) -> None:
        self._stop_typescript_server()
        self._stop_html_server()
        super().stop(shutdown_timeout)

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 5.0

    @override
    def _get_preferred_definition(self, definitions: list[ls_types.Location]) -> ls_types.Location:
        return prefer_non_node_modules_definition(definitions)

    # ---------------------------------------------------------------------
    # Request routing — see module docstring for rationale per (op, ext) pair.
    # ---------------------------------------------------------------------

    @override
    def _request_document_symbols(
        self, relative_file_path: str, file_data: LSPFileBuffer | None
    ) -> list[SymbolInformation] | list[DocumentSymbol] | None:
        if self._ts_server is not None and self._is_typescript_file(relative_file_path):
            with self._ts_server.open_file(relative_file_path):
                return self._ts_server._request_document_symbols(relative_file_path, file_data=None)
        # ngserver returns -32601 for textDocument/documentSymbol on every .html file.
        # Route to the HTML companion which gives the structural element tree
        # (works on both plain HTML like index.html and Angular templates).
        if self._is_html_template_file(relative_file_path):
            if self._html_server is not None and self._html_server_started:
                with self._html_server.open_file(relative_file_path):
                    return self._html_server._request_document_symbols(relative_file_path, file_data=None)
            log.debug("HTML companion unavailable for %s; returning None", relative_file_path)
            return None
        return super()._request_document_symbols(relative_file_path, file_data)

    @override
    def request_definition(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        if self._ts_server is not None and self._is_typescript_file(relative_file_path):
            with self._ts_server.open_file(relative_file_path):
                return self._ts_server.request_definition(relative_file_path, line, column)
        # HTML templates: ngserver knows how to resolve template -> component
        return super().request_definition(relative_file_path, line, column)

    # request_references is intentionally not overridden: ngserver (the parent
    # process) handles both .ts and .html references and returns the full set,
    # whereas the TS companion under-reports because it only sees pre-opened
    # files. See module docstring routing table.

    @override
    def request_rename_symbol_edit(self, relative_file_path: str, line: int, column: int, new_name: str) -> ls_types.WorkspaceEdit | None:
        if self._ts_server is not None and self._is_typescript_file(relative_file_path):
            with self._ts_server.open_file(relative_file_path):
                return self._ts_server.request_rename_symbol_edit(relative_file_path, line, column, new_name)
        return super().request_rename_symbol_edit(relative_file_path, line, column, new_name)

    @override
    def request_hover(
        self, relative_file_path: str, line: int, column: int, file_buffer: LSPFileBuffer | None = None
    ) -> ls_types.Hover | None:
        if self._ts_server is not None and self._is_typescript_file(relative_file_path):
            with self._ts_server.open_file(relative_file_path):
                return self._ts_server.request_hover(relative_file_path, line, column, file_buffer=file_buffer)
        return super().request_hover(relative_file_path, line, column, file_buffer=file_buffer)

    @override
    def request_implementation(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        # ngserver does not advertise textDocument/implementation (returns -32601);
        # the companion typescript-language-server (with the @angular/language-service
        # plugin loaded) does, since the underlying tsserver implements it for
        # interface→implementation, abstract→concrete, etc. Keep this routed even
        # for .html paths because the LSP method is meaningless on plain HTML.
        if self._ts_server is not None and self._is_typescript_file(relative_file_path):
            with self._ts_server.open_file(relative_file_path):
                return self._ts_server.request_implementation(relative_file_path, line, column)
        log.debug(
            "request_implementation called on non-TS path %s; ngserver does not advertise the LSP method "
            "and the request is meaningless on plain HTML — returning []",
            relative_file_path,
        )
        return []

    @override
    def request_text_document_diagnostics(
        self,
        relative_file_path: str,
        start_line: int = 0,
        end_line: int = -1,
        min_severity: int = 4,
    ) -> list[ls_types.Diagnostic]:
        # ngserver does not handle pull diagnostics for .ts files in the way tsserver
        # does — it produces template diagnostics on .html attached via templateUrl,
        # but for component classes we want the TS error stream, which lives in the
        # companion typescript-language-server.
        if self._ts_server is not None and self._is_typescript_file(relative_file_path):
            with self._ts_server.open_file(relative_file_path):
                return self._ts_server.request_text_document_diagnostics(
                    relative_file_path, start_line=start_line, end_line=end_line, min_severity=min_severity
                )
        return super().request_text_document_diagnostics(
            relative_file_path, start_line=start_line, end_line=end_line, min_severity=min_severity
        )
