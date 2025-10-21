import logging
import os
import pathlib
import platform
import shutil

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


class JuliaLanguageServer(SolidLanguageServer):
    """
    Language server implementation for Julia using LanguageServer.jl.
    """

    def __init__(
        self,
        config: LanguageServerConfig,
        logger: LanguageServerLogger,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
    ):
        julia_executable = self._setup_runtime_dependency()
        julia_code = "using LanguageServer; runserver()"

        if platform.system() == "Windows":
            # On Windows, pass as list (Serena handles shell=True differently)
            julia_ls_cmd = [julia_executable, "--startup-file=no", "--history-file=no", "-e", julia_code, repository_root_path]
        else:
            # On Linux/macOS, build shell-escaped string
            import shlex

            julia_ls_cmd = (
                f"{shlex.quote(julia_executable)} "
                f"--startup-file=no "
                f"--history-file=no "
                f"-e {shlex.quote(julia_code)} "
                f"{shlex.quote(repository_root_path)}"
            )

        logger.log(f"[JULIA DEBUG] Command: {julia_ls_cmd}", logging.INFO)

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=julia_ls_cmd, cwd=repository_root_path),
            "julia",
            solidlsp_settings,
        )

    @staticmethod
    def _setup_runtime_dependency() -> str:
        """
        Check if the Julia runtime is available and return its full path.
        Raises RuntimeError with a helpful message if the dependency is missing.
        """
        # First check if julia is in PATH
        julia_path = shutil.which("julia")

        # If not found in PATH, check common installation locations
        if julia_path is None:
            common_locations = [
                os.path.expanduser("~/.juliaup/bin/julia"),
                os.path.expanduser("~/.julia/bin/julia"),
                "/usr/local/bin/julia",
                "/usr/bin/julia",
            ]

            for location in common_locations:
                if os.path.isfile(location) and os.access(location, os.X_OK):
                    julia_path = location
                    break

        if julia_path is None:
            raise RuntimeError(
                "Julia is not installed or not in your PATH. "
                "Please install Julia from https://julialang.org/downloads/ and ensure it is accessible. "
                f"Checked locations: {common_locations}"
            )

        return julia_path

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        """Define language-specific directories to ignore for Julia projects."""
        return super().is_ignored_dirname(dirname) or dirname in [".julia", "build", "dist"]

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Julia Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params: InitializeParams = {  # type: ignore
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "capabilities": {
                "workspace": {"workspaceFolders": True},
                "textDocument": {
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {"dynamicRegistration": True},
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
        """Start the LanguageServer.jl server process."""

        def do_nothing(params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting LanguageServer.jl server process", logging.INFO)
        self.server.start()

        initialize_params = self._get_initialize_params(self.repository_root_path)
        self.logger.log(
            "Sending initialize request to Julia Language Server",
            logging.INFO,
        )

        init_response = self.server.send.initialize(initialize_params)
        assert "definitionProvider" in init_response["capabilities"]
        assert "referencesProvider" in init_response["capabilities"]
        assert "documentSymbolProvider" in init_response["capabilities"]

        self.server.notify.initialized({})
        self.completions_available.set()
        self.logger.log("Julia Language Server is initialized and ready.", logging.INFO)
