"""
Provides Nim specific instantiation of the LanguageServer class using nimlangserver.
Contains various configurations and settings specific to Nim language.
"""

import copy
import json
import logging
import os
import pathlib
import shutil
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, ReferenceInSymbol, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_process import LanguageServerProcess
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo, StringDict
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

if TYPE_CHECKING:
    from collections.abc import Hashable

    from solidlsp.ls import DocumentSymbols, LSPFileBuffer
    from solidlsp.ls_types import Hover
    from solidlsp.lsp_protocol_handler.lsp_types import (
        Definition,
        DefinitionParams,
        DocumentSymbol,
        Location,
        LocationLink,
        SymbolInformation,
    )

log = logging.getLogger(__name__)

ENCODING = "utf-8"

# Default nimsuggest.cfg content — helps nimsuggest operate reliably with the language server.
# Only written when the project does not already have a nimsuggest.cfg.
_NIMSUGGEST_CFG = """\
# Auto-generated nimsuggest.cfg for language server stability
# This supplements the project's nim.cfg without overriding it

-d:nimsuggest
-d:nimSuggestSkipStatic
-d:nimscript

--errorMax:100
--maxLoopIterationsVM:10000000

--skipProjCfg:off
--skipUserCfg:on
--skipParentCfg:on
--verbosity:0
--hints:off
--notes:off
"""

# Template for auto-generated nim.cfg — provides path hints so nimsuggest can
# resolve imports. Only written when no nim.cfg exists and a .nimble file is present.
_NIM_CFG_TEMPLATE = """\
# Auto-generated nim.cfg for nimsuggest/nimlangserver

--path:"."
{extra_paths}
--define:ssl
--define:useStdLib

--hint:XDeclaredButNotUsed:off
--hint:XCannotRaiseY:off
--hint:User:off
"""


class NimLanguageServerProcess(LanguageServerProcess):
    """Custom process handler for nimlangserver.

    nimlangserver only supports the Content-Length header in LSP messages.
    The standard implementation also sends Content-Type, which causes
    nimlangserver to fail to parse messages.
    """

    @override
    def _send_payload(self, payload: StringDict) -> None:
        if not self.process or not self.process.stdin:
            return
        self._trace("solidlsp", "ls", payload)

        body = json.dumps(payload, check_circular=False, ensure_ascii=False, separators=(",", ":")).encode(ENCODING)
        header = f"Content-Length: {len(body)}\r\n\r\n".encode(ENCODING)

        with self._stdin_lock:
            try:
                self.process.stdin.write(header + body)
                self.process.stdin.flush()
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                log.error("Failed to write to stdin: %s", e)


class NimLanguageServer(SolidLanguageServer):
    """Nim language server integration using nimlangserver.

    Uses nimlangserver (installed via nimble) as the LSP backend. Key implementation notes:

    - **Content-Type workaround**: nimlangserver (as of 1.12.0) cannot parse LSP messages
      that include a Content-Type header. NimLanguageServerProcess overrides _send_payload
      to send only the Content-Length header.
    - **Config file generation**: On startup, creates nimsuggest.cfg and nim.cfg in the
      project root if they don't already exist. These are required for reliable nimsuggest
      operation (import resolution, stability). Existing config files are never overwritten.
    - **Retry logic for document symbols**: nimlangserver delegates analysis to nimsuggest,
      which runs as a separate process on a TCP port. When nimsuggest crashes or is still
      initializing, it reports port=0 (meaning "no port assigned / not listening"). Requests
      made during this window return empty results. The request_document_symbols override
      retries with backoff, waiting for nimsuggest to restart and obtain a valid port.
      This primarily affects document symbols because it is typically the first heavy request
      sent after server initialization, hitting the window where nimsuggest may not be ready.
      Other LSP methods (definition, references) are usually called later, after nimsuggest
      has stabilized.
    """

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """Find or install nimlangserver and return the path to the executable."""
            nimble_bin = os.path.expanduser(os.path.join("~", ".nimble", "bin"))

            # Check if nimlangserver is already available on PATH
            system_nimlangserver = shutil.which("nimlangserver")
            if system_nimlangserver:
                log.info("Found nimlangserver at %s", system_nimlangserver)
                return system_nimlangserver

            # Also check the standard nimble bin directory (may not be on PATH)
            nimlangserver_path = os.path.join(nimble_bin, "nimlangserver")
            if os.path.exists(nimlangserver_path):
                log.info("Found nimlangserver at %s", nimlangserver_path)
                return nimlangserver_path

            # Check if nim and nimble are installed
            is_nim_installed = shutil.which("nim") is not None or os.path.exists(os.path.join(nimble_bin, "nim"))
            is_nimble_installed = shutil.which("nimble") is not None or os.path.exists(os.path.join(nimble_bin, "nimble"))

            if not is_nim_installed or not is_nimble_installed:
                missing = []
                if not is_nim_installed:
                    missing.append("nim")
                if not is_nimble_installed:
                    missing.append("nimble")
                raise RuntimeError(
                    f"{' and '.join(missing)} not found in PATH.\n"
                    "Please install Nim using one of these methods:\n"
                    "  - Using choosenim: curl https://nim-lang.org/choosenim/init.sh -sSf | sh\n"
                    "  - From official website: https://nim-lang.org/install.html\n"
                    "  - Using package manager (brew install nim, apt install nim, etc.)\n"
                    "After installation, ensure nim and nimble are in your PATH."
                )

            # Install nimlangserver via nimble
            log.info("Installing nimlangserver via nimble")
            nimble_cmd = shutil.which("nimble") or os.path.join(nimble_bin, "nimble")
            deps = RuntimeDependencyCollection(
                [
                    RuntimeDependency(
                        id="nimlangserver",
                        description="Nim Language Server",
                        command=[nimble_cmd, "install", "nimlangserver", "-y"],
                        platform_id=None,
                    )
                ]
            )

            try:
                deps.install(nimble_bin)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to install nimlangserver via nimble: {e}\nPlease try installing manually with: nimble install nimlangserver"
                ) from e

            # After install, check PATH and nimble bin
            installed_nimlangserver = shutil.which("nimlangserver")
            if installed_nimlangserver:
                log.info("Found nimlangserver in PATH at %s", installed_nimlangserver)
                return installed_nimlangserver

            if os.path.exists(nimlangserver_path):
                log.info("Found nimlangserver at %s", nimlangserver_path)
                return nimlangserver_path

            raise RuntimeError(
                "nimlangserver installation appeared to succeed but the binary was not found.\n"
                "Please verify installation with: nimble list -i | grep nimlangserver"
            )

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path]

        @override
        def create_launch_command_env(self) -> dict[str, str]:
            """Ensure nimble bin is in PATH so nimlangserver can find nimsuggest."""
            nimble_bin = os.path.expanduser(os.path.join("~", ".nimble", "bin"))
            current_path = os.environ.get("PATH", "")
            if nimble_bin not in current_path.split(os.pathsep):
                return {"PATH": f"{nimble_bin}{os.pathsep}{current_path}"}
            return {}

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a NimLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        # Initialize server_ready before parent class initialization
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()

        # Track nimsuggest port health to avoid marking server as ready when port=0.
        # port=0 means nimsuggest has crashed or hasn't started listening yet.
        # These are threading.Events because they're written by notification handler threads
        # and read by request threads.
        self._has_port_error = threading.Event()
        self._nimsuggest_functional = threading.Event()

        super().__init__(
            config,
            repository_root_path,
            None,
            "nim",
            solidlsp_settings,
            cache_version_raw_document_symbols=2,
        )

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    @override
    def _create_server_process(  # type: ignore[override]
        self,
        process_launch_info: ProcessLaunchInfo,
        logging_fn: "Callable[[str, str, StringDict | str], None] | None",
        config: LanguageServerConfig,
    ) -> "NimLanguageServerProcess":
        return NimLanguageServerProcess(
            process_launch_info,
            language=self.language,
            determine_log_level=self._determine_log_level,
            logger=logging_fn,
            start_independent_lsp_process=config.start_independent_lsp_process,
        )

    @staticmethod
    @override
    def _determine_log_level(line: str) -> int:
        """Classify nimlangserver stderr lines to appropriate log levels."""
        if line.startswith("DBG ") or "DBG " in line[:20]:
            return logging.DEBUG
        elif line.startswith("INF ") or "INF " in line[:20]:
            return logging.INFO
        elif line.startswith("WRN ") or "WRN " in line[:20]:
            return logging.WARNING
        elif line.startswith("ERR ") or "ERR " in line[:20]:
            # SVG/resource missing errors are non-critical
            if "cannot open:" in line and ".svg" in line:
                return logging.WARNING
            return logging.ERROR
        return logging.INFO

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "nimcache",
            "htmldocs",
            "node_modules",
        ]

    def _create_nim_config_if_needed(self) -> None:
        """Create Nim config files if the project doesn't already have them.

        nimsuggest (the analysis backend used by nimlangserver) needs configuration to
        reliably resolve imports and avoid noisy diagnostics. Without a nimsuggest.cfg,
        it may crash or produce spurious errors. Without a nim.cfg with --path hints,
        cross-module imports often fail to resolve.

        These files are only written when absent — existing project config is never overwritten.
        """
        try:
            nim_cfg_path = os.path.join(self.repository_root_path, "nim.cfg")
            nimsuggest_cfg_path = os.path.join(self.repository_root_path, "nimsuggest.cfg")

            if not os.path.exists(nimsuggest_cfg_path):
                with open(nimsuggest_cfg_path, "w") as f:
                    f.write(_NIMSUGGEST_CFG)
                log.warning("Created nimsuggest.cfg in project root for nimsuggest stability. Consider adding it to .gitignore.")

            if not os.path.exists(nim_cfg_path):
                nimble_files = list(pathlib.Path(self.repository_root_path).glob("*.nimble"))
                if nimble_files:
                    extra_paths = ""
                    if os.path.exists(os.path.join(self.repository_root_path, "src")):
                        extra_paths += '--path:"src"\n'
                    if os.path.exists(os.path.join(self.repository_root_path, "tests")):
                        extra_paths += '--path:"tests"\n'
                    with open(nim_cfg_path, "w") as f:
                        f.write(_NIM_CFG_TEMPLATE.format(extra_paths=extra_paths))
                    log.warning("Created nim.cfg in project root with path hints for nimsuggest. Consider adding it to .gitignore.")
            else:
                log.debug("Found existing nim.cfg, respecting project configuration")
        except Exception as e:
            log.debug("Could not create config files: %s", e)

    def _detect_nim_project_mapping(self) -> list[dict[str, str]] | None:
        """Detect the Nim project entry point and return a ``projectMapping`` list.

        nimlangserver uses ``projectMapping`` to decide which file to pass as root
        to nimsuggest.  Without an explicit mapping it may pick ``config.nims``
        (a NimScript config file, not a compilable source) which prevents
        nimsuggest from properly analysing the project.

        When a ``.nimble`` file is present we look for the conventional entry
        ``.nim`` file and create a mapping so all ``.nim`` files use it.
        """
        root = pathlib.Path(self.repository_root_path)

        nimble_files = list(root.glob("*.nimble"))
        if not nimble_files:
            return None

        nimble_name = nimble_files[0].stem  # e.g. "myproject" from "myproject.nimble"

        candidates = [
            root / f"{nimble_name}.nim",
            root / "src" / f"{nimble_name}.nim",
            root / "main.nim",
            root / "src" / "main.nim",
        ]

        entry_file: pathlib.Path | None = None
        for candidate in candidates:
            if candidate.exists():
                entry_file = candidate.relative_to(root)
                break

        if entry_file is None:
            # Fall back to first .nim file in root
            nim_files = sorted(root.glob("*.nim"))
            if nim_files:
                entry_file = nim_files[0].relative_to(root)

        if entry_file is None:
            return None

        log.info("Detected Nim project entry point: %s (from %s)", entry_file, nimble_files[0].name)
        return [{"projectFile": str(entry_file), "fileRegex": r".*\.nim$"}]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "signatureHelp": {"dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentHighlight": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "codeAction": {"dynamicRegistration": True},
                    "codeLens": {"dynamicRegistration": True},
                    "formatting": {"dynamicRegistration": True},
                    "rangeFormatting": {"dynamicRegistration": True},
                    "onTypeFormatting": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                    "documentLink": {"dynamicRegistration": True},
                    "typeDefinition": {"dynamicRegistration": True},
                    "implementation": {"dynamicRegistration": True},
                    "colorProvider": {"dynamicRegistration": True},
                    "foldingRange": {"dynamicRegistration": True, "rangeLimit": 5000, "lineFoldingOnly": True},
                    "declaration": {"dynamicRegistration": True},
                    "selectionRange": {"dynamicRegistration": True},
                },
                "workspace": {
                    "applyEdit": True,
                    "workspaceEdit": {"documentChanges": True},
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                    "executeCommand": {"dynamicRegistration": True},
                    "workspaceFolders": True,
                    "configuration": True,
                },
            },
            "initializationOptions": {
                "nim": {
                    "timeout": 120000,
                    "autoRestart": True,
                    "nimsuggestIdleTimeout": 300000,
                    "notificationVerbosity": "warning",
                    "workingDirectoryMapping": [
                        {"projectFile": "*.nimble", "directory": "."},
                        {"projectFile": "src/*.nim", "directory": "."},
                    ],
                }
            },
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }
        return initialize_params  # type: ignore[return-value]

    def _start_server(self) -> None:
        """
        Starts the Nim Language Server, waits for the server to be ready and yields the LanguageServer instance.
        """
        self._create_nim_config_if_needed()

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()

        def execute_client_command_handler(_: dict) -> list:
            return []

        def do_nothing(_: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info("LSP: window/logMessage: %s", msg)
            message_text = msg.get("message", "")
            if "initialized" in message_text.lower() or "ready" in message_text.lower():
                log.info("Nim language server ready signal detected")
                self.server_ready.set()

        def window_show_message(msg: dict) -> None:
            log.info("LSP: window/showMessage: %s", msg)
            message_text = msg.get("message", "")
            msg_type = msg.get("type", 3)

            if msg_type == 1:  # Error
                if "cannot open:" in message_text and ".svg" in message_text:
                    log.warning("Non-critical resource missing: %s", message_text)
                elif "Failed to parse nimsuggest port" in message_text:
                    log.error("Nimsuggest port parsing failed: %s", message_text)
                    self._has_port_error.set()
                    return
                else:
                    log.error("Nim server error: %s", message_text)
            elif "initialized" in message_text.lower() or "ready" in message_text.lower():
                if self._has_port_error.is_set():
                    log.warning(
                        "Ignoring 'initialized' signal because nimsuggest has port errors. "
                        "Waiting for extension/statusUpdate with port > 0."
                    )
                    return
                log.info("Nim language server ready signal detected from showMessage")
                self.server_ready.set()

        def workspace_configuration_handler(params: dict) -> list:
            """Handle workspace/configuration requests - nimlangserver expects an array."""
            items = params.get("items", [])
            return [None for _ in items]

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("window/showMessage", window_show_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_request("workspace/configuration", workspace_configuration_handler)

        def extension_status_update(params: dict) -> None:
            """Handle Nim-specific status updates which include nimsuggest instance info."""
            if "projectErrors" in params:
                errors = params["projectErrors"]
                has_port_error_in_update = False
                for error in errors:
                    error_msg = error.get("errorMessage", "")
                    project_file = error.get("projectFile", "")

                    if "cannot open:" in error_msg and any(ext in error_msg for ext in [".svg", ".png", ".ico"]):
                        log.warning("Non-critical resource missing in %s: %s", project_file, error_msg)
                    elif "Failed to parse nimsuggest port" in error_msg:
                        log.error("Nimsuggest port issue for %s: %s", project_file, error_msg)
                        has_port_error_in_update = True
                    else:
                        log.error("Project error in %s: %s", project_file, error_msg)

                if has_port_error_in_update:
                    self._has_port_error.set()

            if "nimsuggestInstances" in params:
                instances = params["nimsuggestInstances"]
                any_functional = False
                for instance in instances:
                    port = instance.get("port", 0)
                    project = instance.get("projectFile", "")
                    if port > 0:
                        any_functional = True
                        log.debug("Nimsuggest instance running for %s on port %d", project, port)
                    else:
                        log.warning("Nimsuggest instance for %s has port=0 (not functional)", project)

                if any_functional:
                    self._has_port_error.clear()
                    self._nimsuggest_functional.set()
                    if not self.server_ready.is_set():
                        log.info("Nimsuggest has valid port, marking server as ready")
                        self.server_ready.set()
                elif instances:
                    self._nimsuggest_functional.clear()
                    if self.server_ready.is_set():
                        log.warning("All nimsuggest instances have port=0, clearing server ready state")
                        self.server_ready.clear()

        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("extension/statusUpdate", extension_status_update)

        log.info("Starting Nim server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        # When a .nimble project exists, configure projectMapping so nimlangserver
        # starts nimsuggest with the correct entry-point .nim file instead of
        # potentially picking up config.nims (which is a NimScript config, not a
        # compilable source file).
        project_mapping = self._detect_nim_project_mapping()
        if project_mapping:
            nim_opts: dict = initialize_params["initializationOptions"]["nim"]  # type: ignore[call-overload,index,assignment]
            nim_opts["projectMapping"] = project_mapping

        log.info("Sending initialize request to Nim language server")
        init_response = self.server.send.initialize(initialize_params)
        log.debug("Received initialize response from Nim server: %s", init_response)

        caps = init_response["capabilities"]
        for cap_name in ("completionProvider", "documentSymbolProvider", "definitionProvider", "referencesProvider"):
            if cap_name in caps:
                log.info("Nim server supports %s", cap_name)

        self.server.notify.initialized({})

        # Wait for server readiness with timeout
        log.info("Waiting for Nim language server to be ready...")
        if not self.server_ready.wait(timeout=15.0):
            try:
                test_response = self.server.send.workspace_symbol({"query": ""})
                if test_response is not None:
                    log.info("Nim server responded to test query, marking as ready")
                else:
                    log.warning("Nim server not responding, may need manual restart")
            except Exception as e:
                log.warning("Error testing Nim server readiness: %s", e)
            # Proceed anyway
            self.server_ready.set()
        else:
            log.info("Nim server initialization complete")

    # Version key for the symbol range fix. Bump this whenever
    # _fix_nim_symbol_ranges logic changes to invalidate cached results.
    _NIM_SYMBOL_RANGE_FIX_VERSION = 2

    _RETRY_DELAYS = (1.0, 2.0, 3.0)

    # Maximum number of goto-definition LSP requests during the fallback
    # reference search in _find_references_via_goto_definition.
    _GOTO_DEF_FALLBACK_MAX_REQUESTS = 200

    _T = TypeVar("_T")

    def _retry_on_empty(
        self,
        fn: Callable[[], _T],
        description: str,
        *,
        check: Callable[[_T], bool] = bool,  # type: ignore[assignment]
    ) -> _T:
        """Retry *fn()* with backoff while *check(result)* is falsy."""
        for attempt in range(len(self._RETRY_DELAYS) + 1):
            result = fn()
            if check(result):
                if attempt > 0:
                    log.info("Got %s after %d retries", description, attempt)
                return result
            if attempt >= len(self._RETRY_DELAYS):
                log.warning(
                    "No %s after %d retries (port_error=%s, functional=%s).",
                    description,
                    len(self._RETRY_DELAYS),
                    self._has_port_error.is_set(),
                    self._nimsuggest_functional.is_set(),
                )
                return result
            delay = self._RETRY_DELAYS[attempt]
            log.info(
                "Empty %s, nimsuggest may need more time. Retry %d/%d in %ss.",
                description,
                attempt + 1,
                len(self._RETRY_DELAYS),
                delay,
            )
            time.sleep(delay)
        return result  # unreachable but satisfies type checker

    @override
    def _cache_context_fingerprint(self) -> "Hashable | None":
        return ("nim_range_fix", self._NIM_SYMBOL_RANGE_FIX_VERSION)

    @override
    def _request_document_symbols(
        self, relative_file_path: str, file_data: "LSPFileBuffer | None"
    ) -> "list[SymbolInformation] | list[DocumentSymbol] | None":
        """Override to fix nimlangserver's incomplete range bug.

        nimlangserver reports ranges that only cover the symbol name instead of
        the full body.  This applies to both ``DocumentSymbol`` (top-level
        ``range``) and ``SymbolInformation`` (``location.range``) formats.
        This override extends ranges using indentation-based analysis so that
        ``SymbolBody`` can extract the complete text.
        """
        symbols = super()._request_document_symbols(relative_file_path, file_data)

        if not symbols:
            return symbols

        first: dict = symbols[0]  # type: ignore[assignment]  # LSP returns TypedDicts

        # Determine where the range lives depending on the LSP response format:
        # - DocumentSymbol: top-level "range" key
        # - SymbolInformation: nested "location" -> "range"
        is_document_symbol = "range" in first
        location = first.get("location")
        is_symbol_information = not is_document_symbol and isinstance(location, dict) and "range" in location
        if not is_document_symbol and not is_symbol_information:
            return symbols

        # Read file content for indentation analysis
        absolute_path = os.path.join(self.repository_root_path, relative_file_path)
        with open(absolute_path, encoding=ENCODING) as f:
            lines = f.read().split("\n")

        self._fix_nim_symbol_ranges(symbols, lines, len(lines) - 1, is_symbol_information=is_symbol_information)  # type: ignore[arg-type]
        return symbols

    @classmethod
    def _fix_nim_symbol_ranges(
        cls,
        symbols: list[dict],
        lines: list[str],
        container_end_line: int,
        *,
        is_symbol_information: bool = False,
    ) -> None:
        """Fix symbol ranges in-place by extending them to cover the full body.

        nimlangserver reports ranges that only cover the symbol name.
        This method extends each symbol's range to span from the start of the
        declaration line through all indented body lines.

        Handles both ``DocumentSymbol`` (top-level ``range``) and
        ``SymbolInformation`` (``location.range``) formats.
        """

        def _get_range(symbol: dict) -> dict | None:
            if is_symbol_information:
                loc = symbol.get("location")
                return loc.get("range") if loc else None
            return symbol.get("range")

        for i, symbol in enumerate(symbols):
            range_info = _get_range(symbol)
            if not range_info:
                continue

            # Preserve the original name range as selectionRange before extending.
            # nimlangserver's original range covers just the symbol name; after we
            # extend it to the full body, consumers need selectionRange to locate
            # the name (e.g. for hover requests).
            if "selectionRange" not in symbol:
                symbol["selectionRange"] = copy.deepcopy(range_info)

            range_start_line = range_info["start"]["line"]
            range_end_line = range_info["end"]["line"]

            # If the range already spans multiple lines, assume it is correct
            if range_start_line != range_end_line:
                if symbol.get("children"):
                    cls._fix_nim_symbol_ranges(symbol["children"], lines, range_end_line, is_symbol_information=is_symbol_information)
                continue

            # Upper bound: start of next sibling, or container end
            if i + 1 < len(symbols):
                next_range = _get_range(symbols[i + 1])
                upper_bound = next_range["start"]["line"] - 1 if next_range else container_end_line
            else:
                upper_bound = container_end_line

            # Expand start to beginning of the declaration (respecting indent)
            if range_start_line < len(lines):
                base_line = lines[range_start_line]
                indent = len(base_line) - len(base_line.lstrip())
                range_info["start"]["character"] = indent

            # Find the end of the body via indentation
            new_end_line = cls._find_nim_body_end(lines, range_start_line, upper_bound)

            if new_end_line < len(lines):
                range_info["end"]["line"] = new_end_line
                range_info["end"]["character"] = len(lines[new_end_line])
            else:
                range_info["end"]["line"] = len(lines) - 1
                range_info["end"]["character"] = len(lines[-1])

            # Fix children recursively (DocumentSymbol only)
            if symbol.get("children"):
                cls._fix_nim_symbol_ranges(symbol["children"], lines, new_end_line, is_symbol_information=is_symbol_information)

    @staticmethod
    def _find_nim_body_end(lines: list[str], start_line: int, upper_bound: int) -> int:
        """Find the last line of a Nim symbol's body using indentation analysis.

        Starting from the declaration line, scans forward to find all contiguous lines
        that are more indented than the declaration. Empty lines within the body are
        included. The scan stops at the first non-empty line with indentation <= the
        declaration line, or at ``upper_bound``.

        :param lines: all lines of the source file.
        :param start_line: 0-indexed line number of the symbol declaration.
        :param upper_bound: maximum line index (inclusive) to scan.
        :return: 0-indexed line number of the last body line.
        """
        if start_line >= len(lines):
            return start_line

        base_line = lines[start_line]
        base_indent = len(base_line) - len(base_line.lstrip())
        last_content_line = start_line

        for line_idx in range(start_line + 1, min(upper_bound + 1, len(lines))):
            line = lines[line_idx]
            stripped = line.strip()

            if not stripped:
                # Empty line — might be inside the body; continue looking
                continue

            line_indent = len(line) - len(line.lstrip())
            if line_indent <= base_indent:
                # Reached a line at the same or lower indent — body ends
                break

            last_content_line = line_idx

        return last_content_line

    @override
    def request_document_symbols(self, relative_file_path: str, file_buffer: "LSPFileBuffer | None" = None) -> "DocumentSymbols":
        """Override to add bounded retry when nimsuggest has port issues.

        nimlangserver delegates code analysis to nimsuggest, which runs as a separate process
        and communicates over a TCP port. When nimsuggest crashes (e.g. due to malformed code
        or internal errors) nimlangserver automatically restarts it, but during the restart
        window nimsuggest reports port=0 (meaning "not listening / no port assigned"). Any
        LSP request forwarded to nimsuggest during this window returns empty results.

        This primarily affects document symbols because it is typically the first heavy
        request after server startup, hitting the initialization window. Later requests
        (definition, references, hover) are usually made after nimsuggest has stabilized.

        We retry with backoff rather than detecting the crash and restarting, because
        nimlangserver already handles the restart internally — we just need to wait for
        nimsuggest to come back up with a valid port.
        """
        from solidlsp.ls import DocumentSymbols

        max_retries = 3
        retry_delays = [2.0, 5.0, 10.0]

        for attempt in range(max_retries + 1):
            result = super().request_document_symbols(relative_file_path, file_buffer)

            if result.root_symbols:
                if attempt > 0:
                    log.info(
                        "Got %d root symbols for %s after %d retries",
                        len(result.root_symbols),
                        relative_file_path,
                        attempt,
                    )
                return result

            # Empty result - check if it's likely due to nimsuggest port issues
            if not self._has_port_error.is_set() and self._nimsuggest_functional.is_set():
                return result

            if attempt >= max_retries:
                log.warning(
                    "No document symbols for %s after %d retries. Nimsuggest may be non-functional (port_error=%s, functional=%s).",
                    relative_file_path,
                    max_retries,
                    self._has_port_error.is_set(),
                    self._nimsuggest_functional.is_set(),
                )
                return result

            delay = retry_delays[attempt]
            log.info(
                "Empty document symbols for %s, nimsuggest may not be ready (port_error=%s). Retry %d/%d in %ss.",
                relative_file_path,
                self._has_port_error.is_set(),
                attempt + 1,
                max_retries,
                delay,
            )

            # Invalidate cached empty result before retry
            cache_key = relative_file_path
            self._document_symbols_cache.pop(cache_key, None)

            self.server_ready.wait(timeout=delay)

        return DocumentSymbols([])

    @override
    def _request_hover(self, uri: str, line: int, column: int) -> "Hover | None":
        """Override to add bounded retry for Nim hover requests.

        nimsuggest may need additional analysis time after initialization before
        hover results become available, even when it reports as functional.
        """
        return self._retry_on_empty(
            lambda: super(NimLanguageServer, self)._request_hover(uri, line, column),
            "hover info",
            check=lambda r: r is not None,
        )

    @override
    def _send_references_request(self, relative_file_path: str, line: int, column: int) -> "list[Location] | None":
        """Override to add bounded retry for Nim references requests.

        nimsuggest may need additional analysis time after initialization before
        references results become available, even when it reports as functional.
        """
        return self._retry_on_empty(
            lambda: super(NimLanguageServer, self)._send_references_request(relative_file_path, line, column),
            f"references for {relative_file_path}",
        )

    @override
    def _send_definition_request(self, definition_params: "DefinitionParams") -> "Definition | list[LocationLink] | None":
        """Override to add bounded retry for Nim goto-definition requests.

        nimsuggest may need additional analysis time after initialization before
        definition results become available.
        """
        return self._retry_on_empty(
            lambda: super(NimLanguageServer, self)._send_definition_request(definition_params),
            "definition result",
        )

    @override
    def request_referencing_symbols(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        include_imports: bool = True,
        include_self: bool = False,
        include_body: bool = False,
        include_file_symbols: bool = False,
    ) -> list[ReferenceInSymbol]:
        """Override to add a goto-definition fallback for Nim.

        nimsuggest's ``textDocument/references`` can return incomplete results,
        especially for cross-file references.  When the standard path returns
        nothing we fall back to scanning all project symbols and checking
        whether their goto-definition resolves to the target location.
        """
        result = super().request_referencing_symbols(
            relative_file_path,
            line,
            column,
            include_imports=include_imports,
            include_self=include_self,
            include_body=include_body,
            include_file_symbols=include_file_symbols,
        )
        if result:
            return result

        log.info(
            "No references found via LSP for %s:%d:%d, trying goto-definition fallback.",
            relative_file_path,
            line,
            column,
        )

        return self._find_references_via_goto_definition(
            relative_file_path, line, column, include_self=include_self, include_body=include_body
        )

    def _find_references_via_goto_definition(
        self,
        target_file: str,
        target_line: int,
        target_col: int,
        *,
        include_self: bool = False,
        include_body: bool = False,
    ) -> list[ReferenceInSymbol]:
        """Find references by text-searching for the target symbol name across all
        source files and verifying each occurrence via goto-definition.

        For each text occurrence of the symbol name we call goto-definition.
        If it resolves to ``(target_file, target_line, target_col)`` we find
        the containing symbol and include it in the results.
        """
        import re

        from solidlsp import ls_types

        # Resolve the target symbol's name from its position
        target_symbols = self.request_document_symbols(target_file)
        target_name: str | None = None
        for sym in target_symbols.iter_symbols():
            sel = sym.get("selectionRange", {}).get("start", {})
            if sel.get("line") == target_line and sel.get("character") == target_col:
                target_name = sym["name"]
                break

        if not target_name:
            log.warning("Could not determine symbol name at %s:%d:%d for fallback.", target_file, target_line, target_col)
            return []

        log.info("Goto-definition fallback: searching for '%s' across project files.", target_name)

        name_pattern = re.compile(r"\b" + re.escape(target_name) + r"\b")

        result: list[ReferenceInSymbol] = []
        seen: set[tuple[str, int, int]] = set()
        lsp_request_count = 0

        overview = self.request_overview("")

        cap_reached = False
        for file_path in overview:
            if cap_reached:
                break
            if not file_path.endswith(".nim"):
                continue
            content = self.retrieve_full_file_content(file_path)
            lines = content.split("\n")

            for line_idx, line_text in enumerate(lines):
                if cap_reached:
                    break
                for match in name_pattern.finditer(line_text):
                    col_idx = match.start()

                    # Skip the target definition itself unless include_self
                    if file_path == target_file and line_idx == target_line and col_idx == target_col:
                        if not include_self:
                            continue

                    # Guard against unbounded LSP requests
                    if lsp_request_count >= self._GOTO_DEF_FALLBACK_MAX_REQUESTS:
                        log.warning(
                            "Goto-definition fallback hit request cap (%d). Stopping scan.",
                            self._GOTO_DEF_FALLBACK_MAX_REQUESTS,
                        )
                        cap_reached = True
                        break

                    # Call goto-definition to verify this occurrence points to the target
                    lsp_request_count += 1
                    try:
                        definitions = self.request_definition(file_path, line_idx, col_idx)
                    except Exception:
                        log.debug("Goto-definition failed at %s:%d:%d, skipping.", file_path, line_idx, col_idx)
                        continue

                    is_reference = False
                    for defn in definitions:
                        def_start = defn.get("range", {}).get("start", {})
                        if (
                            defn.get("relativePath") == target_file
                            and def_start.get("line") == target_line
                            and def_start.get("character") == target_col
                        ):
                            is_reference = True
                            break

                    if not is_reference:
                        continue

                    # Find the containing symbol for this reference
                    containing = self.request_containing_symbol(file_path, line_idx, col_idx, include_body=include_body)

                    if containing is None:
                        # Module-level code — create a file symbol
                        file_range = self._get_range_from_file_content(content)
                        location = ls_types.Location(
                            uri=pathlib.Path(os.path.join(self.repository_root_path, file_path)).as_uri(),
                            range=file_range,
                            absolutePath=str(os.path.join(self.repository_root_path, file_path)),
                            relativePath=file_path,
                        )
                        containing = ls_types.UnifiedSymbolInformation(
                            kind=ls_types.SymbolKind.File,
                            range=file_range,
                            selectionRange=file_range,
                            location=location,
                            name=os.path.splitext(os.path.basename(file_path))[0],
                            children=[],
                        )

                    # Deduplicate by containing symbol location
                    sym_sel = containing.get("selectionRange", {}).get("start", {})
                    dedup_key: tuple[str, int, int] = (
                        containing.get("location", {}).get("relativePath", "") or "",
                        sym_sel.get("line", -1),
                        sym_sel.get("character", -1),
                    )
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)

                    result.append(ReferenceInSymbol(symbol=containing, line=line_idx, character=col_idx))

        if result:
            log.info(
                "Goto-definition fallback found %d references for %s:%d:%d.",
                len(result),
                target_file,
                target_line,
                target_col,
            )

        return result
