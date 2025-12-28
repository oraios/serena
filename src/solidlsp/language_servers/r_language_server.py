import logging
import os
import pathlib
import subprocess
import threading
from typing import Any

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class RLanguageServer(SolidLanguageServer):
    """R Language Server implementation using the languageserver R package."""

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 5.0  # R language server needs extra time for workspace indexing in CI environments

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For R projects, ignore common directories
        return super().is_ignored_dirname(dirname) or dirname in [
            "renv",  # R environment management
            "packrat",  # Legacy R package management
            ".Rproj.user",  # RStudio project files
            "vignettes",  # Package vignettes (often large)
        ]

    @staticmethod
    def _check_r_installation() -> None:
        """Check if R and languageserver are available."""
        try:
            # Check R installation
            result = subprocess.run(["R", "--version"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise RuntimeError("R is not installed or not in PATH")

            # Check languageserver package
            result = subprocess.run(
                ["R", "--vanilla", "--quiet", "--slave", "-e", "if (!require('languageserver', quietly=TRUE)) quit(status=1)"],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    "R languageserver package is not installed.\nInstall it with: R -e \"install.packages('languageserver')\""
                )

        except FileNotFoundError:
            raise RuntimeError("R is not installed. Please install R from https://www.r-project.org/")

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        # Check R installation
        self._check_r_installation()

        # R command to start language server
        # Use --vanilla for minimal startup and --quiet to suppress all output except LSP
        # Set specific options to improve parsing stability
        r_cmd = 'R --vanilla --quiet --slave -e "options(languageserver.debug_mode = FALSE); languageserver::run()"'

        super().__init__(config, repository_root_path, ProcessLaunchInfo(cmd=r_cmd, cwd=repository_root_path), "r", solidlsp_settings)
        self.server_ready = threading.Event()

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """Initialize params for R Language Server."""
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
                            "preselectSupport": True,
                        },
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "inlayHint": {"dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "formatting": {"dynamicRegistration": True},
                    "rangeFormatting": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
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
        return initialize_params  # type: ignore

    def _start_server(self) -> None:
        """Start R Language Server process."""

        def window_log_message(msg: dict) -> None:
            log.info(f"R LSP: window/logMessage: {msg}")

        def do_nothing(params: Any) -> None:
            return

        def register_capability_handler(params: Any) -> None:
            return

        # Register LSP message handlers
        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting R Language Server process")
        self.server.start()

        initialize_params = self._get_initialize_params(self.repository_root_path)
        log.info(
            "Sending initialize request to R Language Server",
        )

        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        capabilities = init_response.get("capabilities", {})
        assert "textDocumentSync" in capabilities
        if "completionProvider" in capabilities:
            log.info("R LSP completion provider available")
        if "definitionProvider" in capabilities:
            log.info("R LSP definition provider available")

        self.server.notify.initialized({})
        self.completions_available.set()

        # R Language Server is ready after initialization
        self.server_ready.set()
