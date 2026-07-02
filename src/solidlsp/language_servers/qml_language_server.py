"""
Provides QML specific instantiation of the LanguageServer class using Qt's qmlls.
"""

import logging
import pathlib
import shutil

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class QmlLanguageServer(SolidLanguageServer):
    """
    Provides QML specific instantiation of the LanguageServer class using qmlls.

    qmlls is the official QML language server shipped with Qt 6.
    It must be installed separately; see https://doc.qt.io/qt-6/qtqml-tool-qmlls.html
    for installation instructions.

    The server looks for ``qmlls6`` first, then falls back to ``qmlls``.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        qmlls_path = self._find_qmlls()

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=qmlls_path, cwd=repository_root_path),
            "qml",
            solidlsp_settings,
        )

    @staticmethod
    def _find_qmlls() -> str:
        """
        Find the qmlls executable on PATH.

        Tries ``qmlls6`` first (Qt 6+), then falls back to ``qmlls``.

        :return: path to the qmlls executable
        :raises RuntimeError: if qmlls is not found
        """
        qmlls_binary = shutil.which("qmlls6") or shutil.which("qmlls")
        if qmlls_binary is None:
            raise RuntimeError(
                "qmlls (QML language server) is not installed or not in PATH.\n"
                "Please install Qt 6 and ensure 'qmlls' (or 'qmlls6') is available on your PATH.\n"
                "See: https://doc.qt.io/qt-6/qtqml-tool-qmlls.html"
            )
        return qmlls_binary

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Return the initialize params for the QML language server.
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
            "processId": None,  # qmlls may not support processId
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": pathlib.Path(repository_absolute_path).name,
                }
            ],
        }
        return initialize_params  # type: ignore[return-value]

    def _start_server(self) -> None:
        """Start the QML language server process."""

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

        log.info("Starting QML language server (qmlls) process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request to qmlls server")
        init_response = self.server.send.initialize(initialize_params)

        # verify server capabilities
        capabilities = init_response["capabilities"]
        log.info(f"QML language server capabilities: {list(capabilities.keys())}")

        self.server.notify.initialized({})
