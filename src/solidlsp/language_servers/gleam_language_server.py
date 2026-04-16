"""
Provides Gleam specific instantiation of the LanguageServer class.

The Gleam language server is bundled with the Gleam compiler and is started
with `gleam lsp`. No separate installation is required beyond the Gleam compiler itself.
"""

import logging
import os
import pathlib
import shutil
import subprocess

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class GleamLanguageServer(SolidLanguageServer):
    """
    Provides Gleam specific instantiation of the LanguageServer class.

    Uses the language server bundled with the Gleam compiler (`gleam lsp`).
    Requires the `gleam` binary to be installed and available on PATH.
    See https://gleam.run for installation instructions.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        gleam_path = self._find_gleam()
        self._fetch_deps(gleam_path, repository_root_path)

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=[gleam_path, "lsp"], cwd=repository_root_path),
            "gleam",
            solidlsp_settings,
        )

    @staticmethod
    def _fetch_deps(gleam_path: str, repository_root_path: str) -> None:
        """Run ``gleam deps download`` so the stdlib is available before the LSP starts."""
        try:
            result = subprocess.run(
                [gleam_path, "deps", "download"],
                cwd=repository_root_path,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if result.returncode != 0:
                log.warning(f"gleam deps download failed (exit {result.returncode}): {result.stderr[:200]}")
            else:
                log.info("gleam deps download completed")
        except Exception as e:
            log.warning(f"Failed to run gleam deps download: {e}")

    @staticmethod
    def _find_gleam() -> str:
        """
        Find the Gleam compiler executable on PATH.

        :return: absolute path to the `gleam` binary
        :raises RuntimeError: if Gleam is not found on PATH
        """
        path = shutil.which("gleam")
        if path is None:
            raise RuntimeError(
                "Gleam is not installed or not in PATH.\n"
                "Please install the Gleam compiler from https://gleam.run/getting-started/installing/\n"
                "and make sure the 'gleam' binary is available on your PATH.\n"
                "The Gleam language server is bundled with the compiler and requires no separate installation."
            )
        return path

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["build", "_build"]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Gleam Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
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
        """Start the Gleam language server process."""

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

        log.info("Starting Gleam language server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        capabilities = init_response["capabilities"]
        log.info(f"Gleam language server capabilities: {list(capabilities.keys())}")
        assert "textDocumentSync" in capabilities, "textDocumentSync capability missing"

        self.server.notify.initialized({})
        log.info("Gleam language server ready")
