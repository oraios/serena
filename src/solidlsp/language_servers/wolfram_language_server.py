"""Wolfram Language server integration using the official WolframResearch LSPServer paclet."""

import glob
import logging
import os
import pathlib
import platform
import shlex
import shutil
from typing import Any

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

WOLFRAM_PATH_ENV_VAR = "WOLFRAM_PATH"


class WolframLanguageServer(SolidLanguageServer):
    """
    Wolfram Language server using the official WolframResearch LSPServer paclet.

    Requires Wolfram Mathematica 13.0+ or Wolfram Engine 12.1+.
    Configure wolfram_kernel_path in ls_specific_settings or set WOLFRAM_PATH env var.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        from solidlsp.ls_config import Language

        custom_settings = solidlsp_settings.get_ls_specific_settings(Language.WOLFRAM)
        kernel_path = self._find_wolfram_kernel(custom_settings)

        # The command must use shlex.quote because Serena launches processes via shell=True,
        # and Wolfram context marks contain backticks (e.g. LSPServer`) which the shell
        # would interpret as command substitution.
        wolfram_code = 'Needs["LSPServer`"];LSPServer`StartServer[]'

        wolfram_ls_cmd: str | list[str]
        if platform.system() == "Windows":
            wolfram_ls_cmd = [kernel_path, "-noprompt", "-noinit", "-run", wolfram_code]
        else:
            wolfram_ls_cmd = f"{shlex.quote(kernel_path)} -noprompt -noinit -run {shlex.quote(wolfram_code)}"

        log.info(f"Wolfram LSP launch command: {wolfram_ls_cmd}")

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=wolfram_ls_cmd, cwd=repository_root_path),
            "wolfram",
            solidlsp_settings,
        )

        # The Wolfram kernel's LSPServer paclet crashes if the standard `Content-Type`
        # header is included in the JSON-RPC message. We monkey-patch `_send_payload`
        # locally to cleanly omit it without affecting global message formatting in other servers.
        def _wolfram_custom_send_payload(payload: Any) -> None:
            if not self.server.process or not self.server.process.stdin:
                return
            self.server._trace("solidlsp", "ls", payload)

            import json

            from solidlsp.lsp_protocol_handler.server import ENCODING

            body = json.dumps(payload, check_circular=False, ensure_ascii=False, separators=(",", ":")).encode(ENCODING)

            # Note the omission of the Content-Type header! Only Content-Length is sent.
            msg = (
                f"Content-Length: {len(body)}\r\n\r\n".encode(ENCODING),
                body,
            )

            with self.server._stdin_lock:
                self.server.process.stdin.write(b"".join(msg))
                self.server.process.stdin.flush()

        self.server._send_payload = _wolfram_custom_send_payload  # type: ignore[method-assign]

    @staticmethod
    def _find_wolfram_kernel(custom_settings: SolidLSPSettings.CustomLSSettings) -> str:
        """Find the WolframKernel executable."""
        # 1. Custom settings
        custom_path = custom_settings.get("wolfram_kernel_path")
        if custom_path and os.path.isfile(custom_path) and os.access(custom_path, os.X_OK):
            log.info(f"Using WolframKernel from custom settings: {custom_path}")
            return custom_path

        # 2. WOLFRAM_PATH environment variable
        env_path = os.environ.get(WOLFRAM_PATH_ENV_VAR)
        if env_path:
            if os.path.isfile(env_path) and os.access(env_path, os.X_OK):
                log.info(f"Using WolframKernel from {WOLFRAM_PATH_ENV_VAR}: {env_path}")
                return env_path
            kernel_in_dir = _find_kernel_in_install_dir(env_path)
            if kernel_in_dir:
                log.info(f"Using WolframKernel from {WOLFRAM_PATH_ENV_VAR} directory: {kernel_in_dir}")
                return kernel_in_dir

        # 3. System PATH
        kernel_path = shutil.which("WolframKernel")
        if kernel_path:
            log.info(f"Using WolframKernel from PATH: {kernel_path}")
            return kernel_path

        # 4. Common installation locations
        system = platform.system()
        search_locations: list[str] = []

        if system == "Darwin":
            search_locations = [
                "/Applications/Mathematica.app/Contents/MacOS/WolframKernel",
                "/Applications/Wolfram.app/Contents/MacOS/WolframKernel",
                "/Applications/Wolfram Engine.app/Contents/MacOS/WolframKernel",
            ]
            for pattern in [
                "/Applications/Mathematica*.app/Contents/MacOS/WolframKernel",
                "/Applications/Wolfram*.app/Contents/MacOS/WolframKernel",
            ]:
                search_locations.extend(sorted(glob.glob(pattern), reverse=True))

        elif system == "Linux":
            search_locations = [
                "/usr/local/bin/WolframKernel",
                "/usr/bin/WolframKernel",
            ]
            for pattern in [
                "/usr/local/Wolfram/Mathematica/*/Executables/WolframKernel",
                "/usr/local/Wolfram/WolframEngine/*/Executables/WolframKernel",
                "/opt/Wolfram/Mathematica/*/Executables/WolframKernel",
            ]:
                search_locations.extend(sorted(glob.glob(pattern), reverse=True))

        elif system == "Windows":
            for pattern in [
                "C:\\Program Files\\Wolfram Research\\Mathematica\\*\\WolframKernel.exe",
                "C:\\Program Files\\Wolfram Research\\Wolfram Engine\\*\\WolframKernel.exe",
            ]:
                search_locations.extend(sorted(glob.glob(pattern), reverse=True))

        for location in search_locations:
            if os.path.isfile(location) and os.access(location, os.X_OK):
                log.info(f"Found WolframKernel at: {location}")
                return location

        raise RuntimeError(
            "WolframKernel not found. Please either:\n"
            f"1. Set the {WOLFRAM_PATH_ENV_VAR} environment variable to your Wolfram installation\n"
            "2. Add WolframKernel to your system PATH\n"
            "3. Configure wolfram_kernel_path in ls_specific_settings\n"
            "4. Install Wolfram Mathematica (13.0+) or Wolfram Engine (12.1+) from https://www.wolfram.com/"
        )

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            ".Wolfram",
            "SystemFiles",
            "Documentation",
            "FrontEnd",
        ]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "capabilities": {
                "workspace": {"workspaceFolders": True},
                "textDocument": {
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "formatting": {"dynamicRegistration": True},
                    "publishDiagnostics": {"relatedInformation": True},
                },
            },
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }
        return initialize_params  # type: ignore

    def _start_server(self) -> None:
        def do_nothing(params: Any) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"Wolfram LSP: window/logMessage: {msg}")

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Wolfram LSPServer process")
        self.server.start()

        initialize_params = self._get_initialize_params(self.repository_root_path)
        init_response = self.server.send.initialize(initialize_params)

        log.info(f"Wolfram LSP capabilities: {list(init_response.get('capabilities', {}).keys())}")

        self.server.notify.initialized({})
        log.info("Wolfram LSPServer initialized and ready.")


def _find_kernel_in_install_dir(install_dir: str) -> str | None:
    """Try to locate WolframKernel within a Wolfram installation directory."""
    system = platform.system()

    if system == "Darwin":
        candidates = [
            os.path.join(install_dir, "Contents", "MacOS", "WolframKernel"),
            os.path.join(install_dir, "MacOS", "WolframKernel"),
        ]
    elif system == "Windows":
        candidates = [
            os.path.join(install_dir, "WolframKernel.exe"),
        ]
    else:
        candidates = [
            os.path.join(install_dir, "Executables", "WolframKernel"),
            os.path.join(install_dir, "WolframKernel"),
        ]

    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    return None
