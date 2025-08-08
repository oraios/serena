"""Erlang Language Server implementation using Erlang LS."""

import logging
import shutil
import subprocess
import threading
import time

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


class ErlangLanguageServer(SolidLanguageServer):
    """Language server for Erlang using Erlang LS."""

    def __init__(
        self,
        config: LanguageServerConfig,
        logger: LanguageServerLogger,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
    ):
        """
        Creates an ErlangLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        self.erlang_ls_path = shutil.which("erlang_ls")
        if not self.erlang_ls_path:
            raise RuntimeError("Erlang LS not found. Install from: https://github.com/erlang-ls/erlang_ls")

        if not self._check_erlang_installation():
            raise RuntimeError("Erlang/OTP not found. Install from: https://www.erlang.org/downloads")

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=[self.erlang_ls_path, "--transport", "stdio"], cwd=repository_root_path),
            "erlang",
            solidlsp_settings,
        )

        # Add server readiness tracking like Elixir
        self.server_ready = threading.Event()

        # Set generous timeout for Erlang LS initialization
        self.set_request_timeout(120.0)

    def _check_erlang_installation(self) -> bool:
        """Check if Erlang/OTP is available."""
        try:
            result = subprocess.run(["erl", "-version"], check=False, capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    @classmethod
    def _get_erlang_version(cls):
        """Get the installed Erlang/OTP version or None if not found."""
        try:
            result = subprocess.run(["erl", "-version"], check=False, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return result.stderr.strip()  # erl -version outputs to stderr
        except (subprocess.SubprocessError, FileNotFoundError):
            return None
        return None

    @classmethod
    def _check_rebar3_available(cls) -> bool:
        """Check if rebar3 build tool is available."""
        try:
            result = subprocess.run(["rebar3", "version"], check=False, capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def _start_server(self):
        """Start Erlang LS server process with proper initialization waiting."""

        def register_capability_handler(params):
            return

        def window_log_message(msg):
            """Handle window/logMessage notifications from Erlang LS"""
            message_text = msg.get("message", "")
            self.logger.log(f"LSP: window/logMessage: {message_text}", logging.INFO)

            # Look for Erlang LS readiness signals
            # Common patterns: "Started Erlang LS", "initialized", "ready"
            readiness_signals = [
                "Started Erlang LS",
                "server started",
                "initialized",
                "ready to serve requests",
                "compilation finished",
                "indexing complete",
            ]

            message_lower = message_text.lower()
            for signal in readiness_signals:
                if signal.lower() in message_lower:
                    self.logger.log(f"Erlang LS readiness signal detected: {message_text}", logging.INFO)
                    self.server_ready.set()
                    break

        def do_nothing(params):
            return

        def check_server_ready(params):
            """Handle $/progress notifications from Erlang LS as fallback."""
            value = params.get("value", {})

            # Check for initialization completion progress
            if value.get("kind") == "end":
                message = value.get("message", "")
                if any(word in message.lower() for word in ["initialized", "ready", "complete"]):
                    self.logger.log("Erlang LS initialization progress completed", logging.INFO)
                    # Set as fallback if no window/logMessage was received
                    if not self.server_ready.is_set():
                        self.server_ready.set()

        # Set up notification handlers
        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", check_server_ready)
        self.server.on_notification("window/workDoneProgress/create", do_nothing)
        self.server.on_notification("$/workDoneProgress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting Erlang LS server process", logging.INFO)
        self.server.start()

        # Send initialize request
        initialize_params = {
            "processId": None,
            "rootPath": self.repository_root_path,
            "rootUri": f"file://{self.repository_root_path}",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True},
                    "completion": {"dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {"dynamicRegistration": True},
                    "hover": {"dynamicRegistration": True},
                }
            },
        }

        self.logger.log("Sending initialize request to Erlang LS", logging.INFO)
        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        if "capabilities" in init_response:
            self.logger.log(f"Erlang LS capabilities: {list(init_response['capabilities'].keys())}", logging.INFO)

        self.server.notify.initialized({})
        self.completions_available.set()

        # Wait for Erlang LS to be ready
        ready_timeout = 60.0  # Erlang LS is typically faster than Next LS
        self.logger.log(f"Waiting up to {ready_timeout} seconds for Erlang LS readiness...", logging.INFO)

        if self.server_ready.wait(timeout=ready_timeout):
            self.logger.log("Erlang LS is ready and available for requests", logging.INFO)

            # Add settling period for indexing
            settling_time = 5.0  # Shorter than Elixir since Erlang LS is typically faster
            self.logger.log(f"Allowing {settling_time} seconds for Erlang LS indexing to complete...", logging.INFO)
            time.sleep(settling_time)
            self.logger.log("Erlang LS settling period complete", logging.INFO)
        else:
            # Set ready anyway and continue - Erlang LS might not send explicit ready messages
            self.logger.log("Erlang LS readiness timeout reached, proceeding anyway", logging.WARNING)
            self.server_ready.set()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For Erlang projects, we should ignore:
        # - _build: rebar3 build artifacts
        # - deps: dependencies
        # - ebin: compiled beam files
        # - .rebar3: rebar3 cache
        # - logs: log files
        # - node_modules: if the project has JavaScript components
        return super().is_ignored_dirname(dirname) or dirname in [
            "_build",
            "deps",
            "ebin",
            ".rebar3",
            "logs",
            "node_modules",
            "_checkouts",
            "cover",
        ]

    def is_ignored_filename(self, filename: str) -> bool:
        """Check if a filename should be ignored."""
        # Ignore compiled BEAM files
        if filename.endswith(".beam"):
            return True
        # Don't ignore Erlang source files, header files, or configuration files
        return False
