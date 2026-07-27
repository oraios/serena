"""
Provides Gleam specific instantiation of the LanguageServer class.

The Gleam language server is bundled with the Gleam compiler and is started via
``gleam lsp``. No separate language-server package is required beyond the Gleam
compiler itself (https://gleam.run).
"""

import logging
import shutil
import subprocess
import threading

from overrides import override

from solidlsp.ls import (
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# Gleam LSP emits $/progress (begin/end) while resolving/downloading project
# dependencies on first start. Once dependencies are resolved, symbol, reference,
# hover and diagnostics queries are served synchronously — no further
# compile-wait or per-request retry is needed (this was verified against
# gleam 1.17 on Windows: cross-file references return immediately once the
# dependency-download progress phase ends).
_INITIAL_PROGRESS_BEGIN_TIMEOUT = 10  # seconds to wait for the first $/progress begin
_INITIAL_PROGRESS_IDLE_TIMEOUT = 180  # seconds to wait for all progress phases to end


class GleamLanguageServer(SolidLanguageServer):
    """
    Provides Gleam specific instantiation of the LanguageServer class.

    Uses the language server bundled with the Gleam compiler (``gleam lsp``).
    Requires the ``gleam`` binary to be installed and available on PATH; see
    https://gleam.run/getting-started/installing/ for installation instructions.

    The Gleam compiler is a self-contained Rust binary — neither Erlang/OTP nor
    a separate LSP package is required for symbol, reference, hover, definition,
    or diagnostics queries. (Full project compilation to BEAM bytecode does
    require Erlang, but the LSP's analysis path does not.)
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(config, repository_root_path, None, "gleam", solidlsp_settings)
        self._progress_lock = threading.Lock()
        self._active_progress_tokens: set[str | int] = set()
        self._first_progress_seen = threading.Event()
        self._idle = threading.Event()
        self._idle.set()  # optimistic: assume ready until a $/progress begin arrives

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Discover the Gleam compiler executable on PATH.

            :return: path to the ``gleam`` binary
            :raises FileNotFoundError: if ``gleam`` is neither on PATH nor provided via ``ls_path``
            """
            gleam_binary = shutil.which("gleam")
            if gleam_binary is None:
                raise FileNotFoundError(
                    "Gleam is not installed or not in PATH.\n"
                    "Please install the Gleam compiler from https://gleam.run/getting-started/installing/\n"
                    "and ensure the 'gleam' binary is available on your PATH.\n"
                    "The Gleam language server is bundled with the compiler and is started via `gleam lsp`."
                )
            return gleam_binary

        def _create_launch_command(self, core_path: str) -> list[str]:
            # `gleam lsp` runs the language server over stdio.
            return [core_path, "lsp"]

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # Gleam writes compiled output and downloaded dependencies under build/.
        return super().is_ignored_dirname(dirname) or dirname == "build"

    @override
    def _supports_pull_diagnostics(self) -> bool:
        # `gleam lsp` does not implement `textDocument/diagnostic` (LSP 3.17 pull diagnostics) and
        # advertises no `diagnosticProvider` capability. Sending a pull request would hang (the server
        # neither responds nor errors), so opt out and rely on `textDocument/publishDiagnostics` (push),
        # which the base class stores via `_observe_server_notification`.
        return False

    def _create_base_initialize_params(self) -> dict:
        """
        Return the language-specific initialize params for the Gleam language server.

        ``processId``, ``rootPath``, ``rootUri`` and ``workspaceFolders`` are populated by the
        default ``InitializeParamsBuilder`` and must not be set here.
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
        }

    def _download_dependencies(self) -> None:
        """Run ``gleam deps download`` so the stdlib is available before the LSP starts.

        Gleam LSP also fetches missing dependencies on start and reports progress via
        ``$/progress``; pre-fetching keeps the readiness wait short and avoids first-request
        races on slow CI runners.
        """
        gleam_path = shutil.which("gleam")
        if gleam_path is None:
            return  # _get_or_install_core_dependency will raise a clear error when the server starts
        try:
            result = subprocess.run(
                [gleam_path, "deps", "download"],
                cwd=self.repository_root_path,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if result.returncode != 0:
                log.warning("gleam deps download failed (exit %s): %s", result.returncode, result.stderr[:200])
            else:
                log.info("gleam deps download completed")
        except Exception as e:
            log.warning("Failed to run gleam deps download: %s", e)

    def _start_server(self) -> None:
        """Start the Gleam language server process."""

        def register_capability_handler(_params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info("LSP: window/logMessage: %s", msg)

        def on_progress(params: dict) -> None:
            token = params.get("token")
            value = params.get("value", {})
            if not isinstance(value, dict) or token is None:
                return
            kind = value.get("kind")
            with self._progress_lock:
                if kind == "begin":
                    self._active_progress_tokens.add(token)
                    self._first_progress_seen.set()
                    self._idle.clear()
                    log.info(
                        "Gleam LSP: progress begin (token=%s), active=%d",
                        token,
                        len(self._active_progress_tokens),
                    )
                elif kind == "end":
                    self._active_progress_tokens.discard(token)
                    if not self._active_progress_tokens:
                        self._idle.set()
                        log.info("Gleam LSP: all progress phases finished")

        def do_nothing(_params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", on_progress)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        # Pre-fetch dependencies so the LSP's own dependency-download phase is short.
        self._download_dependencies()

        log.info("Starting Gleam language server (gleam lsp) process")
        self.server.start()
        initialize_params = self._create_initialize_params()

        log.info("Sending initialize request to Gleam LSP and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        capabilities = init_response.get("capabilities", {}) if isinstance(init_response, dict) else {}
        log.info("Gleam LSP capabilities: %s", list(capabilities.keys()))

        self.server.notify.initialized({})

        # Wait for Gleam's initial dependency-download progress to finish.
        # Gleam emits $/progress begin/end for dependency resolution on first start; once all
        # phases end, queries are served synchronously. If no progress is reported within the
        # short begin-timeout, dependencies were already resolved and the server is ready.
        if not self._first_progress_seen.wait(timeout=_INITIAL_PROGRESS_BEGIN_TIMEOUT):
            log.info(
                "Gleam LSP: no $/progress within %ss, assuming ready (dependencies already resolved)",
                _INITIAL_PROGRESS_BEGIN_TIMEOUT,
            )
        elif not self._idle.wait(timeout=_INITIAL_PROGRESS_IDLE_TIMEOUT):
            log.warning(
                "Gleam LSP: timed out waiting for initial progress after %ss, proceeding anyway",
                _INITIAL_PROGRESS_IDLE_TIMEOUT,
            )

        log.info("Gleam language server ready")
