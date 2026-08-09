"""
Provides a standalone BasedPyright language server integration for Python.
"""

import logging
import re
import threading
from typing import cast

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderUvx, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

BASEDPYRIGHT_VERSION = "1.39.9"


class BasedPyrightLanguageServer(SolidLanguageServer):
    """Provides Python language support using BasedPyright."""

    _TIMEOUT_FOR_INITIAL_ANALYSIS = 60.0

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a BasedPyrightLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            str(config.ls_id),
            solidlsp_settings,
        )

        self.analysis_complete = threading.Event()
        self.found_source_files = False

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return LanguageServerDependencyProviderUvx(
            self._custom_settings,
            self._ls_resources_dir,
            package="basedpyright",
            entrypoint="basedpyright-langserver",
            default_version=BASEDPYRIGHT_VERSION,
            version_setting_key="basedpyright_version",
            extra_args=("--stdio",),
        )

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["venv", "__pycache__"]

    def _create_base_initialize_params(self) -> dict:
        initialize_params = {
            "initializationOptions": {
                "exclude": [
                    "**/__pycache__",
                    "**/.venv",
                    "**/.env",
                    "**/build",
                    "**/dist",
                    "**/.pixi",
                ],
                "reportMissingImports": "error",
            },
            "capabilities": {
                "workspace": {
                    "workspaceEdit": {"documentChanges": True},
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {"dynamicRegistration": True},
                    "symbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "executeCommand": {"dynamicRegistration": True},
                },
                "textDocument": {
                    "synchronization": {"dynamicRegistration": True, "willSave": True, "willSaveWaitUntil": True, "didSave": True},
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "signatureHelp": {
                        "dynamicRegistration": True,
                        "signatureInformation": {
                            "documentationFormat": ["markdown", "plaintext"],
                            "parameterInformation": {"labelOffsetSupport": True},
                        },
                    },
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                        "hierarchicalDocumentSymbolSupport": True,
                    },
                    "publishDiagnostics": {"relatedInformation": True},
                },
            },
        }
        return initialize_params

    def _start_server(self) -> None:
        """Starts BasedPyright and waits for initial workspace analysis to complete."""

        def execute_client_command_handler(params: dict) -> list:
            return []

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            message_text = msg.get("message", "")
            log.info("LSP: window/logMessage: %s", message_text)

            if re.search(r"Found \d+ source files?", message_text):
                log.info("BasedPyright workspace scanning complete")
                self.found_source_files = True
                self.analysis_complete.set()

        def handle_basedpyright_progress_notification(progress_kind: str, params: object | None) -> None:
            message_text = ""
            percentage: object | None = None
            if isinstance(params, dict):
                params_dict = cast("dict[str, object]", params)
                raw_message = params_dict.get("message")
                message_text = "" if raw_message is None else str(raw_message)
                percentage = params_dict.get("percentage")
            elif params is not None:
                message_text = str(params)

            progress_label = f"{message_text} ({percentage}%)" if percentage is not None else message_text

            if progress_kind == "begin":
                log.info("BasedPyright progress started: %s", progress_label)
                return

            if progress_kind == "report":
                log.debug("BasedPyright progress update: %s", progress_label)
                return

            log.info("BasedPyright progress finished: %s", progress_label)
            self.analysis_complete.set()

        def basedpyright_begin_progress(params: object | None) -> None:
            handle_basedpyright_progress_notification("begin", params)

        def basedpyright_report_progress(params: object | None) -> None:
            handle_basedpyright_progress_notification("report", params)

        def basedpyright_end_progress(params: object | None) -> None:
            handle_basedpyright_progress_notification("end", params)

        def check_experimental_status(params: dict) -> None:
            if params.get("quiescent") == True:
                log.info("Received experimental/serverStatus with quiescent=true")
                if not self.found_source_files:
                    self.analysis_complete.set()

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        # BasedPyright retains the Pyright progress-notification method names.
        self.server.on_notification("pyright/beginProgress", basedpyright_begin_progress)
        self.server.on_notification("pyright/reportProgress", basedpyright_report_progress)
        self.server.on_notification("pyright/endProgress", basedpyright_end_progress)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        log.info("Starting basedpyright-langserver server process")
        self.server.start()

        initialize_params = self._create_initialize_params()

        log.info("Sending initialize request from LSP client to BasedPyright server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.info("Received initialize response from BasedPyright server: %s", init_response)

        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]

        self.server.notify.initialized({})

        log.info(
            "Waiting up to %ss for BasedPyright to complete initial workspace analysis...",
            self._TIMEOUT_FOR_INITIAL_ANALYSIS,
        )
        if self.analysis_complete.wait(timeout=self._TIMEOUT_FOR_INITIAL_ANALYSIS):
            log.info("BasedPyright initial analysis complete, server ready")
        else:
            log.warning("Timeout waiting for BasedPyright analysis completion, proceeding anyway")
            self.analysis_complete.set()
