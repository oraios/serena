"""
Provides Crystal specific instantiation of the LanguageServer class using Crystalline.
"""

import logging
import os
import pathlib
import shutil
import time

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# Minimum time (seconds) to wait after initialization before sending
# definition requests. Crystalline needs to compile the project before
# it can resolve definitions.
_MIN_COMPILATION_DELAY = 10


class CrystalLanguageServer(SolidLanguageServer):
    """
    Provides Crystal specific instantiation of the LanguageServer class using Crystalline.

    Crystalline is a language server for the Crystal programming language,
    implementing the Language Server Protocol. It must be installed separately;
    see https://github.com/elbywan/crystalline for installation instructions.

    Known limitations of Crystalline:

    * Only the first ``textDocument/definition`` request per session returns results.
      Subsequent requests return empty. This is a Crystalline issue, not a Serena issue.
    * ``textDocument/references`` is not functional (documented as partial support).
    * Document symbols work reliably for all requests.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        crystal_ls_path = self._find_crystalline()

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=crystal_ls_path, cwd=repository_root_path),
            "crystal",
            solidlsp_settings,
        )
        self._initialization_timestamp: float | None = None

    @staticmethod
    def _find_crystalline() -> str:
        """
        Find the Crystalline executable on PATH.

        :return: path to the Crystalline executable
        :raises RuntimeError: if Crystalline is not found
        """
        path = shutil.which("crystalline")
        if path is None:
            raise RuntimeError(
                "Crystalline (Crystal language server) is not installed or not in PATH.\n"
                "Please install it from https://github.com/elbywan/crystalline\n"
                "and make sure the 'crystalline' binary is available on your PATH."
            )
        return path

    def _wait_for_compilation(self) -> None:
        """
        Wait for Crystalline to finish its initial compilation.

        Crystalline compiles the project on startup using the Crystal compiler.
        Definition requests will fail if sent before compilation completes.
        """
        if self._initialization_timestamp is None:
            return

        elapsed = time.time() - self._initialization_timestamp
        remaining_delay = max(0, _MIN_COMPILATION_DELAY - elapsed)
        if remaining_delay > 0:
            log.info(f"Waiting {remaining_delay:.1f}s for Crystalline to compile the project")
            time.sleep(remaining_delay)

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Return the initialize params for the Crystal language server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
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
                            "documentationFormat": ["markdown", "plaintext"],
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
        }
        return initialize_params  # type: ignore[return-value]

    def _start_server(self) -> None:
        """Start the Crystal language server process."""

        def register_capability_handler(_params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(_params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Crystal language server (Crystalline) process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # verify server capabilities
        capabilities = init_response["capabilities"]
        log.info(f"Crystal language server capabilities: {list(capabilities.keys())}")
        assert "textDocumentSync" in capabilities, "textDocumentSync capability missing"

        self.server.notify.initialized({})

        # record initialization timestamp for compilation delay calculation
        self._initialization_timestamp = time.time()
