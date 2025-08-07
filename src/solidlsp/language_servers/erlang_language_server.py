"""Erlang Language Server implementation using Erlang LS."""

import shutil
import subprocess

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


class ErlangLanguageServer(SolidLanguageServer):
    """Language server for Erlang using Erlang LS."""

    def __init__(
        self,
        config: LanguageServerConfig,
        logger: LanguageServerLogger,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
    ):
        """
        Creates an ErlangLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        self.erlang_ls_path = shutil.which("erlang_ls")
        if not self.erlang_ls_path:
            raise RuntimeError("Erlang LS not found. Install from: https://github.com/erlang-ls/erlang_ls")

        if not self._check_erlang_installation():
            raise RuntimeError("Erlang/OTP not found. Install from: https://www.erlang.org/downloads")

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=[self.erlang_ls_path, "--transport", "stdio"], cwd=repository_root_path),
            "erlang",
            solidlsp_settings,
        )

    def _check_erlang_installation(self) -> bool:
        """Check if Erlang/OTP is available."""
        try:
            result = subprocess.run(["erl", "-version"], check=False, capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def _start_server(self):
        """Start the Erlang LS language server process."""
        return self.server.start()
