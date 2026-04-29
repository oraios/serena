"""
Provides PowerShell specific instantiation of the LanguageServer class using PowerShell Editor Services.
Contains various configurations and settings specific to PowerShell scripting.

You can pass the following entries in ``ls_specific_settings["powershell"]``:
    - pses_version: Override the pinned PowerShell Editor Services version
      downloaded by Serena (default: the bundled Serena version).
    - psscriptanalyzer_version: Override the pinned PSScriptAnalyzer version
      saved into the bundled PowerShell Editor Services module path.
"""

import logging
import os
import pathlib
import platform
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Hashable
from pathlib import Path

from overrides import override

from solidlsp import ls_types
from solidlsp.ls import LSPConstants, RawDocumentSymbol, SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_types import SymbolKind
from solidlsp.ls_utils import FileUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# PowerShell Editor Services version to download
# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_PSES_VERSION = "4.4.0"
INITIAL_PSES_SHA256 = "690b91092989a0f66e6f43986166aaef69d64b559a9fda51feed882e1103fbcc"
DEFAULT_PSES_VERSION = "4.4.0"
DEFAULT_PSES_SHA256 = "690b91092989a0f66e6f43986166aaef69d64b559a9fda51feed882e1103fbcc"


def _pses_sha(version: str) -> str | None:
    if version == INITIAL_PSES_VERSION:
        return INITIAL_PSES_SHA256
    if version == DEFAULT_PSES_VERSION:
        return DEFAULT_PSES_SHA256
    return None


def _pses_install_dir(ls_resources_dir: str, version: str) -> Path:
    # legacy unversioned dir reserved for INITIAL; every other version goes into a versioned subdir
    if version == INITIAL_PSES_VERSION:
        return Path(ls_resources_dir) / "powershell"
    return Path(ls_resources_dir) / f"powershell-{version}"


PSES_ALLOWED_HOSTS = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")
PSSCRIPTANALYZER_VERSION = "1.25.0"


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
        ps_settings = solidlsp_settings.get_ls_specific_settings(Language.POWERSHELL)
        pses_version = ps_settings.get("pses_version", DEFAULT_PSES_VERSION)
        install_dir = _pses_install_dir(cls.ls_resources_dir(solidlsp_settings), pses_version)
        start_script = install_dir / "PowerShellEditorServices" / "Start-EditorServices.ps1"

        if start_script.exists():
            return str(start_script)

        return None

    @classmethod
    def _download_pses(cls, solidlsp_settings: SolidLSPSettings) -> str:
        """Download and install PowerShell Editor Services."""
        ps_settings = solidlsp_settings.get_ls_specific_settings(Language.POWERSHELL)
        pses_version = ps_settings.get("pses_version", DEFAULT_PSES_VERSION)
        download_url = (
            f"https://github.com/PowerShell/PowerShellEditorServices/releases/download/v{pses_version}/PowerShellEditorServices.zip"
        )

        # Create installation directory; legacy unversioned dir reserved for INITIAL only
        install_dir = _pses_install_dir(cls.ls_resources_dir(solidlsp_settings), pses_version)
        install_dir.mkdir(parents=True, exist_ok=True)

        log.info(f"Downloading PowerShell Editor Services from {download_url}...")
        FileUtils.download_and_extract_archive_verified(
            download_url,
            str(install_dir),
            "zip",
            expected_sha256=_pses_sha(pses_version),
            allowed_hosts=PSES_ALLOWED_HOSTS,
        )

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
        psscriptanalyzer_version = solidlsp_settings.get_ls_specific_settings(Language.POWERSHELL).get(
            "psscriptanalyzer_version", PSSCRIPTANALYZER_VERSION
        )
        psscriptanalyzer_path = Path(bundled_modules_path) / "PSScriptAnalyzer" / psscriptanalyzer_version
        if not psscriptanalyzer_path.exists():
            log.info(f"PSScriptAnalyzer {psscriptanalyzer_version} not found. Installing...")
            subprocess.run(
                [
                    pwsh_path,
                    "-NoLogo",
                    "-NoProfile",
                    "-Command",
                    (
                        "Save-Module "
                        "-Name PSScriptAnalyzer "
                        f"-RequiredVersion '{psscriptanalyzer_version}' "
                        f"-Path '{bundled_modules_path}' "
                        "-Force "
                        "-ErrorAction Stop"
                    ),
                ],
                check=True,
            )

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

    @override
    def _document_symbols_cache_fingerprint(self) -> Hashable:
        normalize_symbol_name_version = 1
        return normalize_symbol_name_version

    @override
    def _normalize_symbol_name(self, symbol: RawDocumentSymbol, relative_file_path: str) -> str:
        original_name = symbol["name"]
        symbol_kind = symbol.get("kind")

        # normalize class declarations
        if symbol_kind == SymbolKind.Class:
            return original_name.removeprefix("class ").split("{", 1)[0].strip()

        # normalize method signatures
        if symbol_kind == SymbolKind.Method:
            return original_name.split("(", 1)[0].rsplit(None, 1)[-1]

        # normalize function declarations
        if symbol_kind == SymbolKind.Function:
            return original_name.removeprefix("function ").split("(", 1)[0].strip()

        return original_name

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
        else:
            log.info("PowerShell Editor Services initialization complete")

    @override
    def request_text_document_diagnostics(
        self,
        relative_file_path: str,
        start_line: int = 0,
        end_line: int = -1,
        min_severity: int = 4,
    ) -> list[ls_types.Diagnostic]:
        uri = self._validate_text_document_diagnostics_request(relative_file_path, start_line, end_line, min_severity)
        published_uri = self._get_published_diagnostics_uri(uri)
        diagnostics_before_request = self._get_published_diagnostics_generation(published_uri)

        with self.open_file(relative_file_path):
            self.server.notify.did_save_text_document(
                {
                    LSPConstants.TEXT_DOCUMENT: {  # type: ignore
                        LSPConstants.URI: uri,
                    }
                }
            )
            diagnostics = self._wait_for_relevant_published_diagnostics(
                uri=published_uri,
                after_generation=diagnostics_before_request,
                timeout=self._get_published_diagnostics_wait_timeout(True),
                allow_cached=True,
            )

        if diagnostics is None:
            return []

        return self._filter_diagnostics(diagnostics, start_line, end_line, min_severity)
