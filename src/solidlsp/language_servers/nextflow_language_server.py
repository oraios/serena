"""
Provides Nextflow specific instantiation of the LanguageServer class, using the official
Nextflow language server (https://github.com/nextflow-io/language-server), which is
distributed as a fat JAR and requires a Java runtime.

You can configure the following options in ls_specific_settings (in serena_config.yml):

    ls_specific_settings:
      nextflow:
        ls_path: '/path/to/language-server-all.jar'  # use an existing JAR instead of downloading one
        nextflow_ls_version: '26.04.3'               # JAR version to download (default: bundled version)
        java_home: '/path/to/jdk'                    # JDK to run the JAR with (default: JAVA_HOME or PATH)
        jvm_options: ['-Xmx2G']                      # JVM options for the language server process
        exclude_patterns: ['work', '.nextflow']      # workspace paths the language server shall ignore
"""

import logging
import os
import shutil
import threading
from collections.abc import Hashable
from pathlib import Path

from overrides import override

from solidlsp.dependency_provider import DownloadedDependency, DownloadedDependencyHashDatabase
from solidlsp.ls import (
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    RawDocumentSymbol,
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.lsp_protocol_handler import lsp_types
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

NEXTFLOW_LS_ALLOWED_HOSTS = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")

# NOTE: after bumping this, re-run scripts/update_downloaded_dependency_hashes.py and commit the
# updated src/solidlsp/resources/downloaded_dependency_hashes.json.
DEFAULT_NEXTFLOW_LS_VERSION = "26.04.3"

NEXTFLOW_LS_JAR_NAME = "language-server-all.jar"

#: the Nextflow language server is built for Java 17+
MIN_JDK_VERSION = 17

#: paths that hold Nextflow's own outputs rather than pipeline sources; scanning them is pure overhead
DEFAULT_EXCLUDE_PATTERNS = ["work", ".nextflow"]

#: the server scans the workspace only when a configuration change asks it to, and it compares the new
#: configuration against its own defaults (see LanguageServerConfiguration.defaults() upstream, where the
#: error reporting mode is "warnings"), so the settings we push must differ in at least one of the keys
#: that trigger a scan
_SCAN_TRIGGERING_ERROR_REPORTING_MODE = "errors"

#: upper bound for the initial workspace scan, which compiles every .nf file in the project
_WORKSPACE_SCAN_TIMEOUT = 180.0

#: declaration keywords the server prepends to symbol names (see ScriptSymbolProvider.getSymbolName upstream)
_SYMBOL_NAME_PREFIXES = frozenset(("process", "workflow", "function", "record", "enum"))


class NextflowLanguageServer(SolidLanguageServer):
    """
    Provides Nextflow specific instantiation of the LanguageServer class.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a Nextflow Language Server instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            "nextflow",
            solidlsp_settings,
        )

        # The workspace scan is asynchronous and reported via $/progress under the "initialize" token;
        # requests answered before it ends see an empty AST cache.
        self._scan_complete = threading.Event()
        self._active_progress_tokens: set[str] = set()
        self._progress_lock = threading.Lock()

        # Whether the server's deferred workspace scan has been observed to complete
        # (see _flush_deferred_workspace_scan).
        self._workspace_scan_flushed = False

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        @classmethod
        def _create_dep_language_server(cls, version: str | None = None) -> DownloadedDependency:
            version = version or DEFAULT_NEXTFLOW_LS_VERSION
            return DownloadedDependency(
                url=f"https://github.com/nextflow-io/language-server/releases/download/v{version}/{NEXTFLOW_LS_JAR_NAME}",
                allowed_hosts=NEXTFLOW_LS_ALLOWED_HOSTS,
            )

        @classmethod
        def update_dep_hashes(cls) -> None:
            deps = [cls._create_dep_language_server()]
            with DownloadedDependencyHashDatabase.get_instance().update_context() as db:
                for dep in deps:
                    db.update(dep)

        def _get_or_install_core_dependency(self) -> str:
            version = self._custom_settings.get("nextflow_ls_version", DEFAULT_NEXTFLOW_LS_VERSION)
            install_dir = os.path.join(self._ls_resources_dir, f"nextflow_language_server-{version}")
            jar_path = os.path.join(install_dir, NEXTFLOW_LS_JAR_NAME)

            if not os.path.exists(jar_path):
                os.makedirs(install_dir, exist_ok=True)
                log.info("Downloading Nextflow Language Server %s ...", version)
                self._create_dep_language_server(version).download_to(jar_path)

            if not os.path.exists(jar_path):
                raise FileNotFoundError(f"Nextflow Language Server JAR not found at {jar_path}")
            return jar_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            java_exe = self._resolve_java()
            jvm_options = self._custom_settings.get("jvm_options", [])
            if not isinstance(jvm_options, list):
                log.warning("The 'jvm_options' setting should be a list of strings. Ignoring the provided value: %s", jvm_options)
                jvm_options = []
            return [java_exe, *jvm_options, "-jar", core_path]

        def _resolve_java(self) -> str:
            """
            Locates a ``java`` executable (``java_home`` setting -> ``JAVA_HOME`` -> PATH) and verifies
            that it is new enough to run the language server.

            :return: the path to the java executable
            """
            java_exe_name = "java.exe" if os.name == "nt" else "java"

            java_exe: str | None = None
            if explicit_home := self._custom_settings.get("java_home"):
                candidate = str(Path(explicit_home) / "bin" / java_exe_name)
                if not os.path.exists(candidate):
                    raise SolidLSPException(
                        f"java_home='{explicit_home}' is invalid: '{candidate}' does not exist. "
                        f"Set ls_specific_settings.nextflow.java_home to a JDK home that contains bin/{java_exe_name}."
                    )
                java_exe = candidate
            elif env_home := os.environ.get("JAVA_HOME"):
                candidate = str(Path(env_home) / "bin" / java_exe_name)
                if os.path.exists(candidate):
                    java_exe = candidate
                else:
                    log.warning("JAVA_HOME='%s' invalid (no '%s'), falling back to PATH.", env_home, candidate)
            if java_exe is None:
                java_exe = shutil.which("java")
            if java_exe is None:
                raise SolidLSPException(
                    "Could not locate a Java installation for the Nextflow language server. "
                    "Set ls_specific_settings.nextflow.java_home, set the JAVA_HOME environment variable, "
                    f"or ensure 'java' is on PATH. Required: JDK {MIN_JDK_VERSION}+."
                )

            # reuse JDTLS's JVM interrogation, which reports the real java.home even for stub launchers
            from solidlsp.language_servers.eclipse_jdtls import EclipseJDTLS

            java_home, major_version = EclipseJDTLS.DependencyProvider._inspect_java(java_exe)
            if major_version < MIN_JDK_VERSION:
                raise SolidLSPException(
                    f"The Nextflow language server requires JDK {MIN_JDK_VERSION}+ but '{java_exe}' is JDK {major_version} "
                    f"(java.home={java_home}). Install a newer JDK and update ls_specific_settings.nextflow.java_home "
                    "or JAVA_HOME."
                )
            log.info("Using JDK %d at %s for the Nextflow language server", major_version, java_exe)
            return java_exe

    def _create_base_initialize_params(self) -> dict:
        """
        Returns the initialize params for the Nextflow Language Server.
        """
        return {
            "capabilities": {
                "textDocument": {
                    "synchronization": {"dynamicRegistration": True, "didSave": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": False}},
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                        "hierarchicalDocumentSymbolSupport": True,
                    },
                    "documentLink": {"dynamicRegistration": True},
                    "callHierarchy": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True, "symbolKind": {"valueSet": list(range(1, 27))}},
                },
                "window": {"workDoneProgress": True},
            },
        }

    def _create_configuration_settings(self) -> dict:
        """
        Returns the settings pushed via workspace/didChangeConfiguration, which is what makes the server
        scan the workspace (see ``_start_server``).
        """
        exclude_patterns = self._custom_settings.get("exclude_patterns", DEFAULT_EXCLUDE_PATTERNS)
        if not isinstance(exclude_patterns, list):
            log.warning("The 'exclude_patterns' setting should be a list of strings. Ignoring the provided value: %s", exclude_patterns)
            exclude_patterns = DEFAULT_EXCLUDE_PATTERNS
        return {
            "nextflow": {
                "debug": False,
                # deliberately not the server's default of "warnings": the value must differ from the
                # defaults for the configuration change to trigger the workspace scan
                "errorReportingMode": _SCAN_TRIGGERING_ERROR_REPORTING_MODE,
                "files": {"exclude": exclude_patterns},
            }
        }

    def _start_server(self) -> None:
        """
        Starts the Nextflow Language Server.
        """

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def work_done_progress_create(params: dict) -> dict:
            token = str(params.get("token", ""))
            with self._progress_lock:
                self._active_progress_tokens.add(token)
                self._scan_complete.clear()
            return {}

        def progress_handler(params: dict) -> None:
            token = str(params.get("token", ""))
            value = params.get("value", {})
            kind = value.get("kind")
            if kind == "begin":
                with self._progress_lock:
                    self._active_progress_tokens.add(token)
                    self._scan_complete.clear()
                log.info("Nextflow LS progress [%s]: started - %s", token, value.get("title", ""))
            elif kind == "report":
                log.debug("Nextflow LS progress [%s]: %s", token, value.get("message", ""))
            elif kind == "end":
                with self._progress_lock:
                    self._active_progress_tokens.discard(token)
                    if not self._active_progress_tokens:
                        self._scan_complete.set()
                log.info("Nextflow LS progress [%s]: ended", token)

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_request("window/workDoneProgress/create", work_done_progress_create)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", progress_handler)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Nextflow server process")
        self.server.start()

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(self._create_initialize_params())

        capabilities = init_response["capabilities"]
        assert "textDocumentSync" in capabilities, "Server must support textDocumentSync"
        assert "hoverProvider" in capabilities, "Server must support hover"
        assert "completionProvider" in capabilities, "Server must support code completion"
        assert "definitionProvider" in capabilities, "Server must support go to definition"
        assert "referencesProvider" in capabilities, "Server must support find references"
        assert "documentSymbolProvider" in capabilities, "Server must support document symbols"
        assert "workspaceSymbolProvider" in capabilities, "Server must support workspace symbols"

        self.server.notify.initialized({})

        # The server does not index anything on `initialized`; it (re-)scans the workspace only when a
        # configuration change arrives whose error reporting mode, exclude patterns or plugin registry
        # URL differ from what it currently holds. Without this notification, every symbol request
        # answers with an empty result.
        self._scan_complete.clear()
        self.server.notify.workspace_did_change_configuration({"settings": self._create_configuration_settings()})

        log.info("Waiting for the Nextflow workspace scan to complete...")
        if self._scan_complete.wait(timeout=_WORKSPACE_SCAN_TIMEOUT):
            log.info("Nextflow LS ready")
        else:
            log.warning("Nextflow LS did not signal scan completion within %.0fs; proceeding anyway", _WORKSPACE_SCAN_TIMEOUT)

    def _flush_deferred_workspace_scan(self, relative_file_path: str) -> None:
        """
        Forces the workspace scan, which the server defers past the first request of a session.

        The scan runs in ``LanguageService.update0`` behind a 1s debounce, and only on a round with no
        pending file change; the session's first ``didOpen`` re-defers it, leaving references to be
        answered from an AST cache holding just that one file.

        ``completion`` calls ``updateNow``, which runs the update synchronously before replying, so two
        such requests force the scan whatever the workspace size: the first drains the pending change,
        the second finds none and scans. Their results are discarded.
        """
        if self._workspace_scan_flushed:
            return

        params: lsp_types.CompletionParams = {
            "textDocument": {"uri": self._resolve_file_uri(relative_file_path)},
            "position": {"line": 0, "character": 0},
        }
        for _ in range(2):
            try:
                self.server.send.completion(params)
            except Exception as e:
                log.debug("Completion request used to flush the Nextflow workspace scan failed: %s", e)
        self._workspace_scan_flushed = True

    @override
    def _send_references_request(self, relative_file_path: str, line: int, column: int) -> list[lsp_types.Location] | None:
        """
        Flushes the server's pending recompile before asking for references.

        Every ``didOpen``/``didChange`` schedules a debounced (1s) update of the file's AST, and
        ``LanguageService.references`` is the one request that does not await it (``documentSymbol``,
        ``codeLens``, ``documentLink`` and ``semanticTokensFull`` all do). A references request issued
        within the debounce window therefore races the recompile of the very file it asks about and can
        come back empty. Sending a ``documentSymbol`` request for the same file first is a cheap way to
        block until the update has been applied.
        """
        self._flush_deferred_workspace_scan(relative_file_path)
        self.server.send.document_symbol({"textDocument": {"uri": self._resolve_file_uri(relative_file_path)}})
        return super()._send_references_request(relative_file_path, line, column)

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        """No blind wait is needed: _send_references_request synchronises with the server explicitly."""
        return 0.0

    @override
    def _document_symbols_cache_fingerprint(self) -> Hashable:
        normalize_symbol_name_version = 1
        return normalize_symbol_name_version

    @override
    def _normalize_symbol_name(self, symbol: RawDocumentSymbol, relative_file_path: str) -> str:
        """
        Strips the declaration keyword the language server prefixes to every symbol name
        ("process GREET", "workflow SAY_HELLO", "function foo"), so that symbols can be addressed
        by the name they are written with in the source. The implicit entry workflow keeps its
        "<entry>" placeholder name, which is what the server calls it.
        """
        name = symbol["name"]
        prefix, sep, rest = name.partition(" ")
        if sep and prefix in _SYMBOL_NAME_PREFIXES:
            return rest
        return name
