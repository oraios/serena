"""
Python language server integration using Meta's ``pyrefly``.

You can pass the following entries in ``ls_specific_settings["python_pyrefly"]``:
    - ls_path: Override the executable used to start ``pyrefly``.
    - pyrefly_version: Override the pinned ``pyrefly`` version used with ``uvx`` / ``uv x``
      (default: the bundled Serena version).
    - indexing_mode: Override pyrefly's LSP indexing mode (e.g. ``lazy-blocking``).
    - workspace_indexing_limit: Override pyrefly's workspace indexing limit.
"""

import logging
import os
import pathlib
import sys
import threading
import time
from typing import Any, cast

from typing_extensions import override

from solidlsp import ls_types
from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderUvx, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams, LSPErrorCodes
from solidlsp.lsp_protocol_handler.server import LSPError, PayloadLike
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

PYREFLY_VERSION = "1.1.1"
PYREFLY_CONFIG_DOC_URL = "https://pyrefly.org/en/docs/configuration/"

# Pyrefly cancels in-flight requests with these error codes whenever its workspace state mutates
# (e.g. background re-indexing triggered by opening files). Such cancellations are transient.
_MUTATION_RETRY_ERROR_CODES = (LSPErrorCodes.RequestCancelled, LSPErrorCodes.ContentModified)


class PyreflyLanguageServer(SolidLanguageServer):
    """
    Provides Python specific instantiation of the LanguageServer class using ``pyrefly``.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a PyreflyLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            str(config.code_language),
            solidlsp_settings,
        )
        self._ensure_workspace_pyrefly_config()
        self._indexing_complete = threading.Event()
        self._active_progress_tokens: set[Any] = set()

    def _ensure_workspace_pyrefly_config(self) -> None:
        """
        Ensure pyrefly has a stable workspace boundary by creating an empty ``pyrefly.toml`` when
        neither ``pyrefly.toml`` nor ``pyproject.toml`` exists in the repository root.
        """
        if not os.path.isdir(self.repository_root_path):
            return

        pyrefly_config_path = os.path.join(self.repository_root_path, "pyrefly.toml")
        pyproject_config_path = os.path.join(self.repository_root_path, "pyproject.toml")

        if not os.path.exists(pyrefly_config_path) and not os.path.exists(pyproject_config_path):
            try:
                pathlib.Path(pyrefly_config_path).touch()
                log.warning(
                    "No config found in repository root (%s): neither `pyrefly.toml` nor `pyproject.toml` exists. "
                    "Created empty `%s` as a fallback so pyrefly won't search parent directories and mis-resolve imports. "
                    "See pyrefly config docs: %s",
                    self.repository_root_path,
                    pyrefly_config_path,
                    PYREFLY_CONFIG_DOC_URL,
                )
            except OSError as exc:
                log.warning("Failed to create fallback pyrefly config at %s: %s", pyrefly_config_path, exc)

    def _install_mutation_retry(self, max_retries: int = 5, retry_delay: float = 0.2) -> None:
        """
        Wraps the underlying ``send_request`` so that requests canceled by pyrefly due to a
        concurrent workspace mutation are transparently retried.

        Pyrefly performs background re-indexing (e.g. when files are opened) and cancels any
        in-flight request with ``RequestCancelled`` (-32800) or ``ContentModified`` (-32801)
        while that mutation is in progress. These cancellations are transient, so we re-issue
        the request after a short delay instead of surfacing the error to the caller.
        """
        inner_send_request = self.server.send_request

        def send_request_with_retry(method: str, params: dict | None = None) -> PayloadLike:
            last_exc: SolidLSPException | None = None
            for attempt in range(1, max_retries + 1):
                try:
                    return inner_send_request(method, params)
                except SolidLSPException as e:
                    cause = e.cause
                    if not (isinstance(cause, LSPError) and int(cause.code) in _MUTATION_RETRY_ERROR_CODES):
                        raise
                    last_exc = e
                    log.info(
                        "Pyrefly request %s canceled by concurrent mutation (code=%s); retrying (%d/%d)",
                        method,
                        cause.code,
                        attempt,
                        max_retries,
                    )
                    time.sleep(retry_delay)
            assert last_exc is not None
            raise last_exc

        self.server.send_request = send_request_with_retry  # type: ignore[method-assign]

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        extra_args = ["lsp"]
        indexing_mode = self._custom_settings.get("indexing_mode")
        if indexing_mode is not None:
            extra_args.extend(["--indexing-mode", str(indexing_mode)])
        workspace_indexing_limit = self._custom_settings.get("workspace_indexing_limit")
        if workspace_indexing_limit is not None:
            extra_args.extend(["--workspace-indexing-limit", str(workspace_indexing_limit)])
        return LanguageServerDependencyProviderUvx(
            self._custom_settings,
            self._ls_resources_dir,
            package="pyrefly",
            entrypoint="pyrefly",
            default_version=PYREFLY_VERSION,
            version_setting_key="pyrefly_version",
            extra_args=extra_args,
        )

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["venv", "__pycache__"]

    @override
    def request_defining_symbol(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        include_body: bool = False,
    ) -> ls_types.UnifiedSymbolInformation | None:
        symbol = super().request_defining_symbol(relative_file_path, line, column, include_body=include_body)
        if symbol is None or symbol.get("name") != "__init__":
            return symbol

        # Pyrefly resolves a constructor call (e.g. ``User(...)``) to the class's ``__init__`` method,
        # whereas jedi/pyright resolve it to the class itself. For parity, return the enclosing class
        # unless the caller pointed directly at the ``__init__`` definition.
        location = symbol.get("location")
        if location is not None:
            def_path = location.get("relativePath")
            def_line = location.get("range", {}).get("start", {}).get("line")
            if (def_path, def_line) == (relative_file_path, line):
                return symbol

        enclosing = self.request_container_of_symbol(symbol, include_body=include_body)
        if enclosing is not None and enclosing.get("kind") == ls_types.SymbolKind.Class:
            return enclosing
        return symbol

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        return "python"

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the pyrefly language server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "processId": os.getpid(),
            "clientInfo": {"name": "Serena", "version": "0.1.0"},
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "capabilities": {
                "window": {
                    "workDoneProgress": True,
                },
                "workspace": {
                    "workspaceEdit": {"documentChanges": True},
                    "configuration": True,
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {"dynamicRegistration": True},
                    "symbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                },
                "textDocument": {
                    "synchronization": {
                        "dynamicRegistration": True,
                        "willSave": True,
                        "willSaveWaitUntil": True,
                        "didSave": True,
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                        "hierarchicalDocumentSymbolSupport": True,
                    },
                    "implementation": {"dynamicRegistration": True, "linkSupport": True},
                    "publishDiagnostics": {"relatedInformation": True},
                },
            },
            "workspaceFolders": [{"uri": root_uri, "name": os.path.basename(repository_absolute_path)}],
        }
        return cast(InitializeParams, initialize_params)

    def _start_server(self) -> None:
        """
        Starts the pyrefly language server and waits for initial workspace indexing to complete.

        Pyrefly defers indexing until it receives a workspace/configuration response,
        then reports progress via $/progress notifications.
        """

        def execute_client_command_handler(params: dict) -> list:
            return []

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info("LSP: window/logMessage: %s", msg.get("message", ""))

        def workspace_configuration_handler(params: dict) -> list[dict]:
            items = params.get("items", []) if isinstance(params, dict) else []
            log.info("Pyrefly workspace/configuration request received: %d items", len(items))
            config = {
                "pythonPath": sys.executable,
                "pyrefly": {
                    # Ensure workspace-wide analysis parity with VSCode's project mode behavior.
                    "diagnosticMode": "workspace",
                },
            }
            return [config.copy() for _ in items]

        def work_done_progress_create(params: dict) -> None:
            return

        def on_progress(params: dict) -> None:
            token = params.get("token")
            value = params.get("value", {})
            kind = value.get("kind")
            if kind == "begin":
                self._active_progress_tokens.add(token)
                log.info("Pyrefly progress begin: %s (token=%s)", value.get("title", ""), token)
            elif kind == "end":
                self._active_progress_tokens.discard(token)
                log.info("Pyrefly progress end (token=%s)", token)
                if not self._active_progress_tokens:
                    self._indexing_complete.set()

        # setting up handlers
        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_request("workspace/configuration", workspace_configuration_handler)
        self.server.on_request("window/workDoneProgress/create", work_done_progress_create)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", on_progress)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        # starting and initializing the server
        log.info("Starting pyrefly language server process")
        self.server.start()
        # retry requests that pyrefly cancels while re-indexing the workspace in the background
        self._install_mutation_retry()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to pyrefly server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.info("Received initialize response from pyrefly server: %s", init_response)

        capabilities = init_response["capabilities"]
        assert "textDocumentSync" in capabilities
        assert "definitionProvider" in capabilities
        assert "referencesProvider" in capabilities
        assert "documentSymbolProvider" in capabilities

        # completing the initialization handshake
        self.server.notify.initialized({})

        # wait for pyrefly to finish initial workspace indexing
        log.info("Waiting for pyrefly to complete initial workspace indexing...")
        if self._indexing_complete.wait(timeout=30.0):
            log.info("Pyrefly initial indexing complete, server ready")
        else:
            log.warning("Timeout waiting for pyrefly indexing completion, proceeding anyway")
