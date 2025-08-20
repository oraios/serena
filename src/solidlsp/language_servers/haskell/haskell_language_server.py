import logging
import os
import pathlib
import shutil
import json
import subprocess
import threading
import time

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings
from solidlsp.ls_utils import PlatformUtils, FileUtils
from ..common import RuntimeDependencyCollection


class HaskellLanguageServer(SolidLanguageServer):
    """
    Provides Haskell-specific instantiation of SolidLanguageServer using HLS.
    Prefers haskell-language-server-wrapper if available, else falls back to haskell-language-server.
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # Common Haskell build artifacts to ignore
        return super().is_ignored_dirname(dirname) or dirname in [
            ".stack-work",
            "dist-newstyle",
            "dist",
            ".cabal-store",
            ".hie",
            ".ghc",
            "node_modules",
        ]

    @staticmethod
    def _find_hls_executable() -> list[str]:
        # Prefer the wrapper, fallback to hls direct binary
        for exe in ["haskell-language-server-wrapper", "haskell-language-server"]:
            path = shutil.which(exe)
            if path:
                # HLS accepts --lsp to run as LSP server; wrapper may not require it, but it's supported
                return [path, "--lsp"]
        raise RuntimeError(
            "Could not find HLS. Install via ghcup and ensure haskell-language-server-wrapper or haskell-language-server is on PATH."
        )

    @classmethod
    def _ensure_managed_hls(cls, logger: LanguageServerLogger, settings: SolidLSPSettings) -> str:
        """Download a pinned HLS if not present and return its path."""
        hls_dir = os.path.join(cls.ls_resources_dir(settings), "hls-2.11.0.0")
        os.makedirs(hls_dir, exist_ok=True)
        runtime_json = os.path.join(os.path.dirname(__file__), "runtime_dependencies.json")
        with open(runtime_json, encoding="utf-8") as f:
            d = json.load(f)
            runtime_deps = d["runtimeDependencies"]
        # Map JSON keys (camelCase) to RuntimeDependency fields (snake_case)
        mapped = []
        for dep in runtime_deps:
            archive_type = dep.get("archiveType")
            # normalize tar.xz to xztar which FileUtils supports as "xztar"
            if archive_type == "txz":
                archive_type = "xztar"
            mapped.append(
                {
                    "id": dep.get("id"),
                    "platform_id": dep.get("platformId"),
                    "url": dep.get("url"),
                    "archive_type": archive_type,
                    "binary_name": dep.get("binaryName"),
                    "extract_path": dep.get("extractPath"),
                    "description": dep.get("description"),
                }
            )
        from ..common import RuntimeDependency
        collection = RuntimeDependencyCollection(
            dependencies=[RuntimeDependency(**m) for m in mapped]
        )
        # Install for current platform if binary missing
        # This will place the binary under hls_dir (or subdir), and we compute the path
        results = collection.install(logger, hls_dir)
        # Choose the first result path as the binary; on Unix, ensure executable
        bin_path = next(iter(results.values()))
        if not os.path.exists(bin_path):
            # Some archives unpack into a subfolder; scan for the binary name
            candidate = None
            for root, _, files in os.walk(hls_dir):
                for fn in files:
                    if fn.startswith("haskell-language-server"):
                        candidate = os.path.join(root, fn)
                        break
                if candidate:
                    break
            if candidate:
                bin_path = candidate
        if not os.path.exists(bin_path):
            raise RuntimeError("Managed HLS download did not yield a usable binary")
        if not PlatformUtils.get_platform_id().is_windows():
            os.chmod(bin_path, 0o755)
        return bin_path

    def __init__(
        self,
        config: LanguageServerConfig,
        logger: LanguageServerLogger,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
    ):
        # PATH-first
        try:
            cmd = self._find_hls_executable()
        except RuntimeError:
            # Managed fallback
            managed_bin = self._ensure_managed_hls(logger, solidlsp_settings)
            cmd = [managed_bin, "--lsp"]
        logger.log(f"Starting HLS using: {' '.join(cmd)}", logging.INFO)

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=" ".join(cmd), cwd=repository_root_path),
            "haskell",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.request_id = 0
        # HLS can take a while on first project load
        self.set_request_timeout(120.0)

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        return {
            "processId": os.getpid(),
            "locale": "en",
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {"snippetSupport": True},
                    },
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                    },
                    "hover": {"dynamicRegistration": True},
                    "formatting": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                },
            },
            "workspaceFolders": [{"uri": root_uri, "name": os.path.basename(repository_absolute_path)}],
        }

    def _start_server(self):
        """Start HLS server process and wait for readiness."""

        def register_capability_handler(params):
            return

        def window_log_message(msg):
            # Example helpful logs for readiness
            message_text = msg.get("message", "")
            self.logger.log(f"LSP: window/logMessage: {message_text}", logging.INFO)
            # HLS tends to be ready right after initialize; we don't rely on a special string here

        def do_nothing(params):
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting Haskell Language Server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to HLS and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)

        # Verify a few basic capabilities
        assert "textDocumentSync" in init_response["capabilities"], "HLS missing textDocumentSync capability"

        self.server.notify.initialized({})
        self.completions_available.set()

        # HLS is typically ready after initialize; add short settling time for indexing
        time.sleep(2.0)
        self.server_ready.set()
        self.server_ready.wait()
