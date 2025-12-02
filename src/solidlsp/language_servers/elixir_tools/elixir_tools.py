import logging
import os
import pathlib
import stat
import subprocess
import threading
from typing import Any, cast

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_utils import FileUtils, PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

from ..common import RuntimeDependency

log = logging.getLogger(__name__)


class ElixirTools(SolidLanguageServer):
    """
    Provides Elixir specific instantiation of the LanguageServer class using Expert, the official Elixir language server.
    """

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 10.0  # Elixir projects need time to compile and index before cross-file references work

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For Elixir projects, we should ignore:
        # - _build: compiled artifacts
        # - deps: dependencies
        # - node_modules: if the project has JavaScript components
        # - .elixir_ls: ElixirLS artifacts (in case both are present)
        # - cover: coverage reports
        # - .expert: Expert artifacts
        return super().is_ignored_dirname(dirname) or dirname in ["_build", "deps", "node_modules", ".elixir_ls", ".expert", "cover"]

    @override
    def is_ignored_path(self, relative_path: str, ignore_unsupported_files: bool = True) -> bool:
        """Check if a path should be ignored for symbol indexing."""
        if relative_path.endswith("mix.exs"):
            # These are project configuration files, not source code with symbols to index
            return True

        return super().is_ignored_path(relative_path, ignore_unsupported_files)

    @classmethod
    def _get_elixir_version(cls) -> str | None:
        """Get the installed Elixir version or None if not found."""
        try:
            result = subprocess.run(["elixir", "--version"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        return None

    @classmethod
    def _setup_runtime_dependencies(cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings) -> str:
        """
        Setup runtime dependencies for Expert.
        Downloads the Expert binary for the current platform and returns the path to the executable.
        """
        # Check if Elixir is available first
        elixir_version = cls._get_elixir_version()
        if not elixir_version:
            raise RuntimeError(
                "Elixir is not installed. Please install Elixir from https://elixir-lang.org/install.html and make sure it is added to your PATH."
            )

        log.info(f"Found Elixir: {elixir_version}")

        # First, check if expert is already in PATH (user may have installed it manually)
        import shutil

        expert_in_path = shutil.which("expert")
        if expert_in_path:
            log.info(f"Found Expert in PATH: {expert_in_path}")
            return expert_in_path

        platform_id = PlatformUtils.get_platform_id()

        valid_platforms = [
            PlatformId.LINUX_x64,
            PlatformId.LINUX_arm64,
            PlatformId.OSX_x64,
            PlatformId.OSX_arm64,
            PlatformId.WIN_x64,
            PlatformId.WIN_arm64,
        ]
        assert platform_id in valid_platforms, f"Platform {platform_id} is not supported for Expert at the moment"

        expert_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), "expert")

        EXPERT_VERSION = "nightly"

        # Define runtime dependencies inline
        runtime_deps = {
            PlatformId.LINUX_x64: RuntimeDependency(
                id="expert_linux_amd64",
                platform_id="linux-x64",
                url=f"https://github.com/elixir-lang/expert/releases/download/{EXPERT_VERSION}/expert_linux_amd64",
                archive_type="binary",
                binary_name="expert_linux_amd64",
                extract_path="expert",
            ),
            PlatformId.LINUX_arm64: RuntimeDependency(
                id="expert_linux_arm64",
                platform_id="linux-arm64",
                url=f"https://github.com/elixir-lang/expert/releases/download/{EXPERT_VERSION}/expert_linux_arm64",
                archive_type="binary",
                binary_name="expert_linux_arm64",
                extract_path="expert",
            ),
            PlatformId.OSX_x64: RuntimeDependency(
                id="expert_darwin_amd64",
                platform_id="osx-x64",
                url=f"https://github.com/elixir-lang/expert/releases/download/{EXPERT_VERSION}/expert_darwin_amd64",
                archive_type="binary",
                binary_name="expert_darwin_amd64",
                extract_path="expert",
            ),
            PlatformId.OSX_arm64: RuntimeDependency(
                id="expert_darwin_arm64",
                platform_id="osx-arm64",
                url=f"https://github.com/elixir-lang/expert/releases/download/{EXPERT_VERSION}/expert_darwin_arm64",
                archive_type="binary",
                binary_name="expert_darwin_arm64",
                extract_path="expert",
            ),
            PlatformId.WIN_x64: RuntimeDependency(
                id="expert_windows_amd64",
                platform_id="win-x64",
                url=f"https://github.com/elixir-lang/expert/releases/download/{EXPERT_VERSION}/expert_windows_amd64.exe",
                archive_type="binary",
                binary_name="expert_windows_amd64.exe",
                extract_path="expert.exe",
            ),
            PlatformId.WIN_arm64: RuntimeDependency(
                id="expert_windows_arm64",
                platform_id="win-arm64",
                url=f"https://github.com/elixir-lang/expert/releases/download/{EXPERT_VERSION}/expert_windows_arm64.exe",
                archive_type="binary",
                binary_name="expert_windows_arm64.exe",
                extract_path="expert.exe",
            ),
        }

        dependency = runtime_deps[platform_id]
        # On Windows, use .exe extension
        executable_name = "expert.exe" if platform_id.value.startswith("win") else "expert"
        executable_path = os.path.join(expert_dir, executable_name)
        assert dependency.binary_name is not None
        binary_path = os.path.join(expert_dir, dependency.binary_name)

        if not os.path.exists(executable_path):
            log.info(f"Downloading Expert binary from {dependency.url}")
            assert dependency.url is not None
            FileUtils.download_file(dependency.url, binary_path)

            # Make the binary executable on Unix-like systems
            if not platform_id.value.startswith("win"):
                os.chmod(binary_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

            # Create a symlink with the expected name on Unix-like systems
            if binary_path != executable_path and not platform_id.value.startswith("win"):
                if os.path.exists(executable_path):
                    os.remove(executable_path)
                os.symlink(os.path.basename(binary_path), executable_path)

        assert os.path.exists(executable_path), f"Expert executable not found at {executable_path}"

        log.info(f"Expert binary ready at: {executable_path}")
        return executable_path

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        expert_executable_path = self._setup_runtime_dependencies(config, solidlsp_settings)

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=f"{expert_executable_path} --stdio", cwd=repository_root_path),
            "elixir",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.request_id = 0

        # Set generous timeout for Expert which can be slow to initialize and respond
        self.set_request_timeout(180.0)

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Expert Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "processId": os.getpid(),
            "locale": "en",
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "initializationOptions": {
                "mix_env": "dev",
                "mix_target": "host",
                "experimental": {"completions": {"enable": False}},
                "extensions": {"credo": {"enable": True, "cli_options": []}},
            },
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {"snippetSupport": True, "documentationFormat": ["markdown", "plaintext"]},
                    },
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "formatting": {"dynamicRegistration": True},
                    "codeAction": {
                        "dynamicRegistration": True,
                        "codeActionLiteralSupport": {
                            "codeActionKind": {
                                "valueSet": [
                                    "quickfix",
                                    "refactor",
                                    "refactor.extract",
                                    "refactor.inline",
                                    "refactor.rewrite",
                                    "source",
                                    "source.organizeImports",
                                ]
                            }
                        },
                    },
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "executeCommand": {"dynamicRegistration": True},
                },
                "window": {
                    "showMessage": {"messageActionItem": {"additionalPropertiesSupport": True}},
                    "showDocument": {"support": True},
                    "workDoneProgress": True,
                },
            },
            "workspaceFolders": [{"uri": root_uri, "name": os.path.basename(repository_absolute_path)}],
        }

        return cast(InitializeParams, initialize_params)

    def _start_server(self) -> None:
        """Start Expert server process"""

        def register_capability_handler(params: Any) -> None:
            return

        def window_log_message(msg: Any) -> None:
            """Handle window/logMessage notifications from Expert"""
            message_text = msg.get("message", "")
            log.info(f"LSP: window/logMessage: {message_text}")

            # Check for Expert readiness signals
            # Expert may have different readiness indicators than NextLS
            if "ready" in message_text.lower() or "initialized" in message_text.lower():
                log.info("Expert runtime is ready based on log message")
                self.server_ready.set()

        def do_nothing(params: Any) -> None:
            return

        def check_server_ready(params: Any) -> None:
            """
            Handle $/progress notifications from Expert.
            Keep as fallback for error detection, but primary readiness detection
            is now done via window/logMessage handler.
            """
            value = params.get("value", {})

            # Check for initialization completion progress (fallback signal)
            if value.get("kind") == "end":
                message = value.get("message", "")
                if "initialized" in message.lower():
                    log.info("Expert initialization progress completed")
                    # Note: We don't set server_ready here - we wait for the log message

        def work_done_progress(params: Any) -> None:
            """
            Handle $/workDoneProgress notifications from Expert.
            Keep for completeness but primary readiness detection is via window/logMessage.
            """
            value = params.get("value", {})
            if value.get("kind") == "end":
                log.info("Expert work done progress completed")
                # Note: We don't set server_ready here - we wait for the log message

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", check_server_ready)
        self.server.on_request("window/workDoneProgress/create", do_nothing)
        self.server.on_notification("$/workDoneProgress", work_done_progress)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Expert server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities - be more lenient with Expert
        log.info(f"Expert capabilities: {list(init_response['capabilities'].keys())}")

        # Expert may not provide all capabilities immediately, so we check for basic ones
        assert "textDocumentSync" in init_response["capabilities"], f"Missing textDocumentSync in {init_response['capabilities']}"

        # Some capabilities might be optional or provided later. This is expected, so we log as info
        if "completionProvider" not in init_response["capabilities"]:
            log.info("completionProvider not available in initial capabilities")

        if "definitionProvider" not in init_response["capabilities"]:
            log.info("definitionProvider not available in initial capabilities")

        self.server.notify.initialized({})
        self.completions_available.set()

        # Expert may take time to fully compile the project, but we can start making requests
        # The window/logMessage handlers will set server_ready when explicit readiness signals arrive
        # However, we'll give it some initial time and then proceed
        ready_timeout = 10.0  # Shorter initial wait
        log.info(f"Waiting up to {ready_timeout} seconds for Expert runtime readiness signals...")

        if self.server_ready.wait(timeout=ready_timeout):
            log.info("Expert is ready based on explicit readiness signals")
        else:
            # Expert may not send explicit readiness messages like NextLS did
            # If initialization succeeded, we can proceed with requests
            log.info("No explicit readiness signal received, but Expert initialized successfully. Proceeding with requests.")
            self.server_ready.set()  # Mark as ready anyway
