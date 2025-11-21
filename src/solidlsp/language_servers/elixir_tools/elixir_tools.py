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
from solidlsp.lsp_protocol_handler import lsp_types
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

from ..common import RuntimeDependency

log = logging.getLogger(__name__)


class ElixirTools(SolidLanguageServer):
    """
    Provides Elixir specific instantiation of the LanguageServer class using Next LS from elixir-tools.
    """

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 10.0  # Elixir projects need a lot of time to compile and index before cross-file references work

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For Elixir projects, we should ignore:
        # - _build: compiled artifacts
        # - deps: dependencies
        # - node_modules: if the project has JavaScript components
        # - .elixir_ls: ElixirLS artifacts (in case both are present)
        # - cover: coverage reports
        return super().is_ignored_dirname(dirname) or dirname in ["_build", "deps", "node_modules", ".elixir_ls", "cover"]

    @override
    def is_ignored_path(self, relative_path: str, ignore_unsupported_files: bool = True) -> bool:
        """Check if a path should be ignored for symbol indexing."""
        if relative_path.endswith("mix.exs"):
            # These are project configuration files, not source code with symbols to index
            return True

        return super().is_ignored_path(relative_path, ignore_unsupported_files)

    @staticmethod
    def _is_next_ls_internal_file(abs_path: str) -> bool:
        """Check if an absolute path is a Next LS internal file that should be ignored."""
        return any(
            pattern in abs_path
            for pattern in [
                ".burrito",  # Next LS runtime directory
                "next_ls_erts-",  # Next LS Erlang runtime
                "_next_ls_private_",  # Next LS private files
                "/priv/monkey/",  # Next LS monkey patching directory
            ]
        )

    @override
    def _send_references_request(self, relative_file_path: str, line: int, column: int) -> list[lsp_types.Location] | None:
        """Override to filter out Next LS internal files from references."""
        from solidlsp.ls_utils import PathUtils

        # Get the raw response from the parent implementation
        raw_response = super()._send_references_request(relative_file_path, line, column)

        if raw_response is None:
            return None

        # Filter out Next LS internal files
        filtered_response = []
        for item in raw_response:
            if isinstance(item, dict) and "uri" in item:
                abs_path = PathUtils.uri_to_path(item["uri"])
                if self._is_next_ls_internal_file(abs_path):
                    log.debug(f"Filtering out Next LS internal file: {abs_path}")
                    continue
            filtered_response.append(item)

        return filtered_response

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
        Setup runtime dependencies for Next LS.
        Downloads the Next LS binary for the current platform and returns the path to the executable.
        """
        # Check if Elixir is available first
        elixir_version = cls._get_elixir_version()
        if not elixir_version:
            raise RuntimeError(
                "Elixir is not installed. Please install Elixir from https://elixir-lang.org/install.html and make sure it is added to your PATH."
            )

        log.info(f"Found Elixir: {elixir_version}")

        platform_id = PlatformUtils.get_platform_id()

        # Check for Windows and provide a helpful error message
        if platform_id.value.startswith("win"):
            raise RuntimeError(
                "Windows is not supported by Next LS. The Next LS project does not provide Windows binaries. "
                "Consider using Windows Subsystem for Linux (WSL) or a virtual machine with Linux/macOS."
            )

        valid_platforms = [
            PlatformId.LINUX_x64,
            PlatformId.LINUX_arm64,
            PlatformId.OSX_x64,
            PlatformId.OSX_arm64,
        ]
        assert platform_id in valid_platforms, f"Platform {platform_id} is not supported for Next LS at the moment"

        next_ls_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), "next-ls")

        NEXTLS_VERSION = "v0.23.4"

        # Define runtime dependencies inline
        runtime_deps = {
            PlatformId.LINUX_x64: RuntimeDependency(
                id="next_ls_linux_amd64",
                platform_id="linux-x64",
                url=f"https://github.com/elixir-tools/next-ls/releases/download/{NEXTLS_VERSION}/next_ls_linux_amd64",
                archive_type="binary",
                binary_name="next_ls_linux_amd64",
                extract_path="next_ls",
            ),
            PlatformId.LINUX_arm64: RuntimeDependency(
                id="next_ls_linux_arm64",
                platform_id="linux-arm64",
                url=f"https://github.com/elixir-tools/next-ls/releases/download/{NEXTLS_VERSION}/next_ls_linux_arm64",
                archive_type="binary",
                binary_name="next_ls_linux_arm64",
                extract_path="next_ls",
            ),
            PlatformId.OSX_x64: RuntimeDependency(
                id="next_ls_darwin_amd64",
                platform_id="osx-x64",
                url=f"https://github.com/elixir-tools/next-ls/releases/download/{NEXTLS_VERSION}/next_ls_darwin_amd64",
                archive_type="binary",
                binary_name="next_ls_darwin_amd64",
                extract_path="next_ls",
            ),
            PlatformId.OSX_arm64: RuntimeDependency(
                id="next_ls_darwin_arm64",
                platform_id="osx-arm64",
                url=f"https://github.com/elixir-tools/next-ls/releases/download/{NEXTLS_VERSION}/next_ls_darwin_arm64",
                archive_type="binary",
                binary_name="next_ls_darwin_arm64",
                extract_path="next_ls",
            ),
        }

        dependency = runtime_deps[platform_id]
        executable_path = os.path.join(next_ls_dir, "nextls")
        assert dependency.binary_name is not None
        binary_path = os.path.join(next_ls_dir, dependency.binary_name)

        if not os.path.exists(executable_path):
            log.info(f"Downloading Next LS binary from {dependency.url}")
            assert dependency.url is not None
            FileUtils.download_file(dependency.url, binary_path)

            # Make the binary executable on Unix-like systems
            os.chmod(binary_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

            # Create a symlink with the expected name
            if binary_path != executable_path:
                if os.path.exists(executable_path):
                    os.remove(executable_path)
                os.symlink(os.path.basename(binary_path), executable_path)

        assert os.path.exists(executable_path), f"Next LS executable not found at {executable_path}"

        log.info(f"Next LS binary ready at: {executable_path}")
        return executable_path

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        nextls_executable_path = self._setup_runtime_dependencies(config, solidlsp_settings)

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=f'"{nextls_executable_path}" --stdio', cwd=repository_root_path),
            "elixir",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.request_id = 0

        # Set generous timeout for Next LS which can be slow to initialize and respond
        self.set_request_timeout(180.0)  # 60 seconds for all environments

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Next LS Language Server.
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
        """Start Next LS server process"""

        def register_capability_handler(params: Any) -> None:
            return

        def window_log_message(msg: Any) -> None:
            """Handle window/logMessage notifications from Next LS"""
            message_text = msg.get("message", "")
            log.info(f"LSP: window/logMessage: {message_text}")

            # Check for the specific Next LS readiness signal
            # Based on Next LS source: "Runtime for folder #{name} is ready..."
            if "Runtime for folder" in message_text and "is ready..." in message_text:
                log.info("Next LS runtime is ready based on official log message")
                self.server_ready.set()

        def do_nothing(params: Any) -> None:
            return

        def check_server_ready(params: Any) -> None:
            """
            Handle $/progress notifications from Next LS.
            Keep as fallback for error detection, but primary readiness detection
            is now done via window/logMessage handler.
            """
            value = params.get("value", {})

            # Check for initialization completion progress (fallback signal)
            if value.get("kind") == "end":
                message = value.get("message", "")
                if "has initialized!" in message:
                    log.info("Next LS initialization progress completed")
                    # Note: We don't set server_ready here - we wait for the log message

        def work_done_progress(params: Any) -> None:
            """
            Handle $/workDoneProgress notifications from Next LS.
            Keep for completeness but primary readiness detection is via window/logMessage.
            """
            value = params.get("value", {})
            if value.get("kind") == "end":
                log.info("Next LS work done progress completed")
                # Note: We don't set server_ready here - we wait for the log message

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", check_server_ready)
        self.server.on_request("window/workDoneProgress/create", do_nothing)
        self.server.on_notification("$/workDoneProgress", work_done_progress)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Next LS server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities - be more lenient with Next LS
        log.info(f"Next LS capabilities: {list(init_response['capabilities'].keys())}")

        # Next LS may not provide all capabilities immediately, so we check for basic ones
        assert "textDocumentSync" in init_response["capabilities"], f"Missing textDocumentSync in {init_response['capabilities']}"

        # Some capabilities might be optional or provided later. This is expected, so we log as info
        if "completionProvider" not in init_response["capabilities"]:
            log.info("completionProvider not available in initial capabilities")

        if "definitionProvider" not in init_response["capabilities"]:
            log.info("definitionProvider not available in initial capabilities")

        self.server.notify.initialized({})
        self.completions_available.set()

        # Wait for Next LS to send the specific "Runtime for folder X is ready..." log message
        # This is the authoritative signal that Next LS is truly ready for requests
        ready_timeout = 180.0
        log.info(f"Waiting up to {ready_timeout} seconds for Next LS runtime readiness...")

        if self.server_ready.wait(timeout=ready_timeout):
            log.info("Next LS is ready and available for requests")

        else:
            error_msg = f"Next LS failed to initialize within {ready_timeout} seconds. This may indicate a problem with the Elixir installation, project compilation, or Next LS itself."
            log.error(error_msg)
            raise RuntimeError(error_msg)
