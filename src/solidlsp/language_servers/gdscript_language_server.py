"""
GDScript language server support for Godot projects.

Godot's built-in LSP endpoint speaks TCP. This server launches Serena's bundled
stdio<->TCP adapter process and then communicates with it as a regular stdio LSP.
"""

import logging
import os
import pathlib
import sys
from typing import Any, cast

from solidlsp.ls import LanguageServerDependencyProvider, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class GDScriptLanguageServer(SolidLanguageServer):
    """GDScript language server adapter for Godot's TCP LSP endpoint."""

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings) -> None:
        super().__init__(config, repository_root_path, None, "gdscript", solidlsp_settings)

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProvider):
        def create_launch_command(self) -> list[str]:
            host = str(self._custom_settings.get("host", "127.0.0.1"))
            port_raw = self._custom_settings.get("port", 6005)
            timeout_raw = self._custom_settings.get("connect_timeout", 10.0)
            python_path = str(self._custom_settings.get("python_path", sys.executable))

            try:
                port = int(port_raw)
            except (TypeError, ValueError) as e:
                raise ValueError(f"Invalid gdscript LSP port '{port_raw}': must be an integer.") from e
            if not 1 <= port <= 65535:
                raise ValueError(f"Invalid gdscript LSP port '{port}': must be in [1, 65535].")

            try:
                connect_timeout = float(timeout_raw)
            except (TypeError, ValueError) as e:
                raise ValueError(f"Invalid gdscript connect_timeout '{timeout_raw}': must be numeric.") from e
            if connect_timeout <= 0:
                raise ValueError(f"Invalid gdscript connect_timeout '{connect_timeout}': must be > 0.")

            return [
                python_path,
                "-m",
                "solidlsp.language_servers.gdscript_tcp_proxy",
                "--host",
                host,
                "--port",
                str(port),
                "--connect-timeout",
                str(connect_timeout),
            ]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                },
            },
            "workspaceFolders": [{"uri": root_uri, "name": os.path.basename(repository_absolute_path)}],
        }
        return cast(InitializeParams, initialize_params)

    def _start_server(self) -> None:
        def do_nothing(params: Any) -> None:
            return

        def on_log_message(params: Any) -> None:
            message = params.get("message", "") if isinstance(params, dict) else str(params)
            if message:
                log.info(f"godot-lsp: {message}")

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("window/logMessage", on_log_message)

        log.info(
            "Starting GDScript language server transport. Ensure Godot editor is running with LSP enabled "
            "(default endpoint: 127.0.0.1:6005)."
        )
        self.server.start()
        init_response = self.server.send.initialize(self._get_initialize_params(self.repository_root_path))
        capabilities = init_response.get("capabilities", {})
        if "textDocumentSync" not in capabilities:
            log.warning("GDScript server did not advertise textDocumentSync capability.")
        self.server.notify.initialized({})
