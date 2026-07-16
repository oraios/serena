"""
Provides Python specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Python.
"""

import logging
import re
import threading
from dataclasses import dataclass
from typing import Literal, cast

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderUvx, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

PYRIGHT_VERSION = "1.1.403"
BASEDPYRIGHT_VERSION = "1.39.9"

_PyrightBackendName = Literal["pyright", "basedpyright"]


@dataclass(frozen=True)
class _PyrightBackend:
    name: _PyrightBackendName
    display_name: str
    package: str
    entrypoint: str
    default_version: str
    version_setting_key: str


_PYRIGHT_BACKENDS: dict[_PyrightBackendName, _PyrightBackend] = {
    "pyright": _PyrightBackend(
        name="pyright",
        display_name="Pyright",
        package="pyright",
        entrypoint="pyright-langserver",
        default_version=PYRIGHT_VERSION,
        version_setting_key="pyright_version",
    ),
    "basedpyright": _PyrightBackend(
        name="basedpyright",
        display_name="BasedPyright",
        package="basedpyright",
        entrypoint="basedpyright-langserver",
        default_version=BASEDPYRIGHT_VERSION,
        version_setting_key="basedpyright_version",
    ),
}


class PyrightServer(SolidLanguageServer):
    """
    Provides Python specific instantiation of the LanguageServer class using Pyright.
    Contains various configurations and settings specific to Python.
    """

    _TIMEOUT_FOR_INITIAL_ANALYSIS = 60.0

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a PyrightServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        custom_settings = solidlsp_settings.get_ls_specific_settings(config.code_language)
        self._backend = self._resolve_backend(custom_settings.get("language_server", "pyright"))
        super().__init__(
            config,
            repository_root_path,
            None,
            "python",
            solidlsp_settings,
            cache_version_raw_document_symbols=("pyright-backend", self._backend.name),
        )

        # Event to signal when initial workspace analysis is complete
        self.analysis_complete = threading.Event()
        self.found_source_files = False

    @staticmethod
    def _resolve_backend(language_server: object) -> _PyrightBackend:
        valid_choices = ", ".join(repr(name) for name in _PYRIGHT_BACKENDS)
        if not isinstance(language_server, str):
            raise ValueError(
                "Invalid ls_specific_settings.python.language_server value "
                f"{language_server!r}: expected a string with one of these values: {valid_choices}"
            )
        if language_server not in _PYRIGHT_BACKENDS:
            raise ValueError(
                f"Invalid ls_specific_settings.python.language_server value {language_server!r}: expected one of: {valid_choices}"
            )
        return _PYRIGHT_BACKENDS[cast(_PyrightBackendName, language_server)]

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return LanguageServerDependencyProviderUvx(
            self._custom_settings,
            self._ls_resources_dir,
            package=self._backend.package,
            entrypoint=self._backend.entrypoint,
            default_version=self._backend.default_version,
            version_setting_key=self._backend.version_setting_key,
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
        """
        Starts the selected Pyright-compatible language server and waits for initial workspace analysis to complete.

        This prevents zombie processes by ensuring the language server has finished its initial background
        tasks before we consider the server ready.

        Usage:
        ```
        async with lsp.start_server():
            # LanguageServer has been initialized and workspace analysis is complete
            await lsp.request_definition(...)
            await lsp.request_references(...)
            # Shutdown the LanguageServer on exit from scope
        # LanguageServer has been shutdown cleanly
        ```
        """
        backend_display_name = self._backend.display_name

        def execute_client_command_handler(params: dict) -> list:
            return []

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            """
            Monitor language server log messages to detect when initial analysis is complete.
            Both supported backends log "Found X source files" when they finish scanning the workspace.
            """
            message_text = msg.get("message", "")
            log.info(f"LSP: window/logMessage: {message_text}")

            # Look for "Found X source files" which indicates workspace scanning is complete
            # Unfortunately, pyright is unreliable and there seems to be no better way
            if re.search(r"Found \d+ source files?", message_text):
                log.info("%s workspace scanning complete", backend_display_name)
                self.found_source_files = True
                self.analysis_complete.set()

        def handle_pyright_progress_notification(progress_kind: str, params: object | None) -> None:
            """Tracks Pyright-specific progress notifications.

            Pyright can emit custom progress notifications instead of only using
            ``$/progress``. Handling them avoids noisy unhandled-method warnings
            and provides an additional signal that initial analysis has quiesced.
            """
            # normalizing the notification payload
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

            # logging the progress transition
            if progress_kind == "begin":
                log.info("%s progress started: %s", backend_display_name, progress_label)
                return

            if progress_kind == "report":
                log.debug("%s progress update: %s", backend_display_name, progress_label)
                return

            log.info("%s progress finished: %s", backend_display_name, progress_label)
            self.analysis_complete.set()

        def pyright_begin_progress(params: object | None) -> None:
            """Handles the ``pyright/beginProgress`` notification."""
            # delegating to the shared progress handler
            handle_pyright_progress_notification("begin", params)

        def pyright_report_progress(params: object | None) -> None:
            """Handles the ``pyright/reportProgress`` notification."""
            # delegating to the shared progress handler
            handle_pyright_progress_notification("report", params)

        def pyright_end_progress(params: object | None) -> None:
            """Handles the ``pyright/endProgress`` notification."""
            # delegating to the shared progress handler
            handle_pyright_progress_notification("end", params)

        def check_experimental_status(params: dict) -> None:
            """
            Also listen for experimental/serverStatus as a backup signal
            """
            if params.get("quiescent") == True:
                log.info("Received experimental/serverStatus with quiescent=true")
                if not self.found_source_files:
                    self.analysis_complete.set()

        # Set up notification handlers
        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("pyright/beginProgress", pyright_begin_progress)
        self.server.on_notification("pyright/reportProgress", pyright_report_progress)
        self.server.on_notification("pyright/endProgress", pyright_end_progress)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        log.info("Starting %s server process", self._backend.entrypoint)
        self.server.start()

        # Send proper initialization parameters
        initialize_params = self._create_initialize_params()

        log.info("Sending initialize request from LSP client to %s server and awaiting response", backend_display_name)
        init_response = self.server.send.initialize(initialize_params)
        log.info("Received initialize response from %s server: %s", backend_display_name, init_response)

        # Verify that the server supports our required features
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]

        # Complete the initialization handshake
        self.server.notify.initialized({})

        # Wait for the selected backend to complete its initial workspace analysis
        # This prevents zombie processes by ensuring background tasks finish
        log.info(
            "Waiting up to %ss for %s to complete initial workspace analysis...",
            self._TIMEOUT_FOR_INITIAL_ANALYSIS,
            backend_display_name,
        )
        if self.analysis_complete.wait(timeout=self._TIMEOUT_FOR_INITIAL_ANALYSIS):
            log.info("%s initial analysis complete, server ready", backend_display_name)
        else:
            log.warning("Timeout waiting for %s analysis completion, proceeding anyway", backend_display_name)
            # Fallback: assume analysis is complete after timeout
            self.analysis_complete.set()
