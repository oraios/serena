import logging
import os
import pathlib
import shutil
import threading
import time

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

from ..common import RuntimeDependency, RuntimeDependencyCollection

# Runtime dependencies configuration - moved from JSON to Python per maintainer feedback
RUNTIME_DEPENDENCIES = [
    RuntimeDependency(
        id="HLS",
        description="HLS 2.11.0.0 for macOS arm64",
        url="https://downloads.haskell.org/~hls/haskell-language-server-2.11.0.0/haskell-language-server-2.11.0.0-aarch64-apple-darwin.tar.xz",
        platform_id="osx-arm64",
        archive_type="xztar",
        binary_name="haskell-language-server-wrapper",
    ),
    RuntimeDependency(
        id="HLS",
        description="HLS 2.11.0.0 for macOS x64",
        url="https://downloads.haskell.org/~hls/haskell-language-server-2.11.0.0/haskell-language-server-2.11.0.0-x86_64-apple-darwin.tar.xz",
        platform_id="osx-x64",
        archive_type="xztar",
        binary_name="haskell-language-server-wrapper",
    ),
    RuntimeDependency(
        id="HLS",
        description="HLS 2.11.0.0 for Linux x64",
        url="https://downloads.haskell.org/~hls/haskell-language-server-2.11.0.0/haskell-language-server-2.11.0.0-x86_64-linux-unknown.tar.xz",
        platform_id="linux-x64",
        archive_type="xztar",
        binary_name="haskell-language-server-wrapper",
    ),
    RuntimeDependency(
        id="HLS",
        description="HLS 2.11.0.0 for Linux arm64 (aarch64)",
        url="https://downloads.haskell.org/~hls/haskell-language-server-2.11.0.0/haskell-language-server-2.11.0.0-aarch64-linux-ubuntu2004.tar.xz",
        platform_id="linux-arm64",
        archive_type="xztar",
        binary_name="haskell-language-server-wrapper",
    ),
    RuntimeDependency(
        id="HLS",
        description="HLS 2.11.0.0 for Windows x64",
        url="https://downloads.haskell.org/~hls/haskell-language-server-2.11.0.0/haskell-language-server-2.11.0.0-x86_64-mingw64.zip",
        platform_id="win-x64",
        archive_type="zip",
        binary_name="haskell-language-server-wrapper.exe",
    ),
]


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
    def _find_hls_executable() -> list[str] | None:
        """Find HLS executable on PATH. Returns None if not found instead of raising exception."""
        # Prefer the wrapper, fallback to hls direct binary
        for exe in ["haskell-language-server-wrapper", "haskell-language-server"]:
            path = shutil.which(exe)
            if path:
                # HLS accepts --lsp to run as LSP server; wrapper may not require it, but it's supported
                return [path, "--lsp"]
        return None

    @classmethod
    def _ensure_managed_hls(cls, logger: LanguageServerLogger, settings: SolidLSPSettings) -> str:
        """Download a pinned HLS if not present and return its path."""
        hls_dir = os.path.join(cls.ls_resources_dir(settings), "hls-2.11.0.0")
        os.makedirs(hls_dir, exist_ok=True)

        # Get the runtime dependency for current platform
        platform_id = PlatformUtils.get_platform_id()
        hls_dependency = None

        for dep in RUNTIME_DEPENDENCIES:
            if dep.platform_id == platform_id.value:
                hls_dependency = dep
                break

        if not hls_dependency:
            raise RuntimeError(f"No HLS dependency found for platform {platform_id.value}")

        runtime_collection = RuntimeDependencyCollection([hls_dependency])
        # Install for current platform if binary missing
        results = runtime_collection.install(logger, hls_dir)
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
            else:
                raise RuntimeError(f"Could not locate HLS binary in {hls_dir}")

        # Make sure the binary is executable on Unix systems
        if os.name != "nt":  # Not Windows
            os.chmod(bin_path, 0o755)

        return bin_path

    def __init__(
        self,
        config: LanguageServerConfig,
        logger: LanguageServerLogger,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
    ):
        # PATH-first approach
        cmd = self._find_hls_executable()
        if cmd is None:
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
