"""
Provides MATLAB specific instantiation of the LanguageServer class using the official MathWorks MATLAB Language Server.
Contains various configurations and settings specific to MATLAB.

Requirements:
    - MATLAB R2021b or later must be installed
    - Node.js and npm must be installed
    - MATLAB path can be specified via MATLAB_PATH environment variable or auto-detected

The MATLAB language server provides:
    - Code diagnostics (publishDiagnostics)
    - Code completions (completionProvider)
    - Go to definition (definitionProvider)
    - Find references (referencesProvider)
    - Document symbols (documentSymbol)
    - Document formatting (documentFormattingProvider)
    - Function signature help (signatureHelpProvider)
    - Symbol rename (renameProvider)
"""

import glob
import logging
import os
import pathlib
import platform
import shutil
import threading
from typing import cast

from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# Environment variable for MATLAB installation path
MATLAB_PATH_ENV_VAR = "MATLAB_PATH"


def find_matlab_installation() -> str | None:
    """
    Find MATLAB installation path.

    Search order:
        1. MATLAB_PATH environment variable
        2. Common installation locations based on platform

    Returns:
        Path to MATLAB installation directory, or None if not found.

    """
    # Check environment variable first
    matlab_path = os.environ.get(MATLAB_PATH_ENV_VAR)
    if matlab_path and os.path.isdir(matlab_path):
        log.info(f"Using MATLAB from environment variable {MATLAB_PATH_ENV_VAR}: {matlab_path}")
        return matlab_path

    system = platform.system()

    if system == "Darwin":  # macOS
        # Check common macOS locations
        search_patterns = [
            "/Applications/MATLAB_*.app",
            "/Volumes/*/Applications/MATLAB_*.app",
            os.path.expanduser("~/Applications/MATLAB_*.app"),
        ]
        for pattern in search_patterns:
            matches = sorted(glob.glob(pattern), reverse=True)  # Newest version first
            for match in matches:
                if os.path.isdir(match):
                    log.info(f"Found MATLAB installation: {match}")
                    return match

    elif system == "Windows":
        # Check common Windows locations
        search_patterns = [
            "C:\\Program Files\\MATLAB\\R*",
            "C:\\Program Files (x86)\\MATLAB\\R*",
        ]
        for pattern in search_patterns:
            matches = sorted(glob.glob(pattern), reverse=True)
            for match in matches:
                if os.path.isdir(match):
                    log.info(f"Found MATLAB installation: {match}")
                    return match

    elif system == "Linux":
        # Check common Linux locations
        search_patterns = [
            "/usr/local/MATLAB/R*",
            "/opt/MATLAB/R*",
            os.path.expanduser("~/MATLAB/R*"),
        ]
        for pattern in search_patterns:
            matches = sorted(glob.glob(pattern), reverse=True)
            for match in matches:
                if os.path.isdir(match):
                    log.info(f"Found MATLAB installation: {match}")
                    return match

    log.warning(
        f"MATLAB installation not found. Set the {MATLAB_PATH_ENV_VAR} environment variable "
        "to your MATLAB installation directory (e.g., /Applications/MATLAB_R2024b.app)"
    )
    return None


class MatlabLanguageServer(SolidLanguageServer):
    """
    Provides MATLAB specific instantiation of the LanguageServer class using the official
    MathWorks MATLAB Language Server.

    The MATLAB language server requires:
        - MATLAB R2021b or later installed on the system
        - Node.js and npm for running the language server

    You can pass the following entries in ls_specific_settings["matlab"]:
        - matlab_path: Path to MATLAB installation (overrides MATLAB_PATH env var)
        - matlab_language_server_version: Version of the MATLAB language server to install
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a MatlabLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        matlab_lsp_command, matlab_path = self._setup_runtime_dependencies(config, solidlsp_settings)
        self._matlab_path = matlab_path

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=matlab_lsp_command, cwd=repository_root_path),
            "matlab",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()

    @classmethod
    def _setup_runtime_dependencies(cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings) -> tuple[list[str], str]:
        """
        Setup runtime dependencies for MATLAB Language Server and return the command to start the server.

        Returns:
            Tuple of (command to start the server, MATLAB installation path)

        """
        # Verify node and npm are installed
        is_node_installed = shutil.which("node") is not None
        assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
        is_npm_installed = shutil.which("npm") is not None
        assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."

        # Get MATLAB path from settings or auto-detect
        language_specific_config = solidlsp_settings.get_ls_specific_settings(cls.get_language_enum_instance())
        matlab_path = language_specific_config.get("matlab_path")

        if not matlab_path:
            matlab_path = find_matlab_installation()

        if not matlab_path:
            raise RuntimeError(
                f"MATLAB installation not found. Please set the {MATLAB_PATH_ENV_VAR} environment variable "
                "to your MATLAB installation directory, or configure 'matlab_path' in ls_specific_settings."
            )

        # Verify MATLAB path exists
        if not os.path.isdir(matlab_path):
            raise RuntimeError(f"MATLAB installation directory does not exist: {matlab_path}")

        log.info(f"Using MATLAB installation: {matlab_path}")

        # Get MATLAB language server version from settings or use default
        matlab_ls_version = language_specific_config.get("matlab_language_server_version", "1.3.0")

        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="matlab-language-server",
                    description="MathWorks MATLAB Language Server",
                    command=["npm", "install", "--prefix", "./", f"@mathworks/matlab-language-server@{matlab_ls_version}"],
                    platform_id="any",
                ),
            ]
        )

        # Install MATLAB language server if not already installed
        matlab_ls_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), "matlab-lsp")
        matlab_executable_path = os.path.join(matlab_ls_dir, "node_modules", ".bin", "matlab-language-server")

        # Handle Windows executable extension
        if os.name == "nt":
            matlab_executable_path += ".cmd"

        # Check if installation is needed
        version_file = os.path.join(matlab_ls_dir, ".installed_version")
        needs_install = False

        if not os.path.exists(matlab_executable_path):
            log.info(f"MATLAB Language Server executable not found at {matlab_executable_path}. Installing...")
            needs_install = True
        elif os.path.exists(version_file):
            with open(version_file) as f:
                installed_version = f.read().strip()
            if installed_version != matlab_ls_version:
                log.info(
                    f"MATLAB Language Server version mismatch: installed={installed_version}, expected={matlab_ls_version}. Reinstalling..."
                )
                needs_install = True
        else:
            log.info("MATLAB Language Server version file not found. Reinstalling to ensure correct version...")
            needs_install = True

        if needs_install:
            log.info("Installing MATLAB Language Server dependencies...")
            deps.install(matlab_ls_dir)
            # Write version marker file
            with open(version_file, "w") as f:
                f.write(matlab_ls_version)
            log.info("MATLAB Language Server dependencies installed successfully")

        if not os.path.exists(matlab_executable_path):
            raise FileNotFoundError(
                f"matlab-language-server executable not found at {matlab_executable_path}, something went wrong with the installation."
            )

        # Build the command with MATLAB path
        # The MATLAB language server needs to know where MATLAB is installed
        cmd = [matlab_executable_path, "--stdio", f"--matlabInstallationPath={matlab_path}"]

        return cmd, matlab_path

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the MATLAB Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {"snippetSupport": True},
                    },
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "signatureHelp": {"dynamicRegistration": True},
                    "codeAction": {"dynamicRegistration": True},
                    "formatting": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
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
        }
        return cast(InitializeParams, initialize_params)

    def _start_server(self) -> None:
        """
        Starts the MATLAB Language Server, waits for the server to be ready.
        """

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
            return

        def execute_client_command_handler(params: dict) -> list:
            return []

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")
            message_text = msg.get("message", "")
            # Check for MATLAB language server ready signals
            if "initialized" in message_text.lower() or "ready" in message_text.lower():
                log.info("MATLAB language server ready signal detected")
                self.server_ready.set()
                self.completions_available.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting MATLAB server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response from MATLAB server: {init_response}")

        # Verify basic capabilities
        capabilities = init_response.get("capabilities", {})
        assert capabilities.get("textDocumentSync") in [1, 2], "Expected Full or Incremental text sync"

        # Log available capabilities
        if "completionProvider" in capabilities:
            log.info("MATLAB server supports completions")
        if "definitionProvider" in capabilities:
            log.info("MATLAB server supports go-to-definition")
        if "referencesProvider" in capabilities:
            log.info("MATLAB server supports find-references")
        if "documentSymbolProvider" in capabilities:
            log.info("MATLAB server supports document symbols")
        if "documentFormattingProvider" in capabilities:
            log.info("MATLAB server supports document formatting")
        if "renameProvider" in capabilities:
            log.info("MATLAB server supports rename")

        self.server.notify.initialized({})

        # Wait for server readiness with timeout
        log.info("Waiting for MATLAB language server to be ready...")
        if not self.server_ready.wait(timeout=10.0):
            # Fallback: assume server is ready after timeout
            log.info("Timeout waiting for MATLAB server ready signal, proceeding anyway")
            self.server_ready.set()
            self.completions_available.set()
        else:
            log.info("MATLAB server initialization complete")

    def is_ignored_dirname(self, dirname: str) -> bool:
        """
        Define MATLAB-specific directories to ignore.
        """
        return super().is_ignored_dirname(dirname) or dirname in [
            "slprj",  # Simulink project files
            "codegen",  # Code generation output
            "sldemo_cache",  # Simulink demo cache
            "helperFiles",  # Common helper file directories
        ]
