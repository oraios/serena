"""
Provides Nim specific instantiation of the LanguageServer class using nimlangserver.
Contains various configurations and settings specific to Nim language.
"""

import logging
import os
import pathlib
import shutil
import threading

from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_handler import SolidLanguageServerHandler
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


class NimLanguageServerHandler(SolidLanguageServerHandler):
    """Custom handler for nimlangserver that only sends Content-Length header."""

    def _send_payload(self, payload):
        """Override to send only Content-Length header for nimlangserver compatibility."""
        if not self.process or not self.process.stdin:
            return
        self._log(payload)

        # Create simplified message for nimlangserver (only Content-Length header)
        import json
        body = json.dumps(payload, check_circular=False, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")

        # Use lock to prevent concurrent writes
        with self._stdin_lock:
            try:
                # Write as single operation
                self.process.stdin.write(header + body)
                self.process.stdin.flush()
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                if self.logger:
                    self.logger("client", "logger", f"Failed to write to stdin: {e}")
                return

    def _read_ls_process_stderr(self) -> None:
        """Override stderr reader to properly parse Nim language server log levels."""
        import logging
        log = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")
        ENCODING = "utf-8"

        # Track nimsuggest errors to prevent endless restarts
        error_count = 0
        max_errors = 10

        try:
            while self.process and self.process.stderr:
                if self.process.poll() is not None:
                    # process has terminated
                    break
                line = self.process.stderr.readline()
                if not line:
                    continue
                line_decoded = line.decode(ENCODING, errors="replace").rstrip()

                # Skip empty lines
                if not line_decoded.strip():
                    continue

                # Parse Nim language server log level prefixes
                # The format is typically "DBG Message text  key=value"
                if line_decoded.startswith("DBG ") or "DBG " in line_decoded[:20]:
                    level = logging.DEBUG
                    # For DEBUG messages, we'll still log them as INFO to avoid clutter
                    level = logging.INFO
                elif line_decoded.startswith("INF ") or "INF " in line_decoded[:20]:
                    level = logging.INFO
                elif line_decoded.startswith("WRN ") or "WRN " in line_decoded[:20]:
                    level = logging.WARNING
                    # Check for specific warnings that are really errors
                    if "Server stopped" in line_decoded:
                        error_count += 1
                elif line_decoded.startswith("ERR ") or "ERR " in line_decoded[:20]:
                    level = logging.ERROR
                    error_count += 1

                    # Track specific error types
                    if "Failed to parse nimsuggest port" in line_decoded:
                        # This is a critical error that needs special handling
                        log.error("Nimsuggest port parsing failed - server may need restart")
                    elif "cannot open:" in line_decoded and ".svg" in line_decoded:
                        # SVG file missing is not critical, just log it
                        log.warning("Missing SVG resource (non-critical): %s", line_decoded)
                        level = logging.WARNING
                        error_count -= 1  # Don't count this as a critical error
                    elif "cannot open:" in line_decoded:
                        # Other file missing errors might be critical
                        log.error("Missing file error: %s", line_decoded)
                else:
                    # Default to INFO for unrecognized format
                    level = logging.INFO

                # Check if we've hit too many errors
                if error_count >= max_errors:
                    log.error("Too many nimsuggest errors (%d), stopping error recovery", error_count)
                    # Signal that the server should be restarted externally
                    break

                log.log(level, line_decoded)
        except Exception as e:
            log.error("Error while reading stderr from Nim language server process: %s", e, exc_info=e)
        if not self._is_shutting_down:
            if error_count >= max_errors:
                log.error("Nim language server terminated due to excessive errors")
            else:
                log.error("Nim language server stderr reader thread terminated unexpectedly")
        else:
            log.info("Nim language server stderr reader thread has terminated")


class NimLanguageServer(SolidLanguageServer):
    """
    Provides Nim specific instantiation of the LanguageServer class using nimlangserver.
    Contains various configurations and settings specific to Nim language.
    """

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        """
        Creates a NimLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        nim_lsp_executable_path = self._setup_runtime_dependencies(logger, solidlsp_settings)

        # Ensure nimble bin is in PATH for nimsuggest
        nimble_bin = os.path.expanduser("~/.nimble/bin")
        env = os.environ.copy()
        if nimble_bin not in env.get("PATH", "").split(os.pathsep):
            env["PATH"] = f"{nimble_bin}{os.pathsep}{env.get('PATH', '')}"

        # Set environment variables to help nimsuggest work better
        env["NIM_SILENT"] = "true"  # Reduce nimsuggest verbosity
        env["NIMSUGEST_RESTART_LIMIT"] = "5"  # Limit restart attempts

        # Initialize server_ready before parent class initialization
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=nim_lsp_executable_path, cwd=repository_root_path, env=env),
            "nim",
            solidlsp_settings,
        )

        # Override with custom handler for nimlangserver after parent initialization
        # First stop the default handler if it's already running
        if hasattr(self, 'server') and self.server and hasattr(self.server, 'process'):
            if self.server.process and self.server.process.poll() is None:
                self.server.stop()

        self._setup_custom_handler(repository_root_path, ProcessLaunchInfo(cmd=nim_lsp_executable_path, cwd=repository_root_path, env=env))

    def _setup_custom_handler(self, repository_root_path: str, process_launch_info: ProcessLaunchInfo):
        """Setup custom handler for nimlangserver."""
        # Store repository path for potential use
        self._repo_path = repository_root_path

        def logging_fn(_, level, message):
            # Convert dict messages to string
            if isinstance(message, dict):
                import json
                message = json.dumps(message, indent=2)
            # Map the log level
            if level == "logger":
                self.logger.log(message, logging.DEBUG)
            elif level == "error":
                self.logger.log(message, logging.ERROR)
            else:
                self.logger.log(message, logging.INFO)

        # Replace with custom handler
        self.server = NimLanguageServerHandler(
            process_launch_info,
            logger=logging_fn,
        )

    def _create_nim_config_if_needed(self):
        """Create a basic nim.cfg file if it doesn't exist to help nimsuggest work better."""
        try:
            nim_cfg_path = os.path.join(self.repository_root_path, "nim.cfg")
            if not os.path.exists(nim_cfg_path):
                # Check if there's a .nimble file to determine project name
                nimble_files = list(pathlib.Path(self.repository_root_path).glob("*.nimble"))
                if nimble_files:
                    # Create a minimal nim.cfg that helps nimsuggest
                    with open(nim_cfg_path, "w") as f:
                        f.write("# Auto-generated nim.cfg for better nimsuggest support\n")
                        f.write("--hints:off\n")  # Reduce verbosity
                        f.write("--warnings:off\n")  # Focus on errors only
                        f.write("--verbosity:0\n")  # Minimal output
                    self.logger.log(f"Created nim.cfg to improve nimsuggest stability", logging.INFO)
        except Exception as e:
            self.logger.log(f"Could not create nim.cfg: {e}", logging.DEBUG)

    @classmethod
    def _setup_runtime_dependencies(cls, logger: LanguageServerLogger, solidlsp_settings: SolidLSPSettings) -> str:
        """
        Setup runtime dependencies for Nim Language Server and return the command to start the server.
        """
        # Store settings for later use if needed
        cls._solidlsp_settings = solidlsp_settings

        # First check if nimlangserver is already installed via nimble
        nimble_bin = os.path.expanduser("~/.nimble/bin")
        nimlangserver_path = os.path.join(nimble_bin, "nimlangserver")

        if os.path.exists(nimlangserver_path):
            logger.log(f"Found nimlangserver at {nimlangserver_path}", logging.INFO)
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

        # Install nimlangserver via nimble using RuntimeDependency
        logger.log("Installing nimlangserver via nimble", logging.INFO)

        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="nimlangserver",
                    description="Nim Language Server",
                    command=["nimble", "install", "nimlangserver", "-y"],
                    platform_id=None,  # Works on all platforms with nimble
                )
            ]
        )

        try:
            # Install to nimble's default location
            deps.install(logger, nimble_bin)
        except Exception as e:
            raise RuntimeError(
                f"Failed to install nimlangserver via nimble: {e}\n"
                "Please try installing manually with: nimble install nimlangserver"
            )

        # Check if nimlangserver was successfully installed
        nimlangserver_path = os.path.join(nimble_bin, "nimlangserver")
        if os.path.exists(nimlangserver_path):
            logger.log(f"Successfully installed nimlangserver at {nimlangserver_path}", logging.INFO)
            return nimlangserver_path

        # Try to find it in PATH as well
        nimlangserver_in_path = shutil.which("nimlangserver")
        if nimlangserver_in_path:
            logger.log(f"Found nimlangserver in PATH at {nimlangserver_in_path}", logging.INFO)
            return nimlangserver_in_path

        raise RuntimeError(
            "nimlangserver installation appeared to succeed but the binary was not found.\n"
            "Please verify installation with: nimble list -i | grep nimlangserver"
        )

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Nim Language Server.
        """
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
            "initializationOptions": {},
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }
        return InitializeParams(**initialize_params)

    def _start_server(self):
        """
        Starts the Nim Language Server, waits for the server to be ready and yields the LanguageServer instance.
        """
        # Try to create a nim.cfg if needed to improve nimsuggest stability
        self._create_nim_config_if_needed()

        def register_capability_handler(params):
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
            return

        def execute_client_command_handler(_):
            return []

        def do_nothing(_):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)
            # Check for nimlangserver ready signals
            message_text = msg.get("message", "")
            if "initialized" in message_text.lower() or "ready" in message_text.lower():
                self.logger.log("Nim language server ready signal detected", logging.INFO)
                self.server_ready.set()
                self.completions_available.set()

        def window_show_message(msg):
            self.logger.log(f"LSP: window/showMessage: {msg}", logging.INFO)
            # Check for nimlangserver ready signals
            message_text = msg.get("message", "")
            msg_type = msg.get("type", 3)  # 1=error, 2=warning, 3=info, 4=log

            # Handle error messages specially
            if msg_type == 1:  # Error
                if "cannot open:" in message_text and ".svg" in message_text:
                    # SVG file missing is non-critical
                    self.logger.log(f"Non-critical resource missing: {message_text}", logging.WARNING)
                elif "Failed to parse nimsuggest port" in message_text:
                    self.logger.log(f"Nimsuggest port parsing failed: {message_text}", logging.ERROR)
                    # Don't mark server as ready if there are critical errors
                    return
                else:
                    self.logger.log(f"Nim server error: {message_text}", logging.ERROR)
            elif "initialized" in message_text.lower() or "ready" in message_text.lower():
                self.logger.log("Nim language server ready signal detected from showMessage", logging.INFO)
                self.server_ready.set()
                self.completions_available.set()

        def workspace_configuration_handler(params):
            """Handle workspace/configuration requests - nimlangserver expects an array."""
            items = params.get("items", [])
            # Return null for each configuration item requested
            # nimlangserver expects an array containing null or objects
            return [None for _ in items]

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("window/showMessage", window_show_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_request("workspace/configuration", workspace_configuration_handler)
        def extension_status_update(params):
            """Handle Nim-specific status updates which include nimsuggest instance info."""
            if "projectErrors" in params:
                errors = params["projectErrors"]
                for error in errors:
                    error_msg = error.get("errorMessage", "")
                    project_file = error.get("projectFile", "")

                    # Log non-critical errors at warning level
                    if "cannot open:" in error_msg and (".svg" in error_msg or ".png" in error_msg or ".ico" in error_msg):
                        self.logger.log(f"Non-critical resource missing in {project_file}: {error_msg}", logging.WARNING)
                    elif "Failed to parse nimsuggest port" in error_msg:
                        self.logger.log(f"Nimsuggest port issue for {project_file}: {error_msg}", logging.ERROR)
                    else:
                        self.logger.log(f"Project error in {project_file}: {error_msg}", logging.ERROR)

            # Check if nimsuggest instances are running
            if "nimsuggestInstances" in params:
                instances = params["nimsuggestInstances"]
                for instance in instances:
                    port = instance.get("port", 0)
                    project = instance.get("projectFile", "")
                    if port > 0:
                        self.logger.log(f"Nimsuggest instance running for {project} on port {port}", logging.DEBUG)
                        # Server is likely ready if we have active instances
                        if not self.server_ready.is_set():
                            self.server_ready.set()
                            self.completions_available.set()

        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("extension/statusUpdate", extension_status_update)  # Nim-specific status updates

        self.logger.log("Starting Nim server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)
        self.logger.log(f"Received initialize response from Nim server: {init_response}", logging.DEBUG)

        # Check capabilities if present
        if init_response and "capabilities" in init_response:
            capabilities = init_response["capabilities"]
            if "textDocumentSync" in capabilities:
                sync_value = capabilities["textDocumentSync"]
                # Handle both simple integer and complex object forms
                if isinstance(sync_value, int):
                    assert sync_value in [0, 1, 2]  # None, Full or Incremental
        else:
            self.logger.log("No capabilities in initialize response", logging.WARNING)
            capabilities = {}

        # Log available capabilities
        if "completionProvider" in capabilities:
            self.logger.log("Nim server supports completion", logging.INFO)

        if "documentSymbolProvider" in capabilities:
            self.logger.log("Nim server supports document symbols", logging.INFO)

        if "definitionProvider" in capabilities:
            self.logger.log("Nim server supports goto definition", logging.INFO)

        if "referencesProvider" in capabilities:
            self.logger.log("Nim server supports find references", logging.INFO)

        self.server.notify.initialized({})

        # Wait for server readiness with timeout
        self.logger.log("Waiting for Nim language server to be ready...", logging.INFO)
        if not self.server_ready.wait(timeout=15.0):  # Increased timeout for Nim server with complex projects
            # Try a simple operation to check if server is actually working
            try:
                # Try to get symbols from a simple test file to verify server is functional
                test_response = self.server.send.workspace_symbol({"query": ""})
                if test_response is not None:
                    self.logger.log("Nim server responded to test query, marking as ready", logging.INFO)
                    self.server_ready.set()
                    self.completions_available.set()
                else:
                    self.logger.log("Nim server not responding, may need manual restart", logging.WARNING)
                    # Still set as ready to allow operations to proceed
                    self.server_ready.set()
                    self.completions_available.set()
            except Exception as e:
                self.logger.log(f"Error testing Nim server readiness: {e}", logging.WARNING)
                # Proceed anyway
                self.server_ready.set()
                self.completions_available.set()
        else:
            self.logger.log("Nim server initialization complete", logging.INFO)

    def is_ignored_dirname(self, dirname: str) -> bool:
        """
        A Nim-specific condition for directories that should always be ignored.
        """
        # Ignore common Nim build and cache directories
        ignored_dirs = {".nimcache", "nimcache", "htmldocs", ".git", ".svn", ".hg", "node_modules"}
        return dirname.startswith(".") or dirname in ignored_dirs
