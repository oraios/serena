"""
MATLAB language server integration using the official MathWorks MATLAB Language Server.

Architecture:
    This module uses the MathWorks MATLAB VS Code extension (mathworks.language-matlab)
    which contains a Node.js-based language server. The extension is downloaded from the
    VS Code Marketplace and extracted locally. The language server spawns a real MATLAB
    process to provide code intelligence - it is NOT a standalone static analyzer.

    Flow: Serena -> Node.js LSP Server -> MATLAB Process -> Code Analysis

Why MATLAB installation is required:
    The language server launches an actual MATLAB session (via MatlabSession.js) to perform
    code analysis, diagnostics, and other features. Without MATLAB, the LSP cannot function.
    This is different from purely static analyzers that parse code without execution.

Requirements:
    - MATLAB R2021b or later must be installed and licensed
    - Node.js must be installed (for running the language server)
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
import zipfile
from typing import Any, Union, cast

import requests

from solidlsp.ls import LanguageServerDependencyProvider, LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import DocumentSymbol, InitializeParams, SymbolInformation
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# Environment variable for MATLAB installation path
MATLAB_PATH_ENV_VAR = "MATLAB_PATH"

# VS Code Marketplace URL for MATLAB extension
MATLAB_EXTENSION_URL = (
    "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/MathWorks/vsextensions/language-matlab/latest/vspackage"
)


class MatlabLanguageServer(SolidLanguageServer):
    """
    Provides MATLAB specific instantiation of the LanguageServer class using the official
    MathWorks MATLAB Language Server.

    The MATLAB language server requires:
        - MATLAB R2021b or later installed on the system
        - Node.js for running the language server

    The language server is automatically downloaded from the VS Code marketplace
    (MathWorks.language-matlab extension) and extracted.

    You can pass the following entries in ls_specific_settings["matlab"]:
        - matlab_path: Path to MATLAB installation (overrides MATLAB_PATH env var)
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a MatlabLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            "matlab",
            solidlsp_settings,
        )

        assert isinstance(self._dependency_provider, self.DependencyProvider)
        self._matlab_path = self._dependency_provider.get_matlab_path()

        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProvider):
        def __init__(self, custom_settings: SolidLSPSettings.CustomLSSettings, ls_resources_dir: str):
            super().__init__(custom_settings, ls_resources_dir)
            self._matlab_path: str | None = None

        @classmethod
        def _download_matlab_extension(cls, url: str, target_dir: str) -> bool:
            """
            Download and extract the MATLAB extension from VS Code marketplace.

            The VS Code marketplace packages extensions as .vsix files (which are ZIP archives).
            This method downloads the VSIX file and extracts it to get the language server.

            Args:
                url: VS Code marketplace URL for the MATLAB extension
                target_dir: Directory where the extension will be extracted

            Returns:
                True if successful, False otherwise

            """
            try:
                log.info(f"Downloading MATLAB extension from {url}")

                # Create target directory for the extension
                os.makedirs(target_dir, exist_ok=True)

                # Download with proper headers to mimic VS Code marketplace client
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/octet-stream, application/vsix, */*",
                }

                response = requests.get(url, headers=headers, stream=True, timeout=300)
                response.raise_for_status()

                # Save to temporary VSIX file
                temp_file = os.path.join(target_dir, "matlab_extension_temp.vsix")
                total_size = int(response.headers.get("content-length", 0))

                log.info(f"Downloading {total_size / 1024 / 1024:.1f} MB...")

                with open(temp_file, "wb") as f:
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0 and downloaded % (10 * 1024 * 1024) == 0:
                                progress = (downloaded / total_size) * 100
                                log.info(f"Download progress: {progress:.1f}%")

                log.info("Download complete, extracting...")

                # Extract VSIX file (VSIX files are ZIP archives)
                with zipfile.ZipFile(temp_file, "r") as zip_ref:
                    zip_ref.extractall(target_dir)

                # Clean up temp file
                os.remove(temp_file)

                log.info("MATLAB extension extracted successfully")
                return True

            except Exception as e:
                log.error(f"Error downloading/extracting MATLAB extension: {e}")
                return False

        def _find_matlab_extension(self) -> str | None:
            """
            Find MATLAB extension in various locations.

            Search order:
            1. Environment variable (MATLAB_EXTENSION_PATH)
            2. Default download location (~/.murena/ls_resources/matlab-extension)
            3. VS Code installed extensions

            Returns:
                Path to MATLAB extension directory or None if not found

            """
            # Check environment variable
            env_path = os.environ.get("MATLAB_EXTENSION_PATH")
            if env_path and os.path.exists(env_path):
                log.debug(f"Found MATLAB extension via MATLAB_EXTENSION_PATH: {env_path}")
                return env_path
            elif env_path:
                log.warning(f"MATLAB_EXTENSION_PATH set but directory not found: {env_path}")

            # Check default download location
            default_path = os.path.join(self._ls_resources_dir, "matlab-extension", "extension")
            if os.path.exists(default_path):
                log.debug(f"Found MATLAB extension in default location: {default_path}")
                return default_path

            # Search VS Code extensions
            vscode_extensions_dir = os.path.expanduser("~/.vscode/extensions")
            if os.path.exists(vscode_extensions_dir):
                for entry in os.listdir(vscode_extensions_dir):
                    if entry.startswith("mathworks.language-matlab"):
                        ext_path = os.path.join(vscode_extensions_dir, entry)
                        if os.path.isdir(ext_path):
                            log.debug(f"Found MATLAB extension in VS Code: {ext_path}")
                            return ext_path

            log.debug("MATLAB extension not found in any known location")
            return None

        def _download_and_install_matlab_extension(self) -> str | None:
            """
            Download and install MATLAB extension from VS Code marketplace.

            Returns:
                Path to installed extension or None if download failed

            """
            matlab_extension_dir = os.path.join(self._ls_resources_dir, "matlab-extension")

            log.info(f"Downloading MATLAB extension from: {MATLAB_EXTENSION_URL}")

            if self._download_matlab_extension(MATLAB_EXTENSION_URL, matlab_extension_dir):
                extension_path = os.path.join(matlab_extension_dir, "extension")
                if os.path.exists(extension_path):
                    log.info("MATLAB extension downloaded and installed successfully")
                    return extension_path
                else:
                    log.error(f"Download completed but extension not found at: {extension_path}")
            else:
                log.error("Failed to download MATLAB extension from marketplace")

            return None

        @classmethod
        def _get_executable_path(cls, extension_path: str) -> str:
            """
            Get the path to the MATLAB language server executable based on platform.

            The language server is a Node.js script located in the extension's server directory.
            """
            # The MATLAB extension bundles the language server in the 'server' directory
            server_dir = os.path.join(extension_path, "server", "out")
            main_script = os.path.join(server_dir, "index.js")

            if os.path.exists(main_script):
                return main_script

            # Alternative location
            alt_script = os.path.join(extension_path, "out", "index.js")
            if os.path.exists(alt_script):
                return alt_script

            raise RuntimeError(f"MATLAB language server script not found in extension at {extension_path}")

        @staticmethod
        def _find_matlab_installation() -> str:
            """
            Find MATLAB installation path.

            Search order:
                1. MATLAB_PATH environment variable
                2. Common installation locations based on platform

            Returns:
                Path to MATLAB installation directory.

            Raises:
                RuntimeError: If MATLAB installation is not found.

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

            raise RuntimeError(
                f"MATLAB installation not found. Set the {MATLAB_PATH_ENV_VAR} environment variable "
                "to your MATLAB installation directory (e.g., /Applications/MATLAB_R2024b.app on macOS, "
                "C:\\Program Files\\MATLAB\\R2024b on Windows, or /usr/local/MATLAB/R2024b on Linux)."
            )

        def get_matlab_path(self) -> str:
            """Get MATLAB path from settings or auto-detect."""
            if self._matlab_path is not None:
                return self._matlab_path

            matlab_path = self._custom_settings.get("matlab_path")

            if not matlab_path:
                matlab_path = self._find_matlab_installation()  # Raises RuntimeError if not found

            # Verify MATLAB path exists
            if not os.path.isdir(matlab_path):
                raise RuntimeError(f"MATLAB installation directory does not exist: {matlab_path}")

            log.info(f"Using MATLAB installation: {matlab_path}")

            self._matlab_path = matlab_path
            return matlab_path

        def create_launch_command(self) -> Union[str, list[str]]:
            # Verify node is installed
            node_path = shutil.which("node")
            if node_path is None:
                raise RuntimeError("Node.js is not installed or isn't in PATH. Please install Node.js and try again.")

            # Find existing extension or download if needed
            extension_path = self._find_matlab_extension()
            if extension_path is None:
                log.info("MATLAB extension not found on disk, attempting to download...")
                extension_path = self._download_and_install_matlab_extension()

            if extension_path is None:
                raise RuntimeError(
                    "Failed to locate or download MATLAB Language Server. Please either:\n"
                    "1. Set MATLAB_EXTENSION_PATH environment variable to the MATLAB extension directory\n"
                    "2. Install the MATLAB extension in VS Code (MathWorks.language-matlab)\n"
                    "3. Ensure internet connection for automatic download"
                )

            # Get the language server script path
            server_script = self._get_executable_path(extension_path)

            if not os.path.exists(server_script):
                raise RuntimeError(f"MATLAB Language Server script not found at: {server_script}")

            # Build the command to run the language server
            # The MATLAB language server is run via Node.js with the --stdio flag
            cmd = [node_path, server_script, "--stdio"]
            return cmd

        def create_launch_command_env(self) -> dict[str, str]:
            return {
                "MATLAB_INSTALL_PATH": self.get_matlab_path(),
            }

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """Return the initialize params for the MATLAB Language Server."""
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
        """Start the MATLAB Language Server and wait for it to be ready."""
        root_uri = pathlib.Path(self.repository_root_path).as_uri()

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
            return

        def execute_client_command_handler(params: dict) -> list:
            return []

        def workspace_folders_handler(params: dict) -> list:
            """Handle workspace/workspaceFolders request from the server."""
            return [{"uri": root_uri, "name": os.path.basename(self.repository_root_path)}]

        def workspace_configuration_handler(params: dict) -> list:
            """Handle workspace/configuration request from the server."""
            items = params.get("items", [])
            result = []
            for item in items:
                section = item.get("section", "")
                if section == "MATLAB":
                    # Return MATLAB configuration
                    result.append({"installPath": self._matlab_path, "matlabConnectionTiming": "onStart"})
                else:
                    result.append({})
            return result

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")
            message_text = msg.get("message", "")
            # Check for MATLAB language server ready signals
            # Wait for "MVM attach success" or "Adding workspace folder" which indicates MATLAB is fully ready
            # Note: "connected to" comes earlier but the server isn't fully ready at that point
            if "mvm attach success" in message_text.lower() or "adding workspace folder" in message_text.lower():
                log.info("MATLAB language server ready signal detected (MVM attached)")
                self.server_ready.set()
                self.completions_available.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_request("workspace/workspaceFolders", workspace_folders_handler)
        self.server.on_request("workspace/configuration", workspace_configuration_handler)
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
        # MATLAB takes longer to start than most language servers (typically 10-30 seconds)
        log.info("Waiting for MATLAB language server to be ready (this may take up to 60 seconds)...")
        if not self.server_ready.wait(timeout=60.0):
            # Fallback: assume server is ready after timeout
            log.info("Timeout waiting for MATLAB server ready signal, proceeding anyway")
            self.server_ready.set()
            self.completions_available.set()
        else:
            log.info("MATLAB server initialization complete")

    def is_ignored_dirname(self, dirname: str) -> bool:
        """Define MATLAB-specific directories to ignore."""
        return super().is_ignored_dirname(dirname) or dirname in [
            "slprj",  # Simulink project files
            "codegen",  # Code generation output
            "sldemo_cache",  # Simulink demo cache
            "helperFiles",  # Common helper file directories
        ]

    def _request_document_symbols(
        self, relative_file_path: str, file_data: LSPFileBuffer | None
    ) -> list[SymbolInformation] | list[DocumentSymbol] | None:
        """
        Override to normalize MATLAB symbol names.

        The MATLAB LSP sometimes returns symbol names as lists instead of strings,
        particularly for script sections (cell mode markers like %%). This method
        normalizes the names to strings for compatibility with the unified symbol format.
        """
        symbols = super()._request_document_symbols(relative_file_path, file_data)

        if symbols is None or len(symbols) == 0:
            return symbols

        self._normalize_matlab_symbols(symbols)
        return symbols

    def _normalize_matlab_symbols(self, symbols: list[SymbolInformation] | list[DocumentSymbol]) -> None:
        """
        Normalize MATLAB symbol names in-place.

        MATLAB LSP returns section names as lists like ["Section Name"] instead of
        strings. This converts them to plain strings.
        """
        for symbol in symbols:
            # MATLAB LSP returns names as lists for script sections, violating LSP spec
            # Cast to Any to handle runtime type that differs from spec
            name: Any = symbol.get("name")
            if isinstance(name, list):
                symbol["name"] = name[0] if name else ""
                log.debug("Normalized MATLAB symbol name from list to string")

            # Recursively normalize children if present
            children: Any = symbol.get("children")
            if children and isinstance(children, list):
                self._normalize_matlab_symbols(children)
