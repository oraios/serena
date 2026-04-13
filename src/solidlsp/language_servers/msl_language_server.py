"""
Provides mSL (mIRC Scripting Language) specific instantiation of the LanguageServer class.
Uses a custom Python-based LSP server (pygls) for parsing .mrc files.

The LSP server script is shipped as ``msl_lsp_server.py`` alongside this module
and launched as a subprocess using the current Python interpreter.
"""

import logging
import os
import pathlib
import sys
import threading

from solidlsp.ls import (
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

_MSL_LSP_SCRIPT = os.path.join(os.path.dirname(__file__), "msl_lsp_server.py")


class MslLanguageServer(SolidLanguageServer):
    """
    Provides mSL (mIRC Scripting Language) specific instantiation of the LanguageServer class.
    Uses a Python-based LSP server for parsing .mrc files (aliases, events, menus, dialogs).
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates an MslLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        process_launch_info = ProcessLaunchInfo(cmd=[sys.executable, _MSL_LSP_SCRIPT], cwd=repository_root_path)
        super().__init__(
            config,
            repository_root_path,
            process_launch_info=process_launch_info,
            language_id="msl",
            solidlsp_settings=solidlsp_settings,
        )
        self.server_ready = threading.Event()

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """Returns the initialize params for the mSL Language Server."""
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "references": {"dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [{"uri": root_uri, "name": os.path.basename(repository_absolute_path)}],
        }
        return initialize_params  # type: ignore

    def _start_server(self) -> None:
        """Starts the mSL Language Server."""

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")
            self.server_ready.set()

        def do_nothing(params: dict) -> None:
            pass

        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting mSL server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request to mSL LSP server")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response: {init_response}")

        self.server.notify.initialized({})

        # Wait briefly for server readiness
        if not self.server_ready.wait(timeout=2.0):
            log.info("Timeout waiting for mSL server ready signal, proceeding anyway")
            self.server_ready.set()

        log.info("mSL server initialization complete")
