"""
Provides PHP specific instantiation of the LanguageServer class using Intelephense.
"""

import logging
import os
import pathlib
import shutil
from time import sleep

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import Definition, DefinitionParams, InitializeParams, LocationLink
from solidlsp.settings import SolidLSPSettings

from ..lsp_protocol_handler import lsp_types
from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)


class Intelephense(SolidLanguageServer):
    """
    Provides PHP specific instantiation of the LanguageServer class using Intelephense.

    You can pass the following entries in ls_specific_settings["php"]:
        - maxMemory: sets intelephense.maxMemory
        - maxFileSize: sets intelephense.files.maxSize
        - ignore_vendor: whether or ignore directories named "vendor" (default: true)
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in self._ignored_dirnames

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Setup runtime dependencies for Intelephense and return the path to the executable.
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
            assert platform_id in valid_platforms, f"Platform {platform_id} is not supported by Intelephense at the moment"

            # Verify both node and npm are installed
            is_node_installed = shutil.which("node") is not None
            assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
            is_npm_installed = shutil.which("npm") is not None
            assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."

            # Install intelephense if not already installed
            intelephense_ls_dir = os.path.join(self._ls_resources_dir, "php-lsp")
            os.makedirs(intelephense_ls_dir, exist_ok=True)
            intelephense_executable_path = os.path.join(intelephense_ls_dir, "node_modules", ".bin", "intelephense")
            if not os.path.exists(intelephense_executable_path):
                deps = RuntimeDependencyCollection(
                    [
                        RuntimeDependency(
                            id="intelephense",
                            command="npm install --prefix ./ intelephense@1.14.4",
                            platform_id="any",
                        )
                    ]
                )
                deps.install(intelephense_ls_dir)

            assert os.path.exists(
                intelephense_executable_path
            ), f"intelephense executable not found at {intelephense_executable_path}, something went wrong."

            return intelephense_executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "--stdio"]

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(config, repository_root_path, None, "php", solidlsp_settings)
        self.request_id = 0

        # For PHP projects, we should ignore:
        # - node_modules: if the project has JavaScript components
        # - cache: commonly used for caching
        # - (configurable) vendor: third-party dependencies managed by Composer
        self._ignored_dirnames = {"node_modules", "cache"}
        if self._custom_settings.get("ignore_vendor", True):
            self._ignored_dirnames.add("vendor")
        log.info(f"Ignoring the following directories for PHP projects: {', '.join(sorted(self._ignored_dirnames))}")

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialization params for the Intelephense Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
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
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
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
        initialization_options = {}
        # Add license key if provided via environment variable
        license_key = os.environ.get("INTELEPHENSE_LICENSE_KEY")
        if license_key:
            initialization_options["licenceKey"] = license_key

        max_memory = self._custom_settings.get("maxMemory")
        max_file_size = self._custom_settings.get("maxFileSize")
        if max_memory is not None:
            initialization_options["intelephense.maxMemory"] = max_memory
        if max_file_size is not None:
            initialization_options["intelephense.files.maxSize"] = max_file_size

        initialize_params["initializationOptions"] = initialization_options
        return initialize_params  # type: ignore

    def _start_server(self) -> None:
        """Start Intelephense server process"""

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

        log.info("Starting Intelephense server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.info("After sent initialize params")

        # Verify server capabilities
        capabilities = init_response["capabilities"]
        assert "textDocumentSync" in capabilities
        assert "completionProvider" in capabilities
        assert "definitionProvider" in capabilities
        assert "documentSymbolProvider" in capabilities, "Server must support document symbols"

        self.server.notify.initialized({})
        self.completions_available.set()

        # Intelephense server is typically ready immediately after initialization
        # TODO: This is probably incorrect; the server does send an initialized notification, which we could wait for!

    @override
    # For some reason, the LS may need longer to process this, so we just retry
    def _send_references_request(self, relative_file_path: str, line: int, column: int) -> list[lsp_types.Location] | None:
        # TODO: The LS doesn't return references contained in other files if it doesn't sleep. This is
        #   despite the LS having processed requests already. I don't know what causes this, but sleeping
        #   one second helps. It may be that sleeping only once is enough but that's hard to reliably test.
        # May be related to the time it takes to read the files or something like that.
        # The sleeping doesn't seem to be needed on all systems
        sleep(1)
        return super()._send_references_request(relative_file_path, line, column)

    @override
    def _send_definition_request(self, definition_params: DefinitionParams) -> Definition | list[LocationLink] | None:
        # TODO: same as above, also only a problem if the definition is in another file
        sleep(1)
        return super()._send_definition_request(definition_params)
