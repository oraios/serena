"""
Provides Zig specific instantiation of the LanguageServer class using ZLS (Zig Language Server).
"""

import logging
import os
import pathlib
import platform
import shutil
import subprocess
import threading

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class ZigLanguageServer(SolidLanguageServer):
    """
    Provides Zig specific instantiation of the LanguageServer class using ZLS.
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For Zig projects, we should ignore:
        # - zig-cache: build cache directory
        # - zig-out: default build output directory
        # - .zig-cache: alternative cache location
        # - node_modules: if the project has JavaScript components
        return super().is_ignored_dirname(dirname) or dirname in ["zig-cache", "zig-out", ".zig-cache", "node_modules", "build", "dist"]

    @staticmethod
    def _get_zig_version() -> str | None:
        """Get the installed Zig version or None if not found."""
        try:
            result = subprocess.run(["zig", "version"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        return None

    @staticmethod
    def _get_zls_version() -> str | None:
        """Get the installed ZLS version or None if not found."""
        try:
            result = subprocess.run(["zls", "--version"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        return None

    @staticmethod
    def _check_zls_installed() -> bool:
        """Check if ZLS is installed in the system."""
        return shutil.which("zls") is not None

    @staticmethod
    def _setup_runtime_dependency() -> bool:
        """
        Check if required Zig runtime dependencies are available.
        Raises RuntimeError with helpful message if dependencies are missing.
        """
        # Check for Windows and provide error message
        if platform.system() == "Windows":
            raise RuntimeError(
                "Windows is not supported by ZLS in this integration. "
                "Cross-file references don't work reliably on Windows. Reason unknown."
            )

        zig_version = ZigLanguageServer._get_zig_version()
        if not zig_version:
            raise RuntimeError(
                "Zig is not installed. Please install Zig from https://ziglang.org/download/ and make sure it is added to your PATH."
            )

        if not ZigLanguageServer._check_zls_installed():
            zls_version = ZigLanguageServer._get_zls_version()
            if not zls_version:
                raise RuntimeError(
                    "Found Zig but ZLS (Zig Language Server) is not installed.\n"
                    "Please install ZLS from https://github.com/zigtools/zls\n"
                    "You can install it via:\n"
                    "  - Package managers (brew install zls, scoop install zls, etc.)\n"
                    "  - Download pre-built binaries from GitHub releases\n"
                    "  - Build from source with: zig build -Doptimize=ReleaseSafe\n\n"
                    "After installation, make sure 'zls' is added to your PATH."
                )

        return True

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        custom_command = solidlsp_settings.get_ls_specific_settings(self.get_language_enum_instance()).get(SolidLSPSettings.CustomLSSettings.COMMAND_KEY, None)
        if custom_command:
            cmd = custom_command
        else:
            self._setup_runtime_dependency()
            cmd = "zls"

        super().__init__(config, repository_root_path, ProcessLaunchInfo(cmd=cmd, cwd=repository_root_path), "zig", solidlsp_settings)
        self.server_ready = threading.Event()
        self.request_id = 0

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Zig Language Server.
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
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "configuration": True,
                },
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
            "initializationOptions": {
                # ZLS specific options based on schema.json
                # Critical paths for ZLS to understand the project
                "zig_exe_path": shutil.which("zig"),  # Path to zig executable
                "zig_lib_path": None,  # Let ZLS auto-detect
                "build_runner_path": None,  # Let ZLS use its built-in runner
                "global_cache_path": None,  # Let ZLS use default cache
                # Build configuration
                "enable_build_on_save": True,  # Enable to analyze project structure
                "build_on_save_args": ["build"],
                # Features
                "enable_snippets": True,
                "enable_argument_placeholders": True,
                "semantic_tokens": "full",
                "warn_style": False,
                "highlight_global_var_declarations": False,
                "skip_std_references": False,
                "prefer_ast_check_as_child_process": True,
                "completion_label_details": True,
                # Inlay hints configuration
                "inlay_hints_show_variable_type_hints": True,
                "inlay_hints_show_struct_literal_field_type": True,
                "inlay_hints_show_parameter_name": True,
                "inlay_hints_show_builtin": True,
                "inlay_hints_exclude_single_argument": True,
                "inlay_hints_hide_redundant_param_names": False,
                "inlay_hints_hide_redundant_param_names_last_token": False,
            },
        }
        return initialize_params  # type: ignore[return-value]

    def _start_server(self) -> None:
        """Start ZLS server process"""

        def register_capability_handler(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting ZLS server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]
        assert "documentSymbolProvider" in init_response["capabilities"]
        assert "referencesProvider" in init_response["capabilities"]

        self.server.notify.initialized({})
        self.completions_available.set()

        # ZLS server is ready after initialization
        self.server_ready.set()
        self.server_ready.wait()

        # Open build.zig if it exists to help ZLS understand project structure
        build_zig_path = os.path.join(self.repository_root_path, "build.zig")
        if os.path.exists(build_zig_path):
            try:
                with open(build_zig_path, encoding="utf-8") as f:
                    content = f.read()
                    uri = pathlib.Path(build_zig_path).as_uri()
                    self.server.notify.did_open_text_document(
                        {
                            "textDocument": {
                                "uri": uri,
                                "languageId": "zig",
                                "version": 1,
                                "text": content,
                            }
                        }
                    )
                    log.info("Opened build.zig to provide project context to ZLS")
            except Exception as e:
                log.warning(f"Failed to open build.zig: {e}")
