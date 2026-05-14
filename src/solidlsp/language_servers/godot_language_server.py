"""GDScript language server for Godot Engine projects.

Connects to an already-running Godot editor via TCP on port 6008.
Both Godot 3 and Godot 4 (tested through 4.6.x) use this port.

The editor must be open with its built-in language server enabled (default).
"""

import logging
import os
import pathlib
from collections.abc import Callable

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_process import LanguageServerInterface, TCPConnectionInfo, TCPLanguageServer
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo, StringDict
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# Maps config_version in project.godot to the Godot major version
_CONFIG_VERSION_TO_GODOT_MAJOR: dict[int, int] = {4: 3, 5: 4}

DEFAULT_GODOT_LS_PORT = 6008
DEFAULT_GODOT_REQUEST_TIMEOUT = 30.0


class GodotLanguageServer(SolidLanguageServer):
    """GDScript language server that connects to a running Godot editor.

    Both Godot 3 and Godot 4 expose an LSP server on TCP port 6008.
    The Godot editor must already be running — this class connects to it
    rather than launching it.

    ls_specific_settings for ``gdscript``:
        - ``port`` (int): TCP port the Godot editor's LSP listens on (default: 6008).
        - ``request_timeout`` (float): seconds to wait for an LSP response (default: 30.0).
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings) -> None:
        self._godot_version = self._detect_godot_version(repository_root_path)
        if self._godot_version is not None:
            log.info("Detected Godot version %d for project at %s", self._godot_version, repository_root_path)
        else:
            log.warning("Could not detect Godot version for project at %s", repository_root_path)

        # Dummy ProcessLaunchInfo — _create_language_server_interface() ignores it
        super().__init__(config, repository_root_path, ProcessLaunchInfo(cmd=""), "gdscript", solidlsp_settings)

    @staticmethod
    def _detect_godot_version(repo_path: str) -> int | None:
        """Read project.godot to determine the major Godot version.

        Returns None if detection fails or the config_version is unrecognized.
        """
        project_file = os.path.join(repo_path, "project.godot")
        try:
            with open(project_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("config_version="):
                        config_version = int(line.split("=", 1)[1])
                        return _CONFIG_VERSION_TO_GODOT_MAJOR.get(config_version)
        except (FileNotFoundError, ValueError, OSError):
            pass
        return None

    def _create_language_server_interface(
        self,
        process_launch_info: ProcessLaunchInfo,
        logging_fn: Callable[[str, str, StringDict | str], None] | None,
    ) -> LanguageServerInterface:
        settings: dict = self._custom_settings or {}
        port = settings.get("port", DEFAULT_GODOT_LS_PORT)
        request_timeout = settings.get("request_timeout", DEFAULT_GODOT_REQUEST_TIMEOUT)
        self._conn_info = TCPConnectionInfo(host="127.0.0.1", port=port)
        return TCPLanguageServer(
            connection_info=self._conn_info,
            language=self.language,
            determine_log_level=self._determine_log_level,
            logger=logging_fn,
            request_timeout=request_timeout,
        )

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        params = {
            "processId": os.getpid(),
            "rootUri": root_uri,
            "rootPath": repository_absolute_path,
            "workspaceFolders": [{"uri": root_uri, "name": os.path.basename(repository_absolute_path)}],
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "declaration": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {"snippetSupport": True},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                },
            },
        }
        return params  # type: ignore

    def _start_server(self) -> None:
        def do_nothing(params: dict) -> None:
            return

        # Godot sends this notification immediately on connect to report the open project path.
        self.server.on_notification("gdscript_client/changeWorkspace", do_nothing)
        # Godot-specific capability advertisement (not standard LSP).
        self.server.on_notification("gdscript/capabilities", do_nothing)
        self.server.on_notification("window/logMessage", lambda msg: log.info("LSP: window/logMessage: %s", msg))
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_request("client/registerCapability", lambda params: None)

        log.info("Connecting to Godot LSP at %s:%d", self._conn_info.host, self._conn_info.port)
        self.server.start()

        initialize_params = self._get_initialize_params(self.repository_root_path)
        log.info("Sending LSP initialize request to Godot")
        self.server.send.initialize(initialize_params)
        self.server.notify.initialized({})
        log.info("Godot LSP initialized")
