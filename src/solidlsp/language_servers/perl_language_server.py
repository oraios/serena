"""
Provides Perl specific instantiation of the LanguageServer class using Perl::LanguageServer.
Perl::LanguageServer: https://github.com/richterger/Perl-LanguageServer
"""

import logging
import os
import pathlib
import shutil
import subprocess
import time

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


class PerlLanguageServer(SolidLanguageServer):
    """
    Provides Perl specific instantiation of the LanguageServer class using Perl::LanguageServer.
    Perl::LanguageServer supports Go to definition, Find references, Document symbols, and more.
    """

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
    def _setup_runtime_dependencies(
        cls, logger: LanguageServerLogger, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings
    ) -> str:
        """
        Setup runtime dependencies for Perl::LanguageServer and return the command to start the server.
        """
        platform_id = PlatformUtils.get_platform_id()

        valid_platforms = [
            PlatformId.LINUX_x64,
            PlatformId.LINUX_arm64,
            PlatformId.OSX,
            PlatformId.OSX_x64,
            PlatformId.OSX_arm64,
            PlatformId.WIN_x64,
            PlatformId.WIN_arm64,
        ]
        assert platform_id in valid_platforms, f"Platform {platform_id} is not supported for Perl at the moment"

        # Verify perl is installed
        is_perl_installed = shutil.which("perl") is not None
        assert is_perl_installed, "perl is not installed or isn't in PATH. Please install Perl and try again."

        # Check if Perl::LanguageServer is already installed
        try:
            result = subprocess.run(
                ["perl", "-MPerl::LanguageServer", "-e", "1"],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                logger.log("Perl::LanguageServer is already installed", logging.INFO)
            else:
                # Install Perl::LanguageServer using cpanm if available, otherwise cpan
                logger.log("Installing Perl::LanguageServer...", logging.INFO)

                # Check if cpanm is available (faster and more user-friendly)
                cpanm_available = shutil.which("cpanm") is not None

                if cpanm_available:
                    install_cmd = ["cpanm", "--notest", "Perl::LanguageServer"]
                else:
                    # Fall back to cpan (requires CPAN to be configured)
                    install_cmd = ["cpan", "Perl::LanguageServer"]

                try:
                    subprocess.run(install_cmd, check=True, capture_output=True, text=True)
                    logger.log("Perl::LanguageServer installed successfully", logging.INFO)
                except subprocess.CalledProcessError as e:
                    error_msg = e.stderr if e.stderr else str(e)
                    raise RuntimeError(
                        f"Failed to install Perl::LanguageServer: {error_msg}\n"
                        "Please try installing manually: cpanm Perl::LanguageServer"
                    ) from e

        except FileNotFoundError as e:
            raise RuntimeError("Perl is not installed or not found in PATH. Please install Perl and try again.") from e

        # Return the command to run Perl::LanguageServer with logging options
        # Use -- to separate Perl options from program arguments (which go into @ARGV)
        return "perl -MPerl::LanguageServer -e 'Perl::LanguageServer::run' -- --log-level 2 --log-file /tmp/perl_language_server.log"

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        # Setup runtime dependencies before initializing
        perl_ls_cmd = self._setup_runtime_dependencies(logger, config, solidlsp_settings)

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=perl_ls_cmd, cwd=repository_root_path),
            "perl",
            solidlsp_settings,
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

        return initialize_params

    def _start_server(self):
        """Start Perl::LanguageServer process"""

        def register_capability_handler(params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        def do_nothing(params):
            return

        def workspace_configuration_handler(params):
            """Handle workspace/configuration request from Perl::LanguageServer."""
            # Perl::LanguageServer requests configuration with items like: [{section: 'perl'}]
            # We need to return an array of configuration objects matching the request
            self.logger.log(f"Received workspace/configuration request: {params}", logging.INFO)

            perl_config = {
                "perlInc": [self.repository_root_path, "."],
                "fileFilter": [".pm", ".pl"],
                "ignoreDirs": [".git", ".svn", "blib", "local", ".carton", "vendor", "_build", "cover_db"],
            }

            # Return array matching the request items
            # Typically one item for 'perl' section
            return [perl_config]

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("workspace/configuration", workspace_configuration_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting Perl::LanguageServer process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)
        self.logger.log(
            "After sent initialize params",
            logging.INFO,
        )

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        # Perl::LanguageServer should support definition and references
        if "definitionProvider" in init_response["capabilities"]:
            self.logger.log("Perl::LanguageServer definition provider is available", logging.INFO)
        if "referencesProvider" in init_response["capabilities"]:
            self.logger.log("Perl::LanguageServer references provider is available", logging.INFO)

        self.server.notify.initialized({})

        # Send workspace configuration to Perl::LanguageServer
        # Perl::LanguageServer requires didChangeConfiguration to set perlInc, fileFilter, and ignoreDirs
        # See: Perl::LanguageServer::Methods::workspace::_rpcnot_didChangeConfiguration
        perl_config = {
            "settings": {
                "perl": {
                    "perlInc": [self.repository_root_path, "."],
                    "fileFilter": [".pm", ".pl"],
                    "ignoreDirs": [".git", ".svn", "blib", "local", ".carton", "vendor", "_build", "cover_db"],
                }
            }
        }
        self.logger.log(f"Sending workspace/didChangeConfiguration notification with config: {perl_config}", logging.INFO)
        self.server.notify.workspace_did_change_configuration(perl_config)

        self.completions_available.set()

        # Perl::LanguageServer needs time to index files and resolve cross-file references
        # Without this delay, requests for definitions/references may return empty results
        settling_time = 0.5
        self.logger.log(f"Allowing {settling_time} seconds for Perl::LanguageServer to index files...", logging.INFO)
        time.sleep(settling_time)
        self.logger.log("Perl::LanguageServer settling period complete", logging.INFO)
