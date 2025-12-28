"""
Provides Perl specific instantiation of the LanguageServer class using Perl::LanguageServer.

Note: Windows is not supported as Nix itself doesn't support Windows natively.
"""

import logging
import os
import pathlib
import subprocess
import time
from typing import Any

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import DidChangeConfigurationParams, InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class PerlLanguageServer(SolidLanguageServer):
    """
    Provides Perl specific instantiation of the LanguageServer class using Perl::LanguageServer.
    """

    @staticmethod
    def _get_perl_version() -> str | None:
        """Get the installed Perl version or None if not found."""
        try:
            result = subprocess.run(["perl", "-v"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        return None

    @staticmethod
    def _get_perl_language_server_version() -> str | None:
        """Get the installed Perl::LanguageServer version or None if not found."""
        try:
            result = subprocess.run(
                ["perl", "-MPerl::LanguageServer", "-e", "print $Perl::LanguageServer::VERSION"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        return None

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For Perl projects, we should ignore:
        # - blib: build library directory
        # - local: local Perl module installation
        # - .carton: Carton dependency manager cache
        # - vendor: vendored dependencies
        # - _build: Module::Build output
        return super().is_ignored_dirname(dirname) or dirname in ["blib", "local", ".carton", "vendor", "_build", "cover_db"]

    @classmethod
    def _setup_runtime_dependencies(cls) -> str:
        """
        Check if required Perl runtime dependencies are available.
        Raises RuntimeError with helpful message if dependencies are missing.
        """
        platform_id = PlatformUtils.get_platform_id()

        valid_platforms = [
            PlatformId.LINUX_x64,
            PlatformId.LINUX_arm64,
            PlatformId.OSX,
            PlatformId.OSX_x64,
            PlatformId.OSX_arm64,
        ]
        if platform_id not in valid_platforms:
            raise RuntimeError(f"Platform {platform_id} is not supported for Perl at the moment")

        perl_version = cls._get_perl_version()
        if not perl_version:
            raise RuntimeError(
                "Perl is not installed. Please install Perl from https://www.perl.org/get.html and make sure it is added to your PATH."
            )

        perl_ls_version = cls._get_perl_language_server_version()
        if not perl_ls_version:
            raise RuntimeError(
                "Found a Perl version but Perl::LanguageServer is not installed.\n"
                "Please install Perl::LanguageServer: cpanm Perl::LanguageServer\n"
                "See: https://metacpan.org/pod/Perl::LanguageServer"
            )

        return "perl -MPerl::LanguageServer -e 'Perl::LanguageServer::run'"

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        # Setup runtime dependencies before initializing
        perl_ls_cmd = self._setup_runtime_dependencies()

        super().__init__(
            config, repository_root_path, ProcessLaunchInfo(cmd=perl_ls_cmd, cwd=repository_root_path), "perl", solidlsp_settings
        )
        self.request_id = 0

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for Perl::LanguageServer.
        Based on the expected structure from Perl::LanguageServer::Methods::_rpcreq_initialize.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {"dynamicRegistration": True},
                    "hover": {"dynamicRegistration": True},
                    "inlayHint": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "initializationOptions": {},
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }

        return initialize_params  # type: ignore

    def _start_server(self) -> None:
        """Start Perl::LanguageServer process"""

        def register_capability_handler(params: Any) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(params: Any) -> None:
            return

        def workspace_configuration_handler(params: Any) -> Any:
            """Handle workspace/configuration request from Perl::LanguageServer."""
            log.info(f"Received workspace/configuration request: {params}")

            perl_config = {
                "perlInc": [self.repository_root_path, "."],
                "fileFilter": [".pm", ".pl"],
                "ignoreDirs": [".git", ".svn", "blib", "local", ".carton", "vendor", "_build", "cover_db"],
            }

            return [perl_config]

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("workspace/configuration", workspace_configuration_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Perl::LanguageServer process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.info(
            "After sent initialize params",
        )

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]
        assert "referencesProvider" in init_response["capabilities"]

        self.server.notify.initialized({})

        # Send workspace configuration to Perl::LanguageServer
        # Perl::LanguageServer requires didChangeConfiguration to set perlInc, fileFilter, and ignoreDirs
        # See: Perl::LanguageServer::Methods::workspace::_rpcnot_didChangeConfiguration
        perl_config: DidChangeConfigurationParams = {
            "settings": {
                "perl": {
                    "perlInc": [self.repository_root_path, "."],
                    "fileFilter": [".pm", ".pl"],
                    "ignoreDirs": [".git", ".svn", "blib", "local", ".carton", "vendor", "_build", "cover_db"],
                }
            }
        }
        log.info(f"Sending workspace/didChangeConfiguration notification with config: {perl_config}")
        self.server.notify.workspace_did_change_configuration(perl_config)

        self.completions_available.set()

        # Perl::LanguageServer needs time to index files and resolve cross-file references
        # Without this delay, requests for definitions/references may return empty results
        settling_time = 0.5
        log.info(f"Allowing {settling_time} seconds for Perl::LanguageServer to index files...")
        time.sleep(settling_time)
        log.info("Perl::LanguageServer settling period complete")
