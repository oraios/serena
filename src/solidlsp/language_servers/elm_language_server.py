"""
Provides Elm specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Elm.
"""

import logging
import os
import pathlib
import shutil
import threading

from overrides import override
from sensai.util.logging import LogTime

from solidlsp import ls_types
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command

log = logging.getLogger(__name__)

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_ELM_LANGUAGE_SERVER_VERSION = "2.8.0"
DEFAULT_ELM_LANGUAGE_SERVER_VERSION = "2.8.0"
INITIAL_ELM_COMPILER_VERSION = "0.19.1-6"
DEFAULT_ELM_COMPILER_VERSION = "0.19.1-6"


class ElmLanguageServer(SolidLanguageServer):
    """
    Provides Elm specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Elm.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates an ElmLanguageServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        elm_lsp_executable_path = self._setup_runtime_dependencies(config, solidlsp_settings)
        managed_bin_dir = os.path.join(self.ls_resources_dir(solidlsp_settings), "elm-lsp", "node_modules", ".bin")

        # Resolve ELM_HOME to absolute path if it's set to a relative path
        env = {"PATH": managed_bin_dir + os.pathsep + os.environ.get("PATH", "")}
        elm_home = os.environ.get("ELM_HOME")
        if elm_home:
            if not os.path.isabs(elm_home):
                # Convert relative ELM_HOME to absolute based on repository root
                elm_home = os.path.abspath(os.path.join(repository_root_path, elm_home))
            env["ELM_HOME"] = elm_home
            log.info(f"Using ELM_HOME: {elm_home}")

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=elm_lsp_executable_path, cwd=repository_root_path, env=env),
            "elm",
            solidlsp_settings,
        )

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "elm-stuff",
            "node_modules",
            "dist",
            "build",
        ]

    @classmethod
    def _setup_runtime_dependencies(cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings) -> list[str]:
        """
        Setup runtime dependencies for Elm Language Server and return the command to start the server.
        """
        elm_config = solidlsp_settings.get_ls_specific_settings(Language.ELM)
        elm_language_server_version = elm_config.get("elm_language_server_version", DEFAULT_ELM_LANGUAGE_SERVER_VERSION)
        elm_compiler_version = elm_config.get("elm_compiler_version", DEFAULT_ELM_COMPILER_VERSION)
        npm_registry = elm_config.get("npm_registry")

        # Check if elm-language-server and elm are already installed globally
        system_elm_ls = shutil.which("elm-language-server")
        system_elm = shutil.which("elm")
        if system_elm_ls and system_elm:
            log.info(f"Found system-installed elm-language-server at {system_elm_ls}")
            return [system_elm_ls, "--stdio"]

        # Verify node and npm are installed
        is_node_installed = shutil.which("node") is not None
        assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
        is_npm_installed = shutil.which("npm") is not None
        assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."
        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="elm-language-server",
                    description="@elm-tooling/elm-language-server package",
                    command=build_npm_install_command("@elm-tooling/elm-language-server", elm_language_server_version, npm_registry),
                    platform_id="any",
                ),
                RuntimeDependency(
                    id="elm",
                    description="Elm compiler package",
                    command=build_npm_install_command("elm", elm_compiler_version, npm_registry),
                    platform_id="any",
                ),
            ]
        )

        # legacy unversioned dir reserved for INITIAL pair; any other version combination goes into a versioned subdir
        is_initial = (
            elm_language_server_version == INITIAL_ELM_LANGUAGE_SERVER_VERSION and elm_compiler_version == INITIAL_ELM_COMPILER_VERSION
        )
        ls_dirname = "elm-lsp" if is_initial else f"elm-lsp-{elm_language_server_version}-{elm_compiler_version}"
        elm_ls_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), ls_dirname)
        elm_ls_executable_path = os.path.join(elm_ls_dir, "node_modules", ".bin", "elm-language-server")
        if not os.path.exists(elm_ls_executable_path):
            log.info(f"Elm Language Server executable not found at {elm_ls_executable_path}. Installing...")
            with LogTime("Installation of Elm language server dependencies", logger=log):
                deps.install(elm_ls_dir)
        elif not system_elm:
            log.info("Elm compiler not found on PATH. Installing a managed Elm compiler...")
            with LogTime("Installation of Elm compiler dependency", logger=log):
                deps.install(elm_ls_dir)

        if not os.path.exists(elm_ls_executable_path):
            raise FileNotFoundError(
                f"elm-language-server executable not found at {elm_ls_executable_path}, something went wrong with the installation."
            )
        return [elm_ls_executable_path, "--stdio"]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Elm Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()

        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "codeAction": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True},
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "initializationOptions": {
                "elmPath": shutil.which("elm") or "elm",
                "elmFormatPath": shutil.which("elm-format") or "elm-format",
                "elmTestPath": shutil.which("elm-test") or "elm-test",
                "skipInstallPackageConfirmation": True,
                "onlyUpdateDiagnosticsOnSave": False,
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
        return initialize_params  # type: ignore[return-value]

    def _start_server(self) -> None:
        """
        Starts the Elm Language Server, waits for the server to be ready and yields the LanguageServer instance.
        """
        workspace_ready = threading.Event()

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def on_diagnostics(params: dict) -> None:
            # Receiving diagnostics indicates the workspace has been scanned
            log.info("LSP: Received diagnostics notification, workspace is ready")
            workspace_ready.set()

        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", on_diagnostics)

        log.info("Starting Elm server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # Elm-specific capability checks
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]
        assert "referencesProvider" in init_response["capabilities"]
        assert "documentSymbolProvider" in init_response["capabilities"]

        self.server.notify.initialized({})
        log.info("Elm server initialized, waiting for workspace scan...")

        # Wait for workspace to be scanned (indicated by receiving diagnostics)
        if workspace_ready.wait(timeout=30.0):
            log.info("Elm server workspace scan completed")
        else:
            log.warning("Timeout waiting for Elm workspace scan, proceeding anyway")

        log.info("Elm server ready")

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 1.0

    @override
    def request_text_document_diagnostics(
        self,
        relative_file_path: str,
        start_line: int = 0,
        end_line: int = -1,
        min_severity: int = 4,
    ) -> list[ls_types.Diagnostic]:
        uri = self._validate_text_document_diagnostics_request(relative_file_path, start_line, end_line, min_severity)

        with self.open_file(relative_file_path):
            diagnostics = self._wait_for_relevant_published_diagnostics(
                uri=uri,
                after_generation=-1,
                timeout=10.0,
                allow_cached=True,
            )

        if diagnostics is None:
            return []

        return self._filter_diagnostics(diagnostics, start_line, end_line, min_severity)
