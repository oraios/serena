"""
Provides Lean 4 specific instantiation of the LanguageServer class.
Uses the built-in Lean 4 language server (lean --server).
"""

import glob
import logging
import os
import pathlib
import shutil
import subprocess
import threading
import time
from typing import cast

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class Lean4LanguageServer(SolidLanguageServer):
    """
    Provides Lean 4 specific instantiation of the LanguageServer class.
    Uses the built-in Lean 4 language server invoked via ``lean --server``.
    Requires ``lean`` to be installed and available on PATH (typically via elan).
    """

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def __init__(self, custom_settings: SolidLSPSettings.CustomLSSettings, ls_resources_dir: str, repository_root_path: str):
            super().__init__(custom_settings, ls_resources_dir)
            self._repository_root_path = repository_root_path

        def _get_or_install_core_dependency(self) -> str:
            lean_path = shutil.which("lean")
            if lean_path is None:
                raise RuntimeError(
                    "lean is not installed or not in PATH.\n"
                    "Please install Lean 4 via elan: https://github.com/leanprover/elan\n"
                    "  curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh\n"
                    "After installation, make sure 'lean' is available on your PATH."
                )
            return lean_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "--server"]

        @override
        def create_launch_command_env(self) -> dict[str, str]:
            """Provides LEAN_PATH and LEAN_SRC_PATH from ``lake env`` for cross-file references."""
            env: dict[str, str] = {}
            lake_path = shutil.which("lake")
            if lake_path is None:
                log.warning("lake not found on PATH; cross-file references may not work")
                return env
            try:
                result = subprocess.run(
                    [lake_path, "env"],
                    check=False,
                    cwd=self._repository_root_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if "=" in line:
                            key, _, value = line.partition("=")
                            if key in ("LEAN_PATH", "LEAN_SRC_PATH"):
                                env[key] = value
                                log.info(f"Lake env: {key}={value}")
                else:
                    log.warning(f"lake env failed (exit {result.returncode}): {result.stderr[:200]}")
            except Exception as e:
                log.warning(f"Failed to run lake env: {e}")
            return env

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a Lean4LanguageServer instance. This class is not meant to be
        instantiated directly. Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            "lean4",
            solidlsp_settings,
        )

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir, self.repository_root_path)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [".lake", "build"]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Lean 4 Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
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
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                        },
                    },
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                },
            },
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }
        return cast(InitializeParams, initialize_params)

    def _start_server(self) -> None:
        """Start the Lean 4 language server process."""
        file_progress_status: dict[str, bool] = {}
        file_progress_lock = threading.Lock()

        def register_capability_handler(_params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(_params: dict) -> None:
            return

        def file_progress_handler(params: dict) -> None:
            """Track file processing progress from Lean 4 LSP."""
            uri = params.get("textDocument", {}).get("uri", "")
            processing = params.get("processing", [])
            with file_progress_lock:
                file_progress_status[uri] = len(processing) == 0
            log.info(f"LSP: $/lean/fileProgress: {uri} done={len(processing) == 0}")

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("$/lean/fileProgress", file_progress_handler)

        log.info("Starting Lean 4 language server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        capabilities = init_response.get("capabilities", {})
        log.info(f"Lean 4 LSP capabilities: {list(capabilities.keys())}")

        self.server.notify.initialized({})

        # Open all .lean files so the LSP can build cross-file references
        lean_files = glob.glob(os.path.join(self.repository_root_path, "**", "*.lean"), recursive=True)
        for fpath in lean_files:
            # Skip files in .lake and build directories
            rel = os.path.relpath(fpath, self.repository_root_path)
            parts = pathlib.PurePath(rel).parts
            if any(self.is_ignored_dirname(p) for p in parts):
                continue
            uri = pathlib.Path(fpath).as_uri()
            try:
                with open(fpath) as f:
                    text = f.read()
                self.server.notify.did_open_text_document(
                    {
                        "textDocument": {
                            "uri": uri,
                            "languageId": "lean4",
                            "version": 0,
                            "text": text,
                        }
                    }
                )
                log.info(f"Opened {rel} in Lean 4 LSP")
            except Exception as e:
                log.warning(f"Failed to open {rel}: {e}")

        # Wait for all opened files to finish processing
        timeout = 60
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            time.sleep(0.5)
            with file_progress_lock:
                if file_progress_status and all(file_progress_status.values()):
                    log.info("All Lean 4 files finished processing")
                    break
        else:
            log.warning("Timed out waiting for Lean 4 file processing")
