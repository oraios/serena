"""
Provides Nim specific instantiation of the LanguageServer class using nimlangserver.
Contains various configurations and settings specific to Nim language.
"""

import json
import logging
import os
import pathlib
import shutil
import threading
from typing import TYPE_CHECKING

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_process import LanguageServerProcess
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo, StringDict
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

if TYPE_CHECKING:
    from solidlsp.ls import DocumentSymbols, LSPFileBuffer

log = logging.getLogger(__name__)

ENCODING = "utf-8"


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
    """
    Provides Nim specific instantiation of the LanguageServer class using nimlangserver.
    Contains various configurations and settings specific to Nim language.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a NimLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        nim_lsp_executable_path = self._setup_runtime_dependencies(config, solidlsp_settings)

        # Ensure nimble bin is in PATH for nimsuggest
        nimble_bin = os.path.expanduser("~/.nimble/bin")
        env: dict[str, str] = {}
        current_path = os.environ.get("PATH", "")
        if nimble_bin not in current_path.split(os.pathsep):
            env["PATH"] = f"{nimble_bin}{os.pathsep}{current_path}"

        # Initialize server_ready before parent class initialization
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()

        # Track nimsuggest port health to avoid marking server as ready when port=0
        self._has_port_error = False
        self._nimsuggest_functional = False

        process_launch_info = ProcessLaunchInfo(cmd=nim_lsp_executable_path, cwd=repository_root_path, env=env)

        super().__init__(
            config,
            repository_root_path,
            process_launch_info,
            "nim",
            solidlsp_settings,
        )

        # Replace the default LanguageServerProcess with our custom one that
        # only sends Content-Length headers (nimlangserver chokes on Content-Type)
        self.server.stop() if self.server.is_running() else None
        self.server = NimLanguageServerProcess(
            process_launch_info,
            language=self.language,
            determine_log_level=self._determine_log_level,
            logger=self.server._trace_log_fn,
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
        """Create or supplement Nim configuration to help nimsuggest work better."""
        try:
            nim_cfg_path = os.path.join(self.repository_root_path, "nim.cfg")
            nimsuggest_cfg_path = os.path.join(self.repository_root_path, "nimsuggest.cfg")

            if not os.path.exists(nimsuggest_cfg_path):
                with open(nimsuggest_cfg_path, "w") as f:
                    f.write("# Auto-generated nimsuggest.cfg for language server stability\n")
                    f.write("# This supplements the project's nim.cfg without overriding it\n\n")
                    f.write("-d:nimsuggest\n")
                    f.write("-d:nimSuggestSkipStatic\n")
                    f.write("-d:nimscript\n\n")
                    f.write("--errorMax:100\n")
                    f.write("--maxLoopIterationsVM:10000000\n\n")
                    f.write("--skipProjCfg:off\n")
                    f.write("--skipUserCfg:on\n")
                    f.write("--skipParentCfg:on\n")
                    f.write("--verbosity:0\n")
                    f.write("--hints:off\n")
                    f.write("--notes:off\n")
                log.info("Created nimsuggest.cfg to improve stability")

            if not os.path.exists(nim_cfg_path):
                nimble_files = list(pathlib.Path(self.repository_root_path).glob("*.nimble"))
                if nimble_files:
                    has_src = os.path.exists(os.path.join(self.repository_root_path, "src"))
                    has_tests = os.path.exists(os.path.join(self.repository_root_path, "tests"))
                    with open(nim_cfg_path, "w") as f:
                        f.write("# Auto-generated nim.cfg for nimsuggest/nimlangserver\n\n")
                        f.write('--path:"."\n')
                        if has_src:
                            f.write('--path:"src"\n')
                        if has_tests:
                            f.write('--path:"tests"\n')
                        f.write("\n--define:ssl\n--define:useStdLib\n\n")
                        f.write("--hint:XDeclaredButNotUsed:off\n")
                        f.write("--hint:XCannotRaiseY:off\n")
                        f.write("--hint:User:off\n")
                    log.info("Created nim.cfg with project paths")
            else:
                log.debug("Found existing nim.cfg, respecting project configuration")
        except Exception as e:
            log.debug("Could not create config files: %s", e)

    @classmethod
    def _setup_runtime_dependencies(cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings) -> str:
        """
        Setup runtime dependencies for Nim Language Server and return the path to the executable.
        """
        # Check if nimlangserver is already installed via nimble
        nimble_bin = os.path.expanduser("~/.nimble/bin")
        nimlangserver_path = os.path.join(nimble_bin, "nimlangserver")

        if os.path.exists(nimlangserver_path):
            log.info("Found nimlangserver at %s", nimlangserver_path)
            return nimlangserver_path

        # Check if nim and nimble are installed
        is_nim_installed = shutil.which("nim") is not None
        is_nimble_installed = shutil.which("nimble") is not None

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
        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="nimlangserver",
                    description="Nim Language Server",
                    command=["nimble", "install", "nimlangserver", "-y"],
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

        nimlangserver_path = os.path.join(nimble_bin, "nimlangserver")
        if os.path.exists(nimlangserver_path):
            log.info("Successfully installed nimlangserver at %s", nimlangserver_path)
            return nimlangserver_path

        nimlangserver_in_path = shutil.which("nimlangserver")
        if nimlangserver_in_path:
            log.info("Found nimlangserver in PATH at %s", nimlangserver_in_path)
            return nimlangserver_in_path

        raise RuntimeError(
            "nimlangserver installation appeared to succeed but the binary was not found.\n"
            "Please verify installation with: nimble list -i | grep nimlangserver"
        )

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
                    self._has_port_error = True
                    return
                else:
                    log.error("Nim server error: %s", message_text)
            elif "initialized" in message_text.lower() or "ready" in message_text.lower():
                if self._has_port_error:
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
                    self._has_port_error = True

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
                    self._has_port_error = False
                    self._nimsuggest_functional = True
                    if not self.server_ready.is_set():
                        log.info("Nimsuggest has valid port, marking server as ready")
                        self.server_ready.set()
                elif instances:
                    self._nimsuggest_functional = False
                    if self.server_ready.is_set():
                        log.warning("All nimsuggest instances have port=0, clearing server ready state")
                        self.server_ready.clear()

        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("extension/statusUpdate", extension_status_update)

        log.info("Starting Nim server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

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

    @override
    def request_document_symbols(self, relative_file_path: str, file_buffer: "LSPFileBuffer | None" = None) -> "DocumentSymbols":
        """Override to add bounded retry when nimsuggest has port issues.

        When nimsuggest crashes and restarts, the first request may return empty results
        because nimsuggest has port=0. This override retries with backoff, waiting for
        nimsuggest to become functional.
        """
        from solidlsp.ls import DocumentSymbols

        max_retries = 3
        retry_delays = [5.0, 15.0, 30.0]

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
            if not self._has_port_error and self._nimsuggest_functional:
                return result

            if attempt >= max_retries:
                log.warning(
                    "No document symbols for %s after %d retries. Nimsuggest may be non-functional (port_error=%s, functional=%s).",
                    relative_file_path,
                    max_retries,
                    self._has_port_error,
                    self._nimsuggest_functional,
                )
                return result

            delay = retry_delays[attempt]
            log.info(
                "Empty document symbols for %s, nimsuggest may not be ready (port_error=%s). Retry %d/%d in %ss.",
                relative_file_path,
                self._has_port_error,
                attempt + 1,
                max_retries,
                delay,
            )

            # Invalidate cached empty result before retry
            cache_key = relative_file_path
            self._document_symbols_cache.pop(cache_key, None)

            self.server_ready.wait(timeout=delay)

        return DocumentSymbols([])
