"""
Provides Nim specific instantiation of the LanguageServer class using nimlangserver.
"""

import logging
import os
import shutil

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class NimLanguageServer(SolidLanguageServer):
    """
    Nim specific instantiation of the LanguageServer class using nimlangserver.

    nimlangserver (https://github.com/nim-lang/langserver) is the officially
    maintained language server for Nim. It drives one nimsuggest process per
    project, so it needs both the ``nimlangserver`` binary and a Nim toolchain
    (``nim`` / ``nimsuggest``) available on PATH. Install it with
    ``nimble install nimlangserver``; nimble drops the binary in ``~/.nimble/bin``.

    Nim support is experimental. nimsuggest compiles the project on the first
    request, so the first symbol/definition lookup of a session can be slow, and
    cross-file references depend on nimsuggest having the whole project loaded.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        nim_ls_path = self._find_nimlangserver()
        self._check_nim_toolchain()

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=nim_ls_path, cwd=repository_root_path),
            "nim",
            solidlsp_settings,
        )

    @staticmethod
    def _find_nimlangserver() -> str:
        """
        Find the nimlangserver executable on PATH or in the nimble bin dir.

        :return: path to the nimlangserver executable
        :raises RuntimeError: if nimlangserver is not found
        """
        path = shutil.which("nimlangserver")
        if path is None:
            nimble_bin = os.path.join(os.path.expanduser("~"), ".nimble", "bin", "nimlangserver")
            if os.path.isfile(nimble_bin) and os.access(nimble_bin, os.X_OK):
                path = nimble_bin
        if path is None:
            raise RuntimeError(
                "nimlangserver (Nim language server) is not installed or not in PATH.\n"
                "Install it with 'nimble install nimlangserver' and make sure the\n"
                "'nimlangserver' binary is on your PATH (nimble installs it into ~/.nimble/bin).\n"
                "See https://github.com/nim-lang/langserver for details."
            )
        return path

    @staticmethod
    def _check_nim_toolchain() -> None:
        """
        Ensure the Nim toolchain nimlangserver depends on is available.

        :raises RuntimeError: if nimsuggest is not found
        """
        if shutil.which("nimsuggest") is None:
            nimble_bin = os.path.join(os.path.expanduser("~"), ".nimble", "bin", "nimsuggest")
            if not (os.path.isfile(nimble_bin) and os.access(nimble_bin, os.X_OK)):
                raise RuntimeError(
                    "nimlangserver requires the Nim toolchain (nimsuggest) but it was not found on PATH.\n"
                    "Install Nim from https://nim-lang.org/install.html (e.g. via choosenim or your\n"
                    "package manager) and make sure 'nimsuggest' is available on your PATH."
                )

    def _create_base_initialize_params(self) -> dict:
        """
        Return the initialize params for the Nim language server (server-specific keys only).
        """
        return {
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
            # nimlangserver reads its options from the workspace configuration; the
            # defaults (auto-discovered nimsuggest, auto project mapping) are what we want.
            "initializationOptions": {},
        }

    def _start_server(self) -> None:
        """Start the Nim language server (nimlangserver) process."""

        def register_capability_handler(_params: dict) -> None:
            return

        def workspace_configuration_handler(params: dict) -> list[dict]:
            # nimlangserver pulls its configuration via workspace/configuration and expects a
            # JSON array (one entry per requested item); the nimsuggest defaults are what we want.
            items = params.get("items", []) if isinstance(params, dict) else []
            return [{} for _ in items]

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def status_update(msg: dict) -> None:
            # nimlangserver reports nimsuggest lifecycle here (e.g. project loaded).
            log.info(f"LSP: extension/statusUpdate: {msg}")

        def do_nothing(_params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("workspace/configuration", workspace_configuration_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("window/showMessage", window_log_message)
        self.server.on_notification("extension/statusUpdate", status_update)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Nim language server (nimlangserver) process")
        self.server.start()
        initialize_params = self._create_initialize_params()

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        capabilities = init_response["capabilities"]
        log.info(f"Nim language server capabilities: {list(capabilities.keys())}")
        assert "textDocumentSync" in capabilities, "textDocumentSync capability missing"

        self.server.notify.initialized({})

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        # nimsuggest compiles the project lazily; give it time to load before
        # cross-file reference queries so it can resolve symbols across modules.
        return 5.0

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # nimcache holds generated C sources / build artifacts; nimble stores
        # downloaded dependencies under nimbledeps.
        return super().is_ignored_dirname(dirname) or dirname in ["nimcache", "nimbledeps", "htmldocs"]
