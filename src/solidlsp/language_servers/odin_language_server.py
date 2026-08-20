"""
Provides Odin specific instantiation of the LanguageServer class using ols.
"""

import logging
import shutil

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class OdinLanguageServer(SolidLanguageServer):
    """
    Odin specific instantiation of the LanguageServer class using ols.

    ols (https://github.com/DanielGavin/ols) is the community language server for
    Odin. It indexes the workspace itself, but relies on the Odin compiler to
    resolve the built-in ``core`` and ``vendor`` collections, so both the ``ols``
    binary and an ``odin`` compiler need to be on PATH. Prebuilt ols binaries are
    published on its releases page; Odin is available from https://odin-lang.org.

    Odin support is experimental. ols reads collection settings from an ``ols.json``
    file at the workspace root; without one it still resolves symbols and
    definitions for files inside the workspace, which is what the symbol tooling
    relies on.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        ols_path = self._find_ols()
        self._check_odin_compiler()

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=ols_path, cwd=repository_root_path),
            "odin",
            solidlsp_settings,
        )

    @staticmethod
    def _find_ols() -> str:
        """
        Find the ols executable on PATH.

        :return: path to the ols executable
        :raises RuntimeError: if ols is not found
        """
        path = shutil.which("ols")
        if path is None:
            raise RuntimeError(
                "ols (Odin language server) is not installed or not in PATH.\n"
                "Grab a prebuilt binary from https://github.com/DanielGavin/ols/releases (or build it\n"
                "with 'odin build src -out:ols') and make sure the 'ols' binary is on your PATH."
            )
        return path

    @staticmethod
    def _check_odin_compiler() -> None:
        """
        Ensure the Odin compiler ols leans on for core/vendor collections is available.

        :raises RuntimeError: if odin is not found
        """
        if shutil.which("odin") is None:
            raise RuntimeError(
                "ols requires the Odin compiler to resolve the core/vendor collections, but 'odin'\n"
                "was not found on PATH. Install Odin from https://odin-lang.org/docs/install/ and make\n"
                "sure the 'odin' binary is on your PATH."
            )

    def _create_base_initialize_params(self) -> dict:
        """
        Return the initialize params for the Odin language server (server-specific keys only).
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
            # ols reads collections and settings from an ols.json in the workspace; the defaults
            # (index the workspace, discover the odin compiler on PATH) are what we want here.
            "initializationOptions": {},
        }

    def _start_server(self) -> None:
        """Start the Odin language server (ols) process."""

        def register_capability_handler(_params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(_params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("window/showMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Odin language server (ols) process")
        self.server.start()
        initialize_params = self._create_initialize_params()

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        capabilities = init_response["capabilities"]
        log.info(f"Odin language server capabilities: {list(capabilities.keys())}")
        assert "textDocumentSync" in capabilities, "textDocumentSync capability missing"
        assert "documentSymbolProvider" in capabilities, "documentSymbolProvider capability missing"

        self.server.notify.initialized({})

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        # ols builds its workspace index in the background; give it time to finish before
        # cross-file queries so it can resolve symbols across files in the package.
        return 5.0

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # ols writes its index cache into a .ols-cache dir; build artifacts land in build/out.
        return super().is_ignored_dirname(dirname) or dirname in [".ols-cache", "build", "out"]
