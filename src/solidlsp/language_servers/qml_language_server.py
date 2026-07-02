"""
Provides QML specific instantiation of the LanguageServer class using Qt's qmlls.
"""

import logging
import shutil

from solidlsp.ls import (
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class QmlLanguageServer(SolidLanguageServer):
    """
    Provides QML specific instantiation of the LanguageServer class using qmlls.

    qmlls is the official QML language server shipped with Qt 6.
    It must be installed separately; see https://doc.qt.io/qt-6/qtqml-tool-qmlls.html
    for installation instructions.

    The dependency provider looks for ``qmlls6`` first, then falls back to ``qmlls``.
    Users can override the executable via the ``ls_path`` entry in ``ls_specific_settings.qml``.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(config, repository_root_path, None, "qml", solidlsp_settings)

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Discover the qmlls executable on PATH.

            Tries ``qmlls6`` first (Qt 6+), then falls back to ``qmlls``.

            :return: path to the qmlls executable
            :raises FileNotFoundError: if qmlls is neither on PATH nor provided via ``ls_path``
            """
            qmlls_binary = shutil.which("qmlls6") or shutil.which("qmlls")
            if qmlls_binary is None:
                raise FileNotFoundError(
                    "qmlls (QML language server) is not installed or not in PATH.\n"
                    "Please install Qt 6 and ensure 'qmlls' (or 'qmlls6') is available on your PATH.\n"
                    "See: https://doc.qt.io/qt-6/qtqml-tool-qmlls.html"
                )
            return qmlls_binary

        def _create_launch_command(self, core_path: str) -> list[str]:
            # qmlls communicates via stdio by default; no extra flags are required.
            return [core_path]

    def _create_base_initialize_params(self) -> dict:
        """
        Return the language-specific initialize params for the QML language server.

        ``processId``, ``rootPath``, ``rootUri`` and ``workspaceFolders`` are populated by the
        default ``InitializeParamsBuilder`` and must not be set here.
        """
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
        }
        return initialize_params

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
        initialize_params = self._create_initialize_params()

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # verify server capabilities
        capabilities = init_response["capabilities"]
        log.info(f"QML language server capabilities: {list(capabilities.keys())}")

        self.server.notify.initialized({})
