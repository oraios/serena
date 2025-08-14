"""Lean 4 language server implementation."""

import logging
import os
import pathlib
import subprocess
import threading
import time
import tomllib
from typing import Any

from overrides import override

from solidlsp import ls_types
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_handler import LanguageServerTerminatedException
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import LSPError, ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

# Constants for dependency management
DEFAULT_DEPENDENCY_TIMEOUT = 1800  # 30 minutes
MAX_RESTART_ATTEMPTS = 3
RESTART_COOLDOWN_SECONDS = 5.0
DEPENDENCY_CHECK_TIMEOUT = 2.0


class Lean4LanguageServer(SolidLanguageServer):
    """
    Language server implementation for Lean 4 using the built-in lean-language-server.

    Features:
    - Automatic Lake project detection and configuration
    - Background mathlib dependency downloads without blocking LSP
    - Intelligent server command selection (lake serve vs lean --server)
    - Automatic crash recovery and health monitoring
    - Cross-file symbol navigation and reference finding

    Supported project types:
    - Lake projects with/without dependencies
    - Single .lean files
    - Mathlib-based mathematical projects
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # Ignore build outputs and Lake's dependency directories
        return super().is_ignored_dirname(dirname) or dirname in [
            "build",
            "lake-packages",  # Lake dependencies
            ".lake",  # Lake cache
            "_target",  # Old build directory name
        ]

    @staticmethod
    def _get_lean_version():
        """Get installed Lean 4 version."""
        try:
            result = subprocess.run(["lean", "--version"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        return None

    @staticmethod
    def _get_elan_version():
        """Check if elan (Lean version manager) is installed."""
        try:
            result = subprocess.run(["elan", "--version"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        return None

    @staticmethod
    def _setup_runtime_dependency():
        """Verify Lean 4 is installed."""
        elan_version = Lean4LanguageServer._get_elan_version()
        lean_version = Lean4LanguageServer._get_lean_version()

        if not lean_version:
            if not elan_version:
                raise RuntimeError(
                    "Lean 4 is not installed. Please install Lean 4 via elan:\n"
                    "curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh"
                )
            raise RuntimeError("Elan is installed but Lean is not available. Please run: elan install stable")

        return True

    @staticmethod
    def _check_dependencies_available(repo_path: str) -> bool:
        """Check if Lake dependencies are already downloaded and built."""
        # First check if there are any external dependencies at all
        if not Lean4LanguageServer._has_external_dependencies(repo_path):
            # No external dependencies needed, consider ready
            return True

        lake_packages_dir = os.path.join(repo_path, "lake-packages")
        build_dir = os.path.join(repo_path, "build")

        # Check if lake-packages directory exists and has content
        if os.path.exists(lake_packages_dir):
            # Check if it's not empty
            try:
                entries = os.listdir(lake_packages_dir)
                if entries:
                    # Check if build directory also exists (indicates successful build)
                    return os.path.exists(build_dir) and os.listdir(build_dir)
            except OSError:
                pass

        return False

    @staticmethod
    def _has_external_dependencies(repo_path: str) -> bool:
        """Check if the lakefile declares any external dependencies (require statements)."""
        lakefile_lean = os.path.join(repo_path, "lakefile.lean")
        lakefile_toml = os.path.join(repo_path, "lakefile.toml")

        lean_exists = os.path.exists(lakefile_lean)
        toml_exists = os.path.exists(lakefile_toml)

        if lean_exists and toml_exists:
            # Both formats exist - this is a configuration error
            raise RuntimeError(
                f"Conflicting lakefile formats found in {repo_path}. Please use either lakefile.lean OR lakefile.toml, not both."
            )

        # Prefer lakefile.toml (newer format) over lakefile.lean
        if toml_exists:
            return Lean4LanguageServer._check_toml_lakefile_dependencies(lakefile_toml)
        elif lean_exists:
            return Lean4LanguageServer._check_lean_lakefile_dependencies(lakefile_lean)

        # No lakefile found - no dependencies
        return False

    @staticmethod
    def _check_lean_lakefile_dependencies(lakefile_path: str) -> bool:
        """Check lakefile.lean for dependencies."""
        try:
            with open(lakefile_path, encoding="utf-8") as f:
                content = f.read()
                # Look for 'require' statements which indicate external dependencies
                lines = content.split("\n")
                for line in lines:
                    line = line.strip()
                    if line.startswith("require "):
                        return True
                    if "require " in line and not line.startswith("--"):
                        return True
                return False
        except (OSError, UnicodeDecodeError):
            # If we can't read the file due to permissions, I/O, or encoding issues,
            # assume there might be dependencies for safety
            return True
        except Exception:
            # Unexpected error - assume dependencies exist for safety
            return True

    @staticmethod
    def _check_toml_lakefile_dependencies(lakefile_path: str) -> bool:
        """Check lakefile.toml for dependencies using proper TOML parsing."""
        try:
            with open(lakefile_path, "rb") as f:
                data = tomllib.load(f)
                # Check for 'require' key which contains dependency declarations
                return "require" in data and len(data["require"]) > 0
        except tomllib.TOMLDecodeError as e:
            # TOML parsing failed - this is a hard error that should be reported
            raise RuntimeError(f"Invalid TOML syntax in {lakefile_path}: {e}") from e
        except (OSError, FileNotFoundError) as e:
            # File access issues - this is also a hard error
            raise RuntimeError(f"Cannot read lakefile.toml at {lakefile_path}: {e}") from e

    def _ensure_dependencies_async(self, repo_path: str, logger) -> threading.Thread:
        """Start downloading/building dependencies in the background."""

        def download_dependencies():
            logger.log("Starting Lake dependency download in background...", logging.INFO)
            try:
                # Use lake update to fetch dependencies
                result = subprocess.run(
                    ["lake", "update"],
                    check=False,
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=self._dependency_timeout,
                )

                if result.returncode == 0:
                    logger.log("Lake dependencies downloaded successfully", logging.INFO)

                    # Now build the dependencies
                    logger.log("Building Lake dependencies...", logging.INFO)
                    build_result = subprocess.run(
                        ["lake", "build"],
                        check=False,
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                        timeout=self._dependency_timeout,
                    )

                    if build_result.returncode == 0:
                        logger.log("Lake dependencies built successfully", logging.INFO)
                    else:
                        logger.log(f"Lake build failed: {build_result.stderr}", logging.WARNING)
                else:
                    logger.log(f"Lake update failed: {result.stderr}", logging.WARNING)

            except subprocess.TimeoutExpired:
                logger.log(f"Lake dependency download/build timed out after {self._dependency_timeout}s", logging.ERROR)
            except FileNotFoundError:
                logger.log("Lake command not found. Ensure Lake is installed and in PATH.", logging.ERROR)
            except OSError as e:
                logger.log(f"OS error during dependency download: {e}", logging.ERROR)
            except Exception as e:
                logger.log(f"Unexpected error downloading dependencies: {e}", logging.ERROR)

        # Use thread-safe access to manage the dependency thread
        with self._dependency_lock:
            thread = threading.Thread(target=download_dependencies, daemon=True)
            thread.start()
            self._dependency_thread = thread
            return thread

    def _check_and_upgrade_server(self) -> None:
        """Check if dependencies are ready and upgrade to lake serve if needed."""
        with self._dependency_lock:
            if self._dependency_thread and self._dependency_thread.is_alive():
                # Dependencies still downloading
                return

            lakefile_path = os.path.join(self.repository_root_path, "lakefile.lean")
            if os.path.exists(lakefile_path) and self._check_dependencies_available(self.repository_root_path):
                # Dependencies are now ready, check if we need to upgrade
                current_cmd = getattr(self, "_current_command", "")
                if current_cmd != "lake serve --":
                    self.logger.log("Dependencies ready, upgrading to lake serve", logging.INFO)
                    try:
                        # Restart server with lake serve
                        self._restart_server_with_command("lake serve --")
                        self._dependencies_ready.set()
                    except Exception as e:
                        self.logger.log(f"Failed to upgrade to lake serve: {e}", logging.WARNING)

    def _restart_server_with_command(self, new_command: str) -> None:
        """Restart the server with a new command."""
        self.logger.log(f"Restarting server with command: {new_command}", logging.INFO)

        # Stop current server
        if self.server:
            try:
                self.stop()
            except Exception as e:
                self.logger.log(f"Error stopping server for upgrade: {e}", logging.WARNING)

        # Update command and restart
        self._current_command = new_command
        self.process_launch_info.cmd = new_command
        self.server_ready.clear()
        self._start_server()

    def get_dependency_status(self) -> dict[str, Any]:
        """Get current status of dependency downloads."""
        lakefile_lean = os.path.join(self.repository_root_path, "lakefile.lean")
        lakefile_toml = os.path.join(self.repository_root_path, "lakefile.toml")

        lean_exists = os.path.exists(lakefile_lean)
        toml_exists = os.path.exists(lakefile_toml)

        if lean_exists and toml_exists:
            # Both formats exist - this is a configuration error
            raise RuntimeError(
                f"Conflicting lakefile formats found in {self.repository_root_path}. "
                "Please use either lakefile.lean OR lakefile.toml, not both."
            )

        has_lakefile = lean_exists or toml_exists

        if not has_lakefile:
            return {"has_dependencies": False, "status": "no_dependencies"}

        # Determine which format is being used for logging
        lakefile_format = "lakefile.toml" if toml_exists else "lakefile.lean"

        if self._dependencies_ready.is_set():
            return {"has_dependencies": True, "status": "ready", "format": lakefile_format}

        # Use lock to prevent race condition with thread access
        with self._dependency_lock:
            if self._dependency_thread and self._dependency_thread.is_alive():
                return {"has_dependencies": True, "status": "downloading", "format": lakefile_format}

        if self._check_dependencies_available(self.repository_root_path):
            self._dependencies_ready.set()  # Update the flag
            return {"has_dependencies": True, "status": "ready", "format": lakefile_format}

        return {"has_dependencies": True, "status": "pending", "format": lakefile_format}

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        self._setup_runtime_dependency()

        # Store logger reference early so we can use it
        self.logger = logger

        # Initialize instance variables using configurable settings
        self._restart_count = 0
        self._max_restart_attempts = solidlsp_settings.lean4_max_restart_attempts
        self._last_restart_time = 0.0
        self._restart_cooldown = solidlsp_settings.lean4_restart_cooldown_seconds
        self._dependency_timeout = solidlsp_settings.lean4_dependency_timeout
        self._health_check_timeout = solidlsp_settings.lean4_health_check_timeout

        # Thread-safe state management
        self._dependency_lock = threading.RLock()  # Reentrant lock for nested access
        self._dependency_thread = None
        self._dependencies_ready = threading.Event()

        # Lean 4 language server is started with 'lake serve --'
        # or 'lean --server' for single file mode
        cmd = self._determine_server_command(repository_root_path)
        self._current_command = cmd

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=cmd, cwd=repository_root_path),
            "lean4",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.request_id = 0

    def _determine_server_command(self, repo_path: str) -> str:
        """Determine the appropriate command to start the language server."""
        lakefile_lean = os.path.join(repo_path, "lakefile.lean")
        lakefile_toml = os.path.join(repo_path, "lakefile.toml")

        lean_exists = os.path.exists(lakefile_lean)
        toml_exists = os.path.exists(lakefile_toml)

        if lean_exists and toml_exists:
            # Both formats exist - this is a configuration error
            raise RuntimeError(
                f"Conflicting lakefile formats found in {repo_path}. Please use either lakefile.lean OR lakefile.toml, not both."
            )

        is_lake_project = lean_exists or toml_exists

        if is_lake_project:
            lakefile_type = "lakefile.toml" if toml_exists else "lakefile.lean"
            self.logger.log(f"Detected Lake project with {lakefile_type}", logging.INFO)

            # Check if dependencies are available
            if self._check_dependencies_available(repo_path):
                self.logger.log("Lake dependencies are available", logging.INFO)
                self._dependencies_ready.set()
                return "lake serve --"
            else:
                self.logger.log("Lake dependencies not found, starting background download...", logging.INFO)
                # Start dependency download in background
                self._dependency_thread = self._ensure_dependencies_async(repo_path, self.logger)

                # For now, start with lean --server as fallback to avoid blocking
                # We can upgrade to lake serve later when dependencies are ready
                self.logger.log("Using lean --server as fallback until dependencies are ready", logging.INFO)
                return "lean --server"
        else:
            # Single file mode
            self.logger.log("No lakefile found, using single file mode", logging.INFO)
            self._dependencies_ready.set()  # No dependencies needed for single files
            return "lean --server"

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Lean 4 Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True},
                },
                "workspace": {"workspaceFolders": True, "didChangeConfiguration": {"dynamicRegistration": True}},
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
        return initialize_params

    def _start_server(self):
        """Start Lean 4 language server process"""

        def register_capability_handler(params):
            self.logger.log(f"LSP: client/registerCapability: {params}", logging.DEBUG)
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        def do_nothing(params):
            return

        def server_initialized(params):
            self.logger.log("LSP: Lean 4 server initialized notification received", logging.INFO)
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("initialized", server_initialized)

        self.logger.log("Starting Lean 4 server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)

        self.logger.log(f"Lean 4 server capabilities: {init_response.get('capabilities', {})}", logging.INFO)

        # Verify server capabilities
        capabilities = init_response.get("capabilities", {})
        if not capabilities.get("definitionProvider"):
            self.logger.log("WARNING: Lean 4 server does not provide definition capability", logging.WARNING)
        if not capabilities.get("referencesProvider"):
            self.logger.log("WARNING: Lean 4 server does not provide references capability", logging.WARNING)

        self.server.notify.initialized({})
        self.completions_available.set()

        # Lean 4 server is typically ready immediately after initialization
        self.server_ready.set()
        self.server_ready.wait()
        self._restart_count = 0  # Reset restart count on successful start

    def _check_server_health(self) -> bool:
        """Check if the language server process is still running and responsive."""
        try:
            # Check if process is alive
            if not self.server or not self.server.is_running():
                self.logger.log("Language server process is not running", logging.WARNING)
                return False

            # Try a simple request to verify responsiveness
            # We'll use a simple hover request which should return quickly
            test_file = os.path.join(self.repository_root_path, "lakefile.lean")
            if os.path.exists(test_file):
                try:
                    # Send a hover request with a short timeout
                    original_timeout = getattr(self.server, "_request_timeout", None)
                    self.server.set_request_timeout(DEPENDENCY_CHECK_TIMEOUT)

                    self.server.send.hover(
                        {"textDocument": {"uri": pathlib.Path(test_file).as_uri()}, "position": {"line": 0, "character": 0}}
                    )

                    # Restore original timeout
                    if original_timeout is not None:
                        self.server.set_request_timeout(original_timeout)

                    return True
                except (LSPError, LanguageServerTerminatedException, Exception) as e:
                    self.logger.log(f"Health check failed: {e}", logging.WARNING)
                    return False

            # If no test file, assume healthy if process is running
            return True

        except Exception as e:
            self.logger.log(f"Error checking server health: {e}", logging.ERROR)
            return False

    def _should_attempt_restart(self) -> bool:
        """Check if we should attempt to restart the server."""
        current_time = time.time()

        # Check cooldown period
        if current_time - self._last_restart_time < self._restart_cooldown:
            self.logger.log(
                f"Restart cooldown in effect. Wait {self._restart_cooldown - (current_time - self._last_restart_time):.1f}s", logging.INFO
            )
            return False

        # Check restart limit
        if self._restart_count >= self._max_restart_attempts:
            self.logger.log(f"Maximum restart attempts ({self._max_restart_attempts}) reached", logging.ERROR)
            return False

        return True

    def _restart_server(self) -> None:
        """Attempt to restart the language server after a crash."""
        if not self._should_attempt_restart():
            raise RuntimeError("Cannot restart server: cooldown period or max attempts reached")

        self.logger.log("Attempting to restart Lean 4 language server...", logging.INFO)
        self._restart_count += 1
        self._last_restart_time = time.time()

        try:
            # Stop the current server if it's still running
            if self.server:
                try:
                    self.stop()
                except Exception as e:
                    self.logger.log(f"Error stopping server: {e}", logging.WARNING)

            # Clear the ready event
            self.server_ready.clear()

            # Start the server again
            self._start_server()

            self.logger.log("Lean 4 language server restarted successfully", logging.INFO)

        except Exception as e:
            self.logger.log(f"Failed to restart server: {e}", logging.ERROR)
            raise

    def _handle_request_with_recovery(self, request_fn: Any, *args: Any, **kwargs: Any) -> Any:
        """
        Execute a request with automatic recovery on server crash.

        :param request_fn: The request function to execute
        :param args: Positional arguments for the request
        :param kwargs: Keyword arguments for the request
        :return: The result of the request
        """
        # Check if we can upgrade the server first
        self._check_and_upgrade_server()

        try:
            return request_fn(*args, **kwargs)
        except LanguageServerTerminatedException as e:
            self.logger.log(f"Language server terminated during request: {e}", logging.ERROR)

            # Attempt to restart
            if self._should_attempt_restart():
                try:
                    self._restart_server()
                    # Retry the request once after restart
                    self.logger.log("Retrying request after server restart...", logging.INFO)
                    return request_fn(*args, **kwargs)
                except (LanguageServerTerminatedException, RuntimeError, OSError) as retry_error:
                    self.logger.log(f"Request failed after restart: {retry_error}", logging.ERROR)
                    raise
            else:
                raise
        except (LSPError, TimeoutError, ConnectionError, BrokenPipeError) as lsp_error:
            # Handle specific LSP communication errors
            self.logger.log(f"LSP communication error: {lsp_error}", logging.WARNING)
            if not self._check_server_health():
                self.logger.log("Server health check failed after LSP error", logging.WARNING)
                # Server might be in bad state, consider restart
                if self._should_attempt_restart():
                    try:
                        self._restart_server()
                        # Retry the request
                        return request_fn(*args, **kwargs)
                    except (LanguageServerTerminatedException, RuntimeError, OSError) as restart_error:
                        self.logger.log(f"Server restart failed: {restart_error}", logging.ERROR)
                        # Fall through to re-raise original error
            raise

    # Override request methods to add recovery capabilities
    @override
    def request_definition(self, relative_file_path: str, line: int, column: int) -> list[dict[str, Any]]:
        """Request definition with automatic recovery on server crash."""
        return self._handle_request_with_recovery(super().request_definition, relative_file_path, line, column)

    @override
    def request_references(self, relative_file_path: str, line: int, column: int) -> list[dict[str, Any]]:
        """Request references with automatic recovery on server crash."""
        return self._handle_request_with_recovery(super().request_references, relative_file_path, line, column)

    @override
    def request_document_symbols(
        self, relative_file_path: str, include_body: bool = False
    ) -> tuple[list[ls_types.UnifiedSymbolInformation], list[ls_types.UnifiedSymbolInformation]]:
        """Request document symbols with automatic recovery on server crash."""
        return self._handle_request_with_recovery(super().request_document_symbols, relative_file_path, include_body)

    @override
    def request_hover(self, relative_file_path: str, line: int, column: int) -> dict[str, Any] | None:
        """Request hover with automatic recovery on server crash."""
        return self._handle_request_with_recovery(super().request_hover, relative_file_path, line, column)

    @override
    def request_completions(
        self, relative_file_path: str, line: int, column: int, allow_incomplete: bool = False
    ) -> list[ls_types.CompletionItem]:
        """Request completions with automatic recovery on server crash."""
        return self._handle_request_with_recovery(super().request_completions, relative_file_path, line, column, allow_incomplete)
