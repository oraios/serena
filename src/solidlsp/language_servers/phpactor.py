"""
Provides PHP specific instantiation of the LanguageServer class using Phpactor.
"""

import logging
import os
import pathlib
import shutil
import stat

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_utils import FileUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

PHPACTOR_VERSION = "2025.12.21.1"
PHPACTOR_PHAR_URL = f"https://github.com/phpactor/phpactor/releases/download/{PHPACTOR_VERSION}/phpactor.phar"


class PhpactorServer(SolidLanguageServer):
    """
    Provides PHP specific instantiation of the LanguageServer class using Phpactor.

    Phpactor is an open-source (MIT) PHP language server that requires PHP 8.1+ on the system.
    It is an alternative to Intelephense, which is the default PHP language server.

    You can pass the following entries in ls_specific_settings["php_phpactor"]:
        - ignore_vendor: whether to ignore directories named "vendor" (default: true)
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in self._ignored_dirnames

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Setup runtime dependencies for Phpactor and return the path to the PHAR file.
            """
            # Verify PHP is installed
            php_path = shutil.which("php")
            assert (
                php_path is not None
            ), "PHP is not installed or not found in PATH. Phpactor requires PHP 8.1+. Please install PHP and try again."

            phpactor_phar_path = os.path.join(self._ls_resources_dir, "phpactor.phar")
            if not os.path.exists(phpactor_phar_path):
                os.makedirs(self._ls_resources_dir, exist_ok=True)
                log.info(f"Downloading phpactor PHAR from {PHPACTOR_PHAR_URL}")
                FileUtils.download_and_extract_archive(PHPACTOR_PHAR_URL, phpactor_phar_path, "binary")

            assert os.path.exists(phpactor_phar_path), f"phpactor PHAR not found at {phpactor_phar_path}, download may have failed."

            # Ensure the PHAR is executable
            current_mode = os.stat(phpactor_phar_path).st_mode
            os.chmod(phpactor_phar_path, current_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

            return phpactor_phar_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return ["php", core_path, "language-server"]

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(config, repository_root_path, None, "php", solidlsp_settings)
        # Override internal language enum for correct file matching
        self.language = Language.PHP_PHPACTOR

        self._ignored_dirnames = {"node_modules", "cache"}
        if self._custom_settings.get("ignore_vendor", True):
            self._ignored_dirnames.add("vendor")
        log.info(f"Ignoring the following directories for PHP (Phpactor): {', '.join(sorted(self._ignored_dirnames))}")

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialization params for the Phpactor Language Server.
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
                    "documentSymbol": {
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                },
            },
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
            "initializationOptions": {
                "language_server_phpstan.enabled": False,
                "language_server_psalm.enabled": False,
                "language_server_php_cs_fixer.enabled": False,
            },
        }
        return initialize_params  # type: ignore

    def _start_server(self) -> None:
        """Start Phpactor server process."""

        def register_capability_handler(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Phpactor server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.info("After sent initialize params")

        # Verify server capabilities
        assert "capabilities" in init_response
        assert init_response["capabilities"].get("definitionProvider"), "Phpactor did not advertise definition support"

        self.server.notify.initialized({})
