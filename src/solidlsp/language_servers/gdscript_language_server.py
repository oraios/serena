"""
Provides GDScript specific instantiation of the LanguageServer class for Godot Engine.
Contains various configurations and settings specific to GDScript.
"""

import atexit
import logging
import os
import pathlib
import shutil
import socket
import stat
import subprocess
import tempfile
import threading
import time
import signal
from typing import Optional
import concurrent.futures

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import FileUtils, PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency


class GDScriptLanguageServer(SolidLanguageServer):
    """
    Provides GDScript specific instantiation of the LanguageServer class.
    Contains various configurations and settings specific to GDScript for Godot Engine.
    """

    _pid_tracking_lock = threading.Lock()
    _global_tracked_godot_pids: set[int] = set()
    _cleanup_registered = False

    @classmethod
    def _ensure_cleanup_registered(cls) -> None:
        with cls._pid_tracking_lock:
            if not cls._cleanup_registered:
                atexit.register(cls._atexit_cleanup)
                cls._cleanup_registered = True

    @classmethod
    def _atexit_cleanup(cls) -> None:
        try:
            with cls._pid_tracking_lock:
                tracked = list(cls._global_tracked_godot_pids)
            for pid in tracked:
                cls._terminate_pid_tree(pid, logger=None)
        except Exception:
            # Suppress any exceptions during interpreter shutdown
            pass

    @classmethod
    def _terminate_pid_tree(cls, pid: int, logger: LanguageServerLogger | None) -> None:
        try:
            import psutil  # type: ignore[import-not-found]
        except ImportError:
            psutil = None  # type: ignore[assignment]

        if psutil is None:
            try:
                if logger:
                    logger.log(f"Sending SIGTERM to Godot process {pid}", logging.INFO)
                sig = getattr(signal, "SIGTERM", signal.SIGINT)
                os.kill(pid, sig)
            except (OSError, ValueError):
                pass
            finally:
                with cls._pid_tracking_lock:
                    cls._global_tracked_godot_pids.discard(pid)
            return

        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess:
            with cls._pid_tracking_lock:
                cls._global_tracked_godot_pids.discard(pid)
            return
        except psutil.AccessDenied:
            if logger:
                logger.log(f"Access denied when terminating Godot process {pid}", logging.WARNING)
            with cls._pid_tracking_lock:
                cls._global_tracked_godot_pids.discard(pid)
            return

        if logger:
            logger.log(f"Terminating Godot process {pid}", logging.INFO)

        children = proc.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        try:
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        try:
            _, alive = psutil.wait_procs([proc] + children, timeout=5.0)
        except Exception:
            alive = []

        for survivor in alive:
            try:
                if logger:
                    logger.log(f"Force killing Godot process {survivor.pid}", logging.INFO)
                survivor.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        with cls._pid_tracking_lock:
            cls._global_tracked_godot_pids.discard(pid)

    def _track_spawned_godot_process(self, pid: int) -> None:
        if not pid or pid <= 0:
            return
        self._tracked_godot_pids.add(pid)
        with self.__class__._pid_tracking_lock:
            self.__class__._global_tracked_godot_pids.add(pid)
        self.__class__._ensure_cleanup_registered()

    def _untrack_godot_pid(self, pid: int) -> None:
        if not pid or pid <= 0:
            return
        self._tracked_godot_pids.discard(pid)
        with self.__class__._pid_tracking_lock:
            self.__class__._global_tracked_godot_pids.discard(pid)

    @staticmethod
    def _parse_external_endpoint(value: str | None) -> tuple[str, int] | None:
        if not value or not isinstance(value, str):
            return None
        endpoint = value.strip()
        if endpoint.startswith("tcp://"):
            endpoint = endpoint[6:]
        if endpoint.startswith("localhost:"):
            endpoint = endpoint.replace("localhost", "127.0.0.1", 1)
        if ":" not in endpoint:
            return None
        host, port_str = endpoint.rsplit(":", 1)
        host = host.strip() or "127.0.0.1"
        try:
            port = int(port_str.strip())
        except ValueError:
            return None
        return host, port

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For GDScript projects, we should ignore:
        # - .godot: Godot project cache and settings
        # - build: common output directories
        # - node_modules: if the project has JavaScript components
        return super().is_ignored_dirname(dirname) or dirname in [".godot", "build", "dist", "node_modules"]

    @staticmethod
    def _get_godot_version(godot_path: str) -> Optional[str]:
        """Get the installed Godot version or None if not found."""
        try:
            result = subprocess.run([godot_path, "--version"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        return None

    @staticmethod
    def _get_gdscript_lsp_path() -> Optional[str]:
        """Get the path to Godot executable for GDScript language server."""
        # First check for GODOT_PATH environment variable
        godot_env_path = os.environ.get("GODOT_PATH")
        if godot_env_path and pathlib.Path(godot_env_path).exists():
            return godot_env_path

        # Then check if Godot is in PATH
        godot_path = shutil.which("godot")
        if godot_path:
            return godot_path

        # Check common installation locations
        home = pathlib.Path.home()
        possible_paths = [
            home / ".local" / "bin" / "godot",
            home / "AppData" / "Local" / "Godot" / "godot.exe",
            home / ".serena" / "language_servers" / "godot" / "godot.exe",
            pathlib.Path("/usr/local/bin/godot"),
            pathlib.Path("/opt/godot/godot"),
        ]

        # Add platform-specific paths
        if os.name == "nt":  # Windows
            possible_paths.extend([
                pathlib.Path("C:/Program Files/Godot/godot.exe"),
                pathlib.Path("C:/Godot/godot.exe"),
            ])
        else:
            # Add common Unix-like paths that might have Godot
            possible_paths.extend([
                pathlib.Path("/usr/bin/godot"),
                pathlib.Path("/opt/Godot/Godot"),
                pathlib.Path("/Applications/Godot.app/Contents/MacOS/Godot"),  # macOS
            ])

        for path in possible_paths:
            if path.exists():
                return str(path)

        return None

    @classmethod
    def _setup_runtime_dependencies(
        cls, logger: LanguageServerLogger, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings
    ) -> str:
        """
        Setup runtime dependencies for GDScript Language Server.
        Downloads the Godot binary for the current platform if not found locally and returns the path to the executable.
        """
        # First check for a custom Godot path in language-specific settings
        godot_path = None
        settings_map = solidlsp_settings.ls_specific_settings or {}
        gdscript_settings = None
        if Language.GDSCRIPT in settings_map:
            gdscript_settings = settings_map[Language.GDSCRIPT]
        else:
            for key in ("gdscript", "GDSCRIPT"):
                if key in settings_map:
                    gdscript_settings = settings_map[key]
                    break
        if isinstance(gdscript_settings, dict) and "godot_path" in gdscript_settings:
            custom_path = gdscript_settings["godot_path"]
            external_endpoint = cls._parse_external_endpoint(custom_path if isinstance(custom_path, str) else None)
            if external_endpoint:
                logger.log(f"Using external Godot LSP endpoint from settings: {custom_path}", logging.INFO)
                return custom_path
            if custom_path and pathlib.Path(custom_path).exists():
                godot_path = custom_path
                logger.log(f"Using custom Godot path from settings: {godot_path}", logging.INFO)

        # If no custom path is set, use the default path resolution
        if not godot_path:
            godot_path = cls._get_gdscript_lsp_path()

        if godot_path:
            version = cls._get_godot_version(godot_path)
            logger.log(f"Found Godot at {godot_path} with version: {version}", logging.INFO)
            return godot_path

        # If not found, download Godot binary
        platform_id = PlatformUtils.get_platform_id()

        # Check for Windows and provide a helpful error message for now
        # In a full implementation, we would download the Windows binary
        if platform_id.value.startswith("win"):
            raise RuntimeError(
                "Automatic Godot installation is not yet supported on Windows. "
                "Please install Godot manually from https://godotengine.org/download and make sure it is added to your PATH."
            )

        valid_platforms = [
            PlatformId.LINUX_x64,
            PlatformId.LINUX_arm64,
            PlatformId.OSX_x64,
            PlatformId.OSX_arm64,
        ]
        if platform_id not in valid_platforms:
            raise RuntimeError(f"Platform {platform_id} is not supported for GDScript at the moment")

        godot_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), "godot")

        default_godot_version = "4.5.1-stable"
        godot_version = default_godot_version
        if isinstance(gdscript_settings, dict):
            custom_version = gdscript_settings.get("godot_version")
            if isinstance(custom_version, str) and custom_version.strip():
                godot_version = custom_version.strip()
                logger.log(f"Using custom Godot version from settings: {godot_version}", logging.INFO)

        if godot_version != default_godot_version:
            logger.log(f"Attempting to download Godot version {godot_version} (default is {default_godot_version})", logging.DEBUG)

        # Define runtime dependencies inline
        runtime_deps = {
            PlatformId.LINUX_x64: RuntimeDependency(
                id="godot_linux_x64",
                platform_id="linux-x64",
                url=f"https://github.com/godotengine/godot/releases/download/{godot_version}/Godot_v{godot_version}_linux.x86_64",
                archive_type="binary",
                binary_name="godot_linux.x86_64",
                extract_path="godot",
            ),
            PlatformId.LINUX_arm64: RuntimeDependency(
                id="godot_linux_arm64",
                platform_id="linux-arm64",
                url=f"https://github.com/godotengine/godot/releases/download/{godot_version}/Godot_v{godot_version}_linux.arm64",
                archive_type="binary",
                binary_name="godot_linux.arm64",
                extract_path="godot",
            ),
            PlatformId.OSX_x64: RuntimeDependency(
                id="godot_osx_x64",
                platform_id="osx-x64",
                url=f"https://github.com/godotengine/godot/releases/download/{godot_version}/Godot_v{godot_version}_macos.universal.zip",
                archive_type="zip",
                binary_name="Godot.app/Contents/MacOS/Godot",
                extract_path="godot",
            ),
            PlatformId.OSX_arm64: RuntimeDependency(
                id="godot_osx_arm64",
                platform_id="osx-arm64",
                url=f"https://github.com/godotengine/godot/releases/download/{godot_version}/Godot_v{godot_version}_macos.universal.zip",
                archive_type="zip",
                binary_name="Godot.app/Contents/MacOS/Godot",
                extract_path="godot",
            ),
        }

        dependency = runtime_deps[platform_id]
        godot_dir_path = pathlib.Path(godot_dir)
        godot_dir_path.mkdir(parents=True, exist_ok=True)

        binary_path = godot_dir_path / dependency.binary_name
        executable_name = "godot.exe" if platform_id.value.startswith("win") else "godot"
        executable_path = godot_dir_path / executable_name

        if not binary_path.exists():
            logger.log(f"Downloading Godot binary from {dependency.url}", logging.INFO)
            archive_type = dependency.archive_type or "binary"
            if archive_type == "binary":
                FileUtils.download_and_extract_archive(logger, dependency.url, str(binary_path), archive_type)
            else:
                FileUtils.download_and_extract_archive(logger, dependency.url, str(godot_dir_path), archive_type)

        if not binary_path.exists():
            raise FileNotFoundError(f"Godot executable not found at {binary_path}")

        # Make the binary executable on Unix-like systems
        if not platform_id.value.startswith("win"):
            os.chmod(binary_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

        if binary_path != executable_path:
            if executable_path.exists() or executable_path.is_symlink():
                executable_path.unlink()
            relative_target = os.path.relpath(binary_path, executable_path.parent)
            try:
                os.symlink(relative_target, executable_path)
            except OSError as exc:
                logger.log(f"Failed to create symlink for Godot binary ({exc}), copying instead.", logging.DEBUG)
                shutil.copy2(binary_path, executable_path)
                # Ensure copied executable retains execute permissions
                if not platform_id.value.startswith("win"):
                    executable_path.chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

        logger.log(f"Godot binary ready at: {executable_path}", logging.INFO)
        return str(executable_path)

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        """
        Creates a GDScriptLanguageServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        self._external_lsp = False
        self._tracked_godot_pids: set[int] = set()
        try:
            godot_path = self._setup_runtime_dependencies(logger, config, solidlsp_settings)
        except Exception as e:
            logger.log(f"Failed to setup GDScript runtime dependencies: {e}", logging.ERROR)
            raise RuntimeError(f"Failed to setup GDScript runtime dependencies: {e}")

        external_endpoint = self._parse_external_endpoint(godot_path if isinstance(godot_path, str) else None)
        use_external_lsp = external_endpoint is not None

        # GDScript language server uses Godot's built-in LSP support.
        # We launch Godot in editor mode and connect to its TCP LSP endpoint.
        temp_dir = None
        if not use_external_lsp:
            temp_dir = tempfile.mkdtemp(prefix="godot_lsp_")
        self._temp_dir = temp_dir  # Store reference to clean up later

        if use_external_lsp:
            tcp_host, tcp_port = external_endpoint  # type: ignore[misc]
        else:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", 0))
                tcp_port = sock.getsockname()[1]
            tcp_host = "127.0.0.1"

        if not use_external_lsp:
            cmd = [
                godot_path,
                "--headless",
                "--editor",
                "--path",
                repository_root_path,
                "--lsp-port",
                str(tcp_port),
            ]
        else:
            cmd = None
            self._external_lsp = True

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(
                cmd=cmd,
                cwd=temp_dir or repository_root_path,
                tcp_host=tcp_host,
                tcp_port=tcp_port,
                tcp_connection_timeout=120.0,
            ),
            "gdscript",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.request_id = 0

        # Set timeout for Godot LSP operations
        self.set_request_timeout(600.0)  # Allow up to 10 minutes for Godot initialization and requests in large projects

    def stop(self, shutdown_timeout: float = 2.0) -> None:
       """
       Stop the GDScript language server and ensure the Godot process is properly terminated.
       """
       self.logger.log("Stopping GDScript Language Server and Godot process...", logging.INFO)

       # First perform the standard shutdown sequence
       super().stop(shutdown_timeout)

       # Additional Godot-specific cleanup: ensure all Godot processes are terminated
       # This addresses potential orphaned Godot processes that might not be caught by the base class
       if not getattr(self, "_external_lsp", False):
           self._terminate_godot_processes()

       # Clean up temporary directory used for LSP process
       if hasattr(self, '_temp_dir') and self._temp_dir:
           try:
               import shutil
               shutil.rmtree(self._temp_dir, ignore_errors=True)
               self.logger.log(f"Cleaned up temporary directory: {self._temp_dir}", logging.DEBUG)
           except Exception as e:
               self.logger.log(f"Error cleaning up temporary directory {self._temp_dir}: {e}", logging.WARNING)
           finally:
               self._temp_dir = None

       self.logger.log("GDScript Language Server stopped", logging.INFO)

    def _terminate_godot_processes(self):
       """
       Additional cleanup to terminate any remaining Godot processes that might have been spawned.
       This helps prevent orphaned Godot processes after Serena shutdown.
       """
       tracked_pids = list(self._tracked_godot_pids)
       for pid in tracked_pids:
           self.__class__._terminate_pid_tree(pid, self.logger)
           self._untrack_godot_pid(pid)

       try:
           import psutil  # type: ignore[import-not-found]
       except ImportError:
           if tracked_pids:
               self._tracked_godot_pids.clear()
               return
           self.logger.log("psutil not available, skipping additional Godot process cleanup", logging.DEBUG)
           self._tracked_godot_pids.clear()
           return

       current_pid = os.getpid()
       try:
           for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'ppid']):
               try:
                   pid = proc.info.get('pid')
                   if not pid:
                       continue
                   if pid in self._tracked_godot_pids:
                       self.__class__._terminate_pid_tree(pid, self.logger)
                       self._untrack_godot_pid(pid)
                       continue
                   name = proc.info.get('name') or ''
                   if 'godot' not in name.lower():
                       continue
                   cmdline_list = proc.info.get('cmdline') or []
                   cmdline = ' '.join(cmdline_list)
                   is_our_process = False
                   if proc.info.get('ppid') == current_pid:
                       is_our_process = True
                   elif self.repository_root_path and self.repository_root_path in cmdline and '--lsp' in cmdline:
                       is_our_process = True
                   elif pid in self.__class__._global_tracked_godot_pids:
                       is_our_process = True
                   if not is_our_process:
                       continue
                   self.logger.log(f"Terminating orphaned Godot process {pid}", logging.INFO)
                   self.__class__._terminate_pid_tree(pid, self.logger)
                   self._untrack_godot_pid(pid)
               except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                   continue
       except Exception as e:
           self.logger.log(f"Error during additional Godot process cleanup: {e}", logging.WARNING)
       finally:
           self._tracked_godot_pids.clear()

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the GDScript Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "processId": os.getpid(),
            "clientInfo": {"name": "Serena", "version": "0.1.0"},
            "locale": "en",
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
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
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "deprecatedSupport": True,
                            "preselectSupport": True,
                        },
                    },
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"],
                    },
                    "signatureHelp": {
                        "dynamicRegistration": True,
                        "signatureInformation": {
                            "documentationFormat": ["markdown", "plaintext"],
                            "parameterInformation": {"labelOffsetSupport": True},
                        },
                    },
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                },
            },
            "initializationOptions": {
                # GDScript Language Server specific options
                "workspace": {
                    "symbols": {"ignoreFolders": [".godot", "build", "dist", "node_modules"]},
                },
            },
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }
        return initialize_params

    def _start_server(self):
        """Start GDScript Language Server process"""

        def register_capability_handler(params):
            self.logger.log(f"Received client/registerCapability request with params: {params}", logging.DEBUG)
            return

        def change_workspace_handler(params):
            """
            Handle Godot-specific gdscript_client/changeWorkspace requests during initialization.
            """
            self.logger.log(f"Received gdscript_client/changeWorkspace notification: {params}", logging.DEBUG)
            requested_path = params.get("path") if isinstance(params, dict) else None
            if requested_path:
                normalized_requested = os.path.normcase(os.path.normpath(requested_path))
                normalized_repo = os.path.normcase(os.path.normpath(self.repository_root_path))
                if normalized_requested != normalized_repo:
                    self.logger.log(
                        f"Received workspace change request for {requested_path}, but repository root is {self.repository_root_path}",
                        logging.WARNING,
                    )
                else:
                    self.logger.log(f"Acknowledging workspace change request for {requested_path}", logging.DEBUG)
            else:
                self.logger.log("Received workspace change request without a path", logging.DEBUG)
            return None

        def window_log_message(msg):
            """Handle window/logMessage notifications from Godot LSP"""
            message_text = msg.get("message", "")
            self.logger.log(f"LSP: window/logMessage: {message_text}", logging.DEBUG)

            # Check for Godot LSP readiness signals (useful for debugging)
            if "Godot Language Server" in message_text and "initialized" in message_text:
                self.logger.log("Godot LSP is ready based on log message", logging.DEBUG)
                # Don't set server_ready here since it's already set after initialization

        diagnostics_counter = {"count": 0}

        def handle_diagnostics(params):
            diagnostics_counter["count"] += 1
            uri = params.get("uri")
            diag_len = len(params.get("diagnostics", [])) if isinstance(params, dict) else "unknown"
            if diagnostics_counter["count"] <= 5 or diagnostics_counter["count"] % 25 == 0:
                self.logger.log(
                    f"Received diagnostics message #{diagnostics_counter['count']} for {uri} (entries={diag_len})",
                    logging.DEBUG,
                )
            return

        def check_server_ready(params):
            """
            Handle $/progress notifications from Godot LSP.
            """
            value = params.get("value", {})

            # Check for initialization completion progress (useful for debugging)
            if value.get("kind") == "end":
                message = value.get("message", "")
                if "initialized" in message.lower():
                    self.logger.log("Godot LSP initialization progress completed", logging.DEBUG)
                    # Don't set server_ready here since it's already set after initialization

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("gdscript_client/changeWorkspace", change_workspace_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", check_server_ready)
        self.server.on_notification("textDocument/publishDiagnostics", handle_diagnostics)

        self.logger.log("Starting GDScript Language Server process", logging.INFO)
        try:
            self.server.start()
        except Exception as e:
            self.logger.log(f"Failed to start GDScript LSP process: {e}", logging.ERROR)
            # Mark server as ready to avoid hanging, even if process failed to start
            self.server_ready.set()
            raise RuntimeError(f"Failed to start GDScript LSP process: {e}")

        if not getattr(self, "_external_lsp", False):
            server_process = getattr(self.server, "process", None)
            if server_process and getattr(server_process, "pid", None):
                self._track_spawned_godot_process(server_process.pid)

        # Add a small delay to allow the Godot process to start properly before sending initialize
        time.sleep(1.0)

        # Check if the process is still alive after the delay
        if not self._external_lsp and not self.server.is_running():
            self.logger.log("Godot LSP process terminated early", logging.ERROR)
            self.server_ready.set()  # Mark as ready to avoid hanging
            raise RuntimeError("Godot LSP process terminated early")

        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        original_timeout = self.server.get_request_timeout()  # type: ignore[attr-defined]
        if original_timeout is None or original_timeout < 600.0:
            self.logger.log(
                f"Extending request timeout from {original_timeout} to 600.0 seconds for GDScript initialization",
                logging.DEBUG,
            )
            self.server.set_request_timeout(600.0)  # type: ignore[attr-defined]
        init_start_time = time.time()
        try:
            init_response = self.server.send.initialize(initialize_params)
            elapsed = time.time() - init_start_time
            self.logger.log(f"Received initialize response from Godot LSP after {elapsed:.2f}s", logging.INFO)

            # Process the response normally
            # Verify server capabilities
            if "textDocumentSync" not in init_response["capabilities"]:
                self.logger.log("Warning: textDocumentSync not available in GDScript LSP capabilities", logging.WARNING)
            if "definitionProvider" not in init_response["capabilities"]:
                self.logger.log("Warning: definitionProvider not available in GDScript LSP capabilities", logging.WARNING)
            if "documentSymbolProvider" not in init_response["capabilities"]:
                self.logger.log("Warning: documentSymbolProvider not available in GDScript LSP capabilities", logging.WARNING)

            self.server.notify.initialized({})

        except TimeoutError as e:
            elapsed = time.time() - init_start_time
            self.logger.log(f"Initialize request timed out after {elapsed:.2f}s: {e}", logging.ERROR)
            self.server_ready.set()
            raise RuntimeError(f"Failed to initialize GDScript LSP: {e}") from e
        except Exception as e:
            elapsed = time.time() - init_start_time
            self.logger.log(f"Initialize request failed after {elapsed:.2f}s: {e}", logging.ERROR)
            self.logger.log(f"Failed to initialize GDScript LSP: {e}", logging.ERROR)
            # Mark server as ready to prevent hanging, even on initialization failure
            self.server_ready.set()
            raise RuntimeError(f"Failed to initialize GDScript LSP: {e}")
        finally:
            if original_timeout is not None and original_timeout < 600.0:
                self.server.set_request_timeout(original_timeout)  # type: ignore[attr-defined]

        # Set completions as available after successful initialization
        self.completions_available.set()

        # Set server as ready after successful initialization
        self.logger.log("GDScript LSP initialized successfully, setting as ready", logging.INFO)
        self.server_ready.set()

        # Add a settling period to ensure background indexing is complete
        settling_time = 5.0  # Allow time for any background operations
        self.logger.log(f"Allowing {settling_time} seconds for Godot LSP background operations to settle...", logging.INFO)
        time.sleep(settling_time)
        self.logger.log("GDScript LSP settling period complete", logging.INFO)
