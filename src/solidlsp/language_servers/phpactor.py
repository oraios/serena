"""
Provides PHP specific instantiation of the LanguageServer class using Phpactor.
"""

import logging
import os
import pathlib
import re
import shutil
import stat
import subprocess

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_utils import FileUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

PHPACTOR_ALLOWED_HOSTS = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_PHPACTOR_VERSION = "2025.12.21.1"
INITIAL_PHPACTOR_PHAR_SHA256 = "53bbe9625cd9b5e9b394bc2f595fbad13dbbe6dfc96950c56dea3b5d9a246cc3"
DEFAULT_PHPACTOR_VERSION = "2025.12.21.1"
DEFAULT_PHPACTOR_PHAR_SHA256 = "53bbe9625cd9b5e9b394bc2f595fbad13dbbe6dfc96950c56dea3b5d9a246cc3"


def _phpactor_sha(version: str) -> str | None:
    if version == INITIAL_PHPACTOR_VERSION:
        return INITIAL_PHPACTOR_PHAR_SHA256
    if version == DEFAULT_PHPACTOR_VERSION:
        return DEFAULT_PHPACTOR_PHAR_SHA256
    return None


class PhpactorServer(SolidLanguageServer):
    """
    Provides PHP specific instantiation of the LanguageServer class using Phpactor.

    Phpactor is an open-source (MIT) PHP language server that requires PHP 8.1+ on the system.
    It is an alternative to Intelephense, which is the default PHP language server.

    You can pass the following entries in ls_specific_settings["php_phpactor"]:
        - ignore_vendor: whether to ignore directories named "vendor" (default: true)
        - phpactor_version: Override the pinned Phpactor PHAR version downloaded by
          Serena (default: the bundled Serena version)
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in self._ignored_dirnames

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Setup runtime dependencies for Phpactor and return the path to the PHAR file.
            """
            phpactor_version = self._custom_settings.get("phpactor_version", DEFAULT_PHPACTOR_VERSION)
            phpactor_phar_url = f"https://github.com/phpactor/phpactor/releases/download/{phpactor_version}/phpactor.phar"
            # Verify PHP is installed
            php_path = shutil.which("php")
            assert php_path is not None, (
                "PHP is not installed or not found in PATH. Phpactor requires PHP 8.1+. Please install PHP and try again."
            )

            # Check PHP version (Phpactor requires PHP 8.1+)
            result = subprocess.run(["php", "--version"], capture_output=True, text=True, check=False)
            php_version_output = result.stdout.strip()
            log.info(f"PHP version: {php_version_output}")
            version_match = re.search(r"PHP (\d+)\.(\d+)", php_version_output)
            if version_match:
                major, minor = int(version_match.group(1)), int(version_match.group(2))
                if major < 8 or (major == 8 and minor < 1):
                    raise RuntimeError(f"PHP {major}.{minor} detected, but Phpactor requires PHP 8.1+. Please upgrade PHP.")
            else:
                log.warning("Could not parse PHP version from output. Continuing anyway.")

            # legacy unversioned phar at root reserved for INITIAL; every other version goes into a versioned subdir
            if phpactor_version == INITIAL_PHPACTOR_VERSION:
                phar_dir = self._ls_resources_dir
            else:
                phar_dir = os.path.join(self._ls_resources_dir, f"phpactor-{phpactor_version}")
            phpactor_phar_path = os.path.join(phar_dir, "phpactor.phar")
            if not os.path.exists(phpactor_phar_path):
                os.makedirs(phar_dir, exist_ok=True)
                log.info(f"Downloading phpactor PHAR from {phpactor_phar_url}")
                FileUtils.download_and_extract_archive_verified(
                    phpactor_phar_url,
                    phpactor_phar_path,
                    "binary",
                    expected_sha256=_phpactor_sha(phpactor_version),
                    allowed_hosts=PHPACTOR_ALLOWED_HOSTS,
                )

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
