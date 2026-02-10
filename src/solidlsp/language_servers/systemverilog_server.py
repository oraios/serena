"""
SystemVerilog language server using verible-verilog-ls.
"""

import logging
import os
import pathlib
import shutil
import subprocess
import threading
from typing import Any, cast

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)


class SystemVerilogLanguageServer(SolidLanguageServer):
    """
    SystemVerilog language server using verible-verilog-ls.
    Supports .sv, .svh, .v, .vh files.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings) -> None:
        super().__init__(config, repository_root_path, None, "systemverilog", solidlsp_settings)
        self.server_ready = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            # 1. Check PATH first for system-installed verible
            system_verible = shutil.which("verible-verilog-ls")
            if system_verible:
                # Log version information
                try:
                    result = subprocess.run(
                        [system_verible, "--version"],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        version_info = result.stdout.strip().split("\n")[0]
                        log.info(f"Using system-installed verible-verilog-ls: {version_info}")
                    else:
                        log.info(f"Using system-installed verible-verilog-ls at {system_verible}")
                except Exception:
                    log.info(f"Using system-installed verible-verilog-ls at {system_verible}")
                return system_verible

            # 2. Not found in PATH, try to download
            deps = RuntimeDependencyCollection(
                [
                    RuntimeDependency(
                        id="verible-ls",
                        description="verible-verilog-ls for Linux (x64)",
                        url="https://github.com/chipsalliance/verible/releases/download/v0.0-4051-g9fdb4057/verible-v0.0-4051-g9fdb4057-linux-static-x86_64.tar.gz",
                        platform_id="linux-x64",
                        archive_type="gztar",
                        binary_name="verible-v0.0-4051-g9fdb4057/bin/verible-verilog-ls",
                    ),
                    RuntimeDependency(
                        id="verible-ls",
                        description="verible-verilog-ls for Linux (arm64)",
                        url="https://github.com/chipsalliance/verible/releases/download/v0.0-4051-g9fdb4057/verible-v0.0-4051-g9fdb4057-linux-static-arm64.tar.gz",
                        platform_id="linux-arm64",
                        archive_type="gztar",
                        binary_name="verible-v0.0-4051-g9fdb4057/bin/verible-verilog-ls",
                    ),
                    RuntimeDependency(
                        id="verible-ls",
                        description="verible-verilog-ls for macOS",
                        url="https://github.com/chipsalliance/verible/releases/download/v0.0-4051-g9fdb4057/verible-v0.0-4051-g9fdb4057-macOS.tar.gz",
                        platform_id="osx-x64",
                        archive_type="gztar",
                        binary_name="verible-v0.0-4051-g9fdb4057/bin/verible-verilog-ls",
                    ),
                    RuntimeDependency(
                        id="verible-ls",
                        description="verible-verilog-ls for macOS",
                        url="https://github.com/chipsalliance/verible/releases/download/v0.0-4051-g9fdb4057/verible-v0.0-4051-g9fdb4057-macOS.tar.gz",
                        platform_id="osx-arm64",
                        archive_type="gztar",
                        binary_name="verible-v0.0-4051-g9fdb4057/bin/verible-verilog-ls",
                    ),
                    RuntimeDependency(
                        id="verible-ls",
                        description="verible-verilog-ls for Windows (x64)",
                        url="https://github.com/chipsalliance/verible/releases/download/v0.0-4051-g9fdb4057/verible-v0.0-4051-g9fdb4057-win64.zip",
                        platform_id="win-x64",
                        archive_type="zip",
                        binary_name="verible-v0.0-4051-g9fdb4057/bin/verible-verilog-ls.exe",
                    ),
                ]
            )

            try:
                dep = deps.get_single_dep_for_current_platform()
            except RuntimeError:
                dep = None

            if dep is None:
                raise FileNotFoundError(
                    "verible-verilog-ls is not installed on your system.\n"
                    + "Please install verible manually or use a supported platform.\n"
                    + "See https://github.com/chipsalliance/verible for installation instructions."
                )

            verible_ls_dir = os.path.join(self._ls_resources_dir, "verible-ls")
            executable_path = deps.binary_path(verible_ls_dir)

            if not os.path.exists(executable_path):
                log.info(f"verible-verilog-ls not found. Downloading from {dep.url}")
                _ = deps.install(verible_ls_dir)

            if not os.path.exists(executable_path):
                raise FileNotFoundError(f"verible-verilog-ls not found at {executable_path}")

            os.chmod(executable_path, 0o755)
            return executable_path

        def _create_launch_command(self, core_path: str) -> list[str] | str:
            return [core_path]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {"snippetSupport": True},
                    },
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"],
                    },
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                },
            },
            "workspaceFolders": [{"uri": root_uri, "name": os.path.basename(repository_absolute_path)}],
        }
        return cast(InitializeParams, initialize_params)

    def _start_server(self) -> None:
        def do_nothing(params: Any) -> None:
            return

        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting verible-verilog-ls process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request")
        init_response = self.server.send.initialize(initialize_params)
        log.info(f"Initialize response capabilities: {init_response.get('capabilities', {}).keys()}")

        self.server.notify.initialized({})
        self.server_ready.set()
        self.server_ready.wait()
