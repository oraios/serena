"""
Provides BSL (1C:Enterprise) specific instantiation of the LanguageServer class
using bsl-language-server by 1c-syntax. Supports .bsl and .os files.
Requires Java 11+ on PATH.
"""

import logging
import os
import pathlib
import shutil
import threading

from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection
from solidlsp.ls import (
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

BSL_LS_VERSION = "0.29.0"
BSL_LS_JAR_URL = "https://github.com/1c-syntax/bsl-language-server/releases/download/v0.29.0/bsl-language-server-0.29.0-exec.jar"
BSL_LS_JAR_SHA256 = "d6fa9ad638ba51855e260b88ad1f8ce4e602385845a4ee43600d148f779bcf0b"


class BSLLanguageServer(SolidLanguageServer):
    """
    BSL (1C:Enterprise / OneScript) language server integration for Serena.
    """

    def __init__(
        self,
        config: LanguageServerConfig,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
    ):
        super().__init__(
            config,
            repository_root_path,
            None,
            "bsl",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            if shutil.which("java") is None:
                raise RuntimeError("Java 11+ is required for BSL Language Server but was not found on PATH.")
            jar_dir = os.path.join(self._ls_resources_dir, "bsl-ls")
            jar_path = os.path.join(jar_dir, "bsl-language-server.jar")
            if not os.path.exists(jar_path):
                deps = RuntimeDependencyCollection(
                    [
                        RuntimeDependency(
                            id="bsl-language-server",
                            description="BSL Language Server JAR by 1c-syntax",
                            url=BSL_LS_JAR_URL,
                            sha256=BSL_LS_JAR_SHA256,
                            archive_type="binary",
                            binary_name="bsl-language-server.jar",
                            platform_id="any",
                        ),
                    ]
                )
                deps.install(jar_dir)
            if not os.path.exists(jar_path):
                raise FileNotFoundError(f"BSL Language Server JAR not found at {jar_path} after installation.")
            return jar_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return ["java", "-jar", core_path]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        return {  # type: ignore[return-value]
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},  # type: ignore
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},  # type: ignore
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {"uri": root_uri, "name": os.path.basename(repository_absolute_path)},
            ],
        }

    def _start_server(self) -> None:
        def window_log_message(msg: dict) -> None:
            log.info("BSL LSP: %s", msg.get("message", ""))

        def do_nothing(_: dict) -> None:
            return

        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_request(
            "client/registerCapability",
            lambda params: None,
        )

        log.info("Starting BSL language server process")
        self.server.start()

        init_params = self._get_initialize_params(self.repository_root_path)
        init_response = self.server.send.initialize(init_params)
        log.debug("BSL LSP initialize response: %s", init_response)

        assert "capabilities" in init_response, "BSL LSP did not return capabilities"

        self.server.notify.initialized({})
        self.server_ready.set()
