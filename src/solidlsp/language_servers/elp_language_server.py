"""Erlang Language Server implementation using ELP (Erlang Language Platform).

ELP is the successor to the archived erlang_ls project. It was designed at WhatsApp,
inspired by rust-analyzer, and provides scalable, fully incremental IDE features for
Erlang code.

Installation: https://whatsapp.github.io/erlang-language-platform/docs/get-started/
"""

import logging
import os
import pathlib
import shutil
import subprocess

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class ErlangLanguagePlatform(SolidLanguageServer):
    """Language server for Erlang using ELP (Erlang Language Platform).

    ELP is the successor to the archived erlang_ls project. It provides
    go-to-definition, find references, call hierarchy and more via the
    Language Server Protocol.

    The ELP binary (``elp``) must be installed and available in ``PATH``.
    See https://whatsapp.github.io/erlang-language-platform/docs/get-started/
    for installation instructions.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        elp_path = self._find_elp()
        if not elp_path:
            raise RuntimeError(
                "ELP (Erlang Language Platform) binary 'elp' not found.\n"
                "Please install ELP and ensure 'elp' is available in your PATH.\n"
                "Installation: https://whatsapp.github.io/erlang-language-platform/docs/get-started/\n"
                "Alternatively, use the legacy 'erlang_ls' language server by setting "
                "'language: erlang_ls' in your project.yml (not recommended, archived project)."
            )

        if not self._check_erlang_installation():
            raise RuntimeError(
                "Erlang/OTP not found. ELP requires Erlang/OTP to be installed.\n"
                "Install from: https://www.erlang.org/downloads\n"
                "Or use your package manager: brew install erlang / apt-get install erlang"
            )

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=[elp_path, "server"], cwd=repository_root_path),
            "erlang",
            solidlsp_settings,
        )

    @staticmethod
    def _find_elp() -> str | None:
        """Return the path to the ``elp`` binary, or ``None`` if not found."""
        return shutil.which("elp")

    @staticmethod
    def _check_erlang_installation() -> bool:
        """Check that Erlang/OTP is available (required by ELP at runtime)."""
        try:
            result = subprocess.run(["erl", "-version"], check=False, capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """Return initialize params for ELP."""
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
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "deprecatedSupport": True,
                            "preselectSupport": True,
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
                    "symbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                },
            },
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }

    def _start_server(self) -> None:
        """Start the ELP server process."""

        def register_capability_handler(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"ELP: window/logMessage: {msg.get('message', msg)}")

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("window/workDoneProgress/create", do_nothing)

        log.info("Starting ELP (Erlang Language Platform) server")
        self.server.start()

        initialize_params = self._get_initialize_params(self.repository_root_path)
        log.info("Sending initialize request to ELP")
        init_response = self.server.send.initialize(initialize_params)  # type: ignore[arg-type]

        if "capabilities" in init_response:
            log.info(f"ELP capabilities: {list(init_response['capabilities'].keys())}")

        self.server.notify.initialized({})
        log.info("ELP server initialized and ready")

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # Erlang build artifacts and tooling directories
        return super().is_ignored_dirname(dirname) or dirname in [
            "_build",
            "deps",
            "ebin",
            ".rebar3",
            "logs",
            "_checkouts",
            "cover",
            "node_modules",
        ]

    def is_ignored_filename(self, filename: str) -> bool:
        # Ignore compiled BEAM files
        return filename.endswith(".beam")
