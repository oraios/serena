"""
Provides PowerShell specific instantiation of the LanguageServer class using PowerShell Editor Services.
Contains various configurations and settings specific to PowerShell scripting.
"""

import logging
import os
import pathlib
import platform
import shutil
import tempfile
import threading
import zipfile
from pathlib import Path

import requests
from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# PowerShell Editor Services version to download
PSES_VERSION = "4.4.0"


class PowerShellLanguageServer(SolidLanguageServer):
    """
    Provides PowerShell specific instantiation of the LanguageServer class using PowerShell Editor Services.
    Contains various configurations and settings specific to PowerShell scripting.
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For PowerShell projects, ignore common build/output directories
        return super().is_ignored_dirname(dirname) or dirname in [
            "bin",
            "obj",
            ".vscode",
            "TestResults",
            "Output",
        ]

    @staticmethod
    def _get_pwsh_path() -> str | None:
        """Get the path to PowerShell Core (pwsh) executable."""
        # Check if pwsh is in PATH
        pwsh = shutil.which("pwsh")
        if pwsh:
            return pwsh

        # Check common installation locations
        home = Path.home()
        system = platform.system()

        possible_paths: list[Path] = []
        if system == "Windows":
            possible_paths = [
                Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "PowerShell" / "7" / "pwsh.exe",
                Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "PowerShell" / "7-preview" / "pwsh.exe",
                home / "AppData" / "Local" / "Microsoft" / "PowerShell" / "pwsh.exe",
            ]
        elif system == "Darwin":
            possible_paths = [
                Path("/usr/local/bin/pwsh"),
                Path("/opt/homebrew/bin/pwsh"),
                home / ".dotnet" / "tools" / "pwsh",
            ]
        else:  # Linux
            possible_paths = [
                Path("/usr/bin/pwsh"),
                Path("/usr/local/bin/pwsh"),
                Path("/opt/microsoft/powershell/7/pwsh"),
                home / ".dotnet" / "tools" / "pwsh",
            ]

        for path in possible_paths:
            if path.exists():
                return str(path)

        return None

    @classmethod
    def _get_pses_path(cls, solidlsp_settings: SolidLSPSettings) -> str | None:
        """Get the path to PowerShell Editor Services installation."""
        install_dir = Path(cls.ls_resources_dir(solidlsp_settings)) / "powershell"
        start_script = install_dir / "PowerShellEditorServices" / "Start-EditorServices.ps1"

        if start_script.exists():
            return str(start_script)

        return None

    @classmethod
    def _download_pses(cls, solidlsp_settings: SolidLSPSettings) -> str:
        """Download and install PowerShell Editor Services."""
        download_url = (
            f"https://github.com/PowerShell/PowerShellEditorServices/releases/download/v{PSES_VERSION}/PowerShellEditorServices.zip"
        )

        # Create installation directory
        install_dir = Path(cls.ls_resources_dir(solidlsp_settings)) / "powershell"
        install_dir.mkdir(parents=True, exist_ok=True)

        # Download the file
        log.info(f"Downloading PowerShell Editor Services from {download_url}...")
        response = requests.get(download_url, stream=True, timeout=120)
        response.raise_for_status()

        # Save the zip file
        zip_path = install_dir / "PowerShellEditorServices.zip"
        with open(zip_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        log.info(f"Extracting PowerShell Editor Services to {install_dir}...")
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(install_dir)

        # Clean up zip file
        zip_path.unlink()

        start_script = install_dir / "PowerShellEditorServices" / "Start-EditorServices.ps1"
        if not start_script.exists():
            raise RuntimeError(f"Failed to find Start-EditorServices.ps1 after extraction at {start_script}")

        log.info(f"PowerShell Editor Services installed at: {install_dir}")
        return str(start_script)

    @classmethod
    def _setup_runtime_dependency(cls, solidlsp_settings: SolidLSPSettings) -> tuple[str, str, str]:
        """
        Check if required PowerShell runtime dependencies are available.
        Downloads PowerShell Editor Services if not present.

        Returns:
            tuple: (pwsh_path, start_script_path, bundled_modules_path)

        """
        # Check for PowerShell Core
        pwsh_path = cls._get_pwsh_path()
        if not pwsh_path:
            raise RuntimeError(
                "PowerShell Core (pwsh) is not installed or not in PATH. "
                "Please install PowerShell 7+ from https://github.com/PowerShell/PowerShell"
            )

        # Check for PowerShell Editor Services
        pses_path = cls._get_pses_path(solidlsp_settings)
        if not pses_path:
            log.info("PowerShell Editor Services not found. Downloading...")
            pses_path = cls._download_pses(solidlsp_settings)

        # The bundled modules path is the directory containing PowerShellEditorServices
        bundled_modules_path = str(Path(pses_path).parent)

        return pwsh_path, pses_path, bundled_modules_path

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        pwsh_path, pses_path, bundled_modules_path = self._setup_runtime_dependency(solidlsp_settings)

        # Create a temp directory for PSES logs and session details
        pses_temp_dir = Path(tempfile.gettempdir()) / "solidlsp_pses"
        pses_temp_dir.mkdir(parents=True, exist_ok=True)
        log_path = pses_temp_dir / "pses.log"
        session_details_path = pses_temp_dir / "session.json"

        # Build the command to start PowerShell Editor Services in stdio mode
        # PSES requires several parameters beyond just -Stdio
        # Using list format for robust argument handling - the PowerShell command
        # after -Command must be a single string element
        pses_command = (
            f"& '{pses_path}' "
            f"-HostName 'SolidLSP' "
            f"-HostProfileId 'solidlsp' "
            f"-HostVersion '1.0.0' "
            f"-BundledModulesPath '{bundled_modules_path}' "
            f"-LogPath '{log_path}' "
            f"-LogLevel 'Information' "
            f"-SessionDetailsPath '{session_details_path}' "
            f"-Stdio"
        )
        cmd: list[str] = [
            pwsh_path,
            "-NoLogo",
            "-NoProfile",
            "-Command",
            pses_command,
        ]

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=cmd, cwd=repository_root_path),
            "powershell",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the PowerShell Editor Services.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "deprecatedSupport": True,
                        },
                    },
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "signatureHelp": {
                        "dynamicRegistration": True,
                        "signatureInformation": {
                            "documentationFormat": ["markdown", "plaintext"],
                            "parameterInformation": {"labelOffsetSupport": True},
                        },
                    },
                    "codeAction": {"dynamicRegistration": True},
                    "formatting": {"dynamicRegistration": True},
                    "rangeFormatting": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "configuration": True,
                    "symbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
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
        return initialize_params  # type: ignore[return-value]

    def _start_server(self) -> None:
        """
        Starts the PowerShell Editor Services, waits for the server to be ready.
        """
        self._dynamic_capabilities: set[str] = set()

        def register_capability_handler(params: dict) -> None:
            """Handle dynamic capability registration from PSES."""
            registrations = params.get("registrations", [])
            for reg in registrations:
                method = reg.get("method", "")
                log.info(f"PSES registered dynamic capability: {method}")
                self._dynamic_capabilities.add(method)
                # Mark server ready when we get document symbol registration
                if method == "textDocument/documentSymbol":
                    self.server_ready.set()
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")
            # Check for PSES ready signals
            message_text = msg.get("message", "")
            if "started" in message_text.lower() or "ready" in message_text.lower():
                log.info("PowerShell Editor Services ready signal detected")
                self.server_ready.set()
                self.completions_available.set()

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("powerShell/executionStatusChanged", do_nothing)

        log.info("Starting PowerShell Editor Services process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.info(f"Received initialize response from PowerShell server: {init_response}")

        # Verify server capabilities - PSES uses dynamic capability registration
        # so we check for either static or dynamic capabilities
        capabilities = init_response.get("capabilities", {})
        log.info(f"Server capabilities: {capabilities}")

        # Send initialized notification to trigger dynamic capability registration
        self.server.notify.initialized({})

        # Wait for server readiness with timeout
        log.info("Waiting for PowerShell Editor Services to be ready...")
        if not self.server_ready.wait(timeout=10.0):
            # Fallback: assume server is ready after timeout
            log.info("Timeout waiting for PSES ready signal, proceeding anyway")
            self.server_ready.set()
            self.completions_available.set()
        else:
            log.info("PowerShell Editor Services initialization complete")
