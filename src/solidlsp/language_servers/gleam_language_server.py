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
import threading
import time

from overrides import override

from solidlsp.ls import LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

_COMPILE_READY_TIMEOUT = 60


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
        self._active_progress_tokens: set[str | int] = set()
        self._progress_lock = threading.Lock()
        self._compile_ready = threading.Event()
        self._any_progress_seen = threading.Event()

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

        def on_progress(params: dict) -> None:
            # Gleam sends $/progress begin/end for each compilation phase.
            # Track all active tokens; only signal readiness when all tokens have ended.
            token = params.get("token")
            value = params.get("value", {})
            if not isinstance(value, dict) or token is None:
                return
            kind = value.get("kind")
            with self._progress_lock:
                if kind == "begin":
                    self._active_progress_tokens.add(token)
                    self._compile_ready.clear()
                    self._any_progress_seen.set()
                    log.info(f"Gleam LSP: compilation phase started (token={token}), active={len(self._active_progress_tokens)}")
                elif kind == "end":
                    self._active_progress_tokens.discard(token)
                    log.info(f"Gleam LSP: compilation phase ended (token={token}), active={len(self._active_progress_tokens)}")
                    if not self._active_progress_tokens:
                        log.info("Gleam LSP: all compilation phases finished")
                        self._compile_ready.set()

        def do_nothing(_params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", on_progress)
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

        # Wait for all Gleam compilation phases to finish before returning.
        # Gleam sends $/progress begin/end for each phase; we wait until no phases
        # are active. Without this, document symbol requests return empty for files
        # that haven't been fully analysed yet.
        #
        # Phase 1: wait briefly for the first $/progress begin. If none arrives
        # within 5 s the project was already cached and we can proceed immediately.
        if not self._any_progress_seen.wait(timeout=5):
            log.info("Gleam LSP: no $/progress notifications received within 5s, assuming ready (cached build)")
        else:
            # Phase 2: wait for all active tokens to complete.
            if not self._compile_ready.wait(timeout=_COMPILE_READY_TIMEOUT):
                log.warning(f"Gleam LSP: timed out waiting for initial compilation after {_COMPILE_READY_TIMEOUT}s, proceeding anyway")

        log.info("Gleam language server ready")

    @override
    def _request_document_symbols(
        self, relative_file_path: str, file_data: LSPFileBuffer | None
    ) -> list | None:
        # Send textDocument/didOpen before requesting symbols. Gleam LSP may start a
        # recompilation in response; we must wait for it to finish or the server returns
        # an empty symbol list for the file.
        if file_data is not None:
            file_data.ensure_open_in_ls()
        else:
            # Rare path: open the file ourselves so the super call gets a live buffer.
            with self.open_file(relative_file_path, open_in_ls=True) as fb:
                time.sleep(0.2)
                if not self._compile_ready.wait(timeout=_COMPILE_READY_TIMEOUT):
                    log.warning("Gleam: timed out waiting for recompile after didOpen (%s)", relative_file_path)
                return super()._request_document_symbols(relative_file_path, fb)

        # Brief window for any $/progress begin triggered by didOpen to arrive before
        # we check _compile_ready (which is already set after the initial compile).
        time.sleep(0.2)
        if not self._compile_ready.wait(timeout=_COMPILE_READY_TIMEOUT):
            log.warning("Gleam: timed out waiting for recompile after didOpen (%s)", relative_file_path)
        # file is already open in LS; super will call ensure_open_in_ls() (no-op) then
        # send the documentSymbol request.
        return super()._request_document_symbols(relative_file_path, file_data)
