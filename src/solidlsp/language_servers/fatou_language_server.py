"""Julia language server integration using Fatou."""

import logging
import threading

from typing_extensions import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderUvx, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

FATOU_VERSION = "0.18.0"
DEFAULT_INDEXING_TIMEOUT = 60.0


class FatouLanguageServer(SolidLanguageServer):
    """Provide Julia language support through Fatou.

    Optional ``ls_specific_settings.julia_fatou`` values:

    - ``ls_path``: Path to a preinstalled Fatou executable.
    - ``fatou_version``: Version installed and run through ``uvx``.
    - ``indexing_timeout``: Seconds to wait for the initial workspace index.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        self._indexing_complete = threading.Event()
        super().__init__(config, repository_root_path, None, "julia", solidlsp_settings)
        self._indexing_timeout = float(self._custom_settings.get("indexing_timeout", DEFAULT_INDEXING_TIMEOUT))

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return LanguageServerDependencyProviderUvx(
            self._custom_settings,
            self._ls_resources_dir,
            package="fatou",
            entrypoint="fatou",
            default_version=FATOU_VERSION,
            version_setting_key="fatou_version",
            extra_args=("lsp",),
        )

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [".julia", "build", "dist"]

    def _create_base_initialize_params(self) -> dict:
        return {
            "locale": "en",
            "capabilities": {
                "general": {"positionEncodings": ["utf-16"]},
                "window": {"workDoneProgress": True},
                "workspace": {
                    "applyEdit": True,
                    "workspaceEdit": {"documentChanges": True, "resourceOperations": ["create", "rename", "delete"]},
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {"dynamicRegistration": True},
                    "diagnostic": {"refreshSupport": True},
                    "symbol": {"dynamicRegistration": True},
                },
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "diagnostic": {"dynamicRegistration": False, "relatedDocumentSupport": True},
                },
            },
        }

    def _start_server(self) -> None:
        def do_nothing(_params: object) -> None:
            return

        def work_done_progress_create(_params: object) -> dict:
            self._indexing_complete.clear()
            return {}

        def progress(params: dict) -> None:
            value = params.get("value", {})
            log.info("Fatou indexing: %s", value.get("message") or value.get("title") or value.get("kind", ""))
            if value.get("kind") == "end":
                self._indexing_complete.set()

        def window_log_message(params: dict) -> None:
            log.info("Fatou: %s", params.get("message", ""))

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_request("workspace/diagnostic/refresh", do_nothing)
        self.server.on_request("window/workDoneProgress/create", work_done_progress_create)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", progress)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Fatou language server process")
        self.server.start()
        init_response = self.server.send.initialize(self._create_initialize_params())

        capabilities = init_response["capabilities"]
        assert "documentSymbolProvider" in capabilities
        assert "definitionProvider" in capabilities
        assert "referencesProvider" in capabilities

        self.server.notify.initialized({})

    @override
    def _wait_for_cross_file_references_if_needed(self) -> None:
        if self._has_waited_for_cross_file_references:
            return

        if not self._indexing_complete.wait(timeout=self._indexing_timeout):
            log.warning("Fatou indexing did not finish within %.1f seconds", self._indexing_timeout)
        self._has_waited_for_cross_file_references = True
