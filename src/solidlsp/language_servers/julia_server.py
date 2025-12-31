import logging
import os
import pathlib
import platform
import shutil
import subprocess
from typing import Any

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class JuliaLanguageServer(SolidLanguageServer):
    """
    Language server implementation for Julia using LanguageServer.jl.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        julia_executable = self._setup_runtime_dependency()  # PASS LOGGER
        julia_code = "using LanguageServer; runserver()"

        julia_ls_cmd: str | list[str]
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

        log.info(f"[JULIA DEBUG] Command: {julia_ls_cmd}")

        super().__init__(
            config, repository_root_path, ProcessLaunchInfo(cmd=julia_ls_cmd, cwd=repository_root_path), "julia", solidlsp_settings
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

        # Check if LanguageServer.jl is installed
        check_cmd = [julia_path, "-e", "using LanguageServer"]
        try:
            result = subprocess.run(check_cmd, check=False, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                # LanguageServer.jl not found, install it
                JuliaLanguageServer._install_language_server(julia_path)
        except subprocess.TimeoutExpired:
            # Assume it needs installation
            JuliaLanguageServer._install_language_server(julia_path)

        return julia_path

    @staticmethod
    def _install_language_server(julia_path: str) -> None:
        """Install LanguageServer.jl package."""
        log.info("LanguageServer.jl not found. Installing... (this may take a minute)")

        install_cmd = [julia_path, "-e", 'using Pkg; Pkg.add("LanguageServer")']

        try:
            result = subprocess.run(install_cmd, check=False, capture_output=True, text=True, timeout=300)  # 5 minutes for installation

            if result.returncode == 0:
                log.info("LanguageServer.jl installed successfully!")
            else:
                raise RuntimeError(f"Failed to install LanguageServer.jl: {result.stderr}")
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                "LanguageServer.jl installation timed out. Please install manually: julia -e 'using Pkg; Pkg.add(\"LanguageServer\")'"
            )

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
                    "inlayHint": {"dynamicRegistration": True},
                },
            },
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }
        return initialize_params  # type: ignore

    def _start_server(self) -> None:
        """Start the LanguageServer.jl server process."""

        def do_nothing(params: Any) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", self._handle_publish_diagnostics)

        log.info("Starting LanguageServer.jl server process")
        self.server.start()

        initialize_params = self._get_initialize_params(self.repository_root_path)
        log.info("Sending initialize request to Julia Language Server")

        init_response = self.server.send.initialize(initialize_params)
        assert "definitionProvider" in init_response["capabilities"]
        assert "referencesProvider" in init_response["capabilities"]
        assert "documentSymbolProvider" in init_response["capabilities"]

        self.server.notify.initialized({})
        self.completions_available.set()
        log.info("Julia Language Server is initialized and ready.")
