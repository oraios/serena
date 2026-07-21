"""
Provides PHP specific instantiation of the LanguageServer class using PHPantom.
"""

import logging
import os
import shutil
import stat
from time import sleep

from overrides import override

from solidlsp import ls_types
from solidlsp.ls import (
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    LSPFileBuffer,
    SolidLanguageServer,
)
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler import lsp_types as protocol_lsp_types
from solidlsp.lsp_protocol_handler.lsp_types import Definition, DefinitionParams, LocationLink
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)

PHPANTOM_ALLOWED_HOSTS = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_PHPANTOM_VERSION = "0.8.0"
DEFAULT_PHPANTOM_VERSION = "0.8.0"

_PHPANTOM_RUNTIME_DEPENDENCIES_BY_VERSION: dict[str, tuple[RuntimeDependency, ...]] = {
    "0.8.0": (
        RuntimeDependency(
            id="phpantom_lsp",
            description="PHPantom language server for macOS (arm64)",
            url="https://github.com/PHPantom-dev/phpantom_lsp/releases/download/0.8.0/phpantom_lsp-aarch64-apple-darwin.tar.gz",
            platform_id=PlatformId.OSX_arm64.value,
            archive_type="gztar",
            binary_name="phpantom_lsp",
            sha256="2cdfd103b5df98d20712eaeea9bd00d2b459e2a588296f1ab8e558fe25fde456",
            allowed_hosts=PHPANTOM_ALLOWED_HOSTS,
        ),
        RuntimeDependency(
            id="phpantom_lsp",
            description="PHPantom language server for macOS (x64)",
            url="https://github.com/PHPantom-dev/phpantom_lsp/releases/download/0.8.0/phpantom_lsp-x86_64-apple-darwin.tar.gz",
            platform_id=PlatformId.OSX_x64.value,
            archive_type="gztar",
            binary_name="phpantom_lsp",
            sha256="e09eef93342cd38c9f9cc6c58064d81b005d06ec6d054e7cdeeec7698dc6c5da",
            allowed_hosts=PHPANTOM_ALLOWED_HOSTS,
        ),
        RuntimeDependency(
            id="phpantom_lsp",
            description="PHPantom language server for Linux (arm64)",
            url="https://github.com/PHPantom-dev/phpantom_lsp/releases/download/0.8.0/phpantom_lsp-aarch64-unknown-linux-gnu.tar.gz",
            platform_id=PlatformId.LINUX_arm64.value,
            archive_type="gztar",
            binary_name="phpantom_lsp",
            sha256="e87fc96430f1bcc4966f953033a73a4e2ea53b2dbb7dc3e5f71cc8ced9022a57",
            allowed_hosts=PHPANTOM_ALLOWED_HOSTS,
        ),
        RuntimeDependency(
            id="phpantom_lsp",
            description="PHPantom language server for Linux (x64)",
            url="https://github.com/PHPantom-dev/phpantom_lsp/releases/download/0.8.0/phpantom_lsp-x86_64-unknown-linux-gnu.tar.gz",
            platform_id=PlatformId.LINUX_x64.value,
            archive_type="gztar",
            binary_name="phpantom_lsp",
            sha256="39615b495e624bbafe8787c3be61acabc123ec5ac23e9b30e00ab7660f50e020",
            allowed_hosts=PHPANTOM_ALLOWED_HOSTS,
        ),
        RuntimeDependency(
            id="phpantom_lsp",
            description="PHPantom language server for Windows (arm64)",
            url="https://github.com/PHPantom-dev/phpantom_lsp/releases/download/0.8.0/phpantom_lsp-aarch64-pc-windows-msvc.zip",
            platform_id=PlatformId.WIN_arm64.value,
            archive_type="zip",
            binary_name="phpantom_lsp.exe",
            sha256="352bfd90351c0f35947ea1af458dabe7a4dc4753d0cabaf9711a23a61346a63d",
            allowed_hosts=PHPANTOM_ALLOWED_HOSTS,
        ),
        RuntimeDependency(
            id="phpantom_lsp",
            description="PHPantom language server for Windows (x64)",
            url="https://github.com/PHPantom-dev/phpantom_lsp/releases/download/0.8.0/phpantom_lsp-x86_64-pc-windows-msvc.zip",
            platform_id=PlatformId.WIN_x64.value,
            archive_type="zip",
            binary_name="phpantom_lsp.exe",
            sha256="17e23af816fc7ec695fe716f6209df6b0eafcec2fdafb5d9d72e2b352d5ddf83",
            allowed_hosts=PHPANTOM_ALLOWED_HOSTS,
        ),
    )
}


def _create_phpantom_dependencies(version: str) -> RuntimeDependencyCollection:
    dependencies = _PHPANTOM_RUNTIME_DEPENDENCIES_BY_VERSION.get(version)
    if dependencies is None:
        raise RuntimeError(
            f"Unsupported phpantom_version '{version}'. "
            + f"Known bundled versions: {', '.join(sorted(_PHPANTOM_RUNTIME_DEPENDENCIES_BY_VERSION))}"
        )
    return RuntimeDependencyCollection(dependencies)


class PHPantomServer(SolidLanguageServer):
    """
    Provides PHP specific instantiation of the LanguageServer class using PHPantom.

    PHPantom is an open-source PHP language server written in Rust.
    It is an experimental alternative to Intelephense, which remains the default PHP language server.

    You can pass the following entries in ls_specific_settings["php_phpantom"]:
        - ls_path: path to a pre-installed phpantom_lsp binary
        - phpantom_version: override the pinned PHPantom version downloaded by Serena
        - ignore_vendor: whether to ignore directories named "vendor" (default: true)
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in self._ignored_dirnames

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Setup runtime dependencies for PHPantom and return the path to the executable.
            """
            # checking PATH first
            system_phpantom = shutil.which("phpantom_lsp")
            if system_phpantom is not None:
                log.info(f"Using system-installed phpantom_lsp at {system_phpantom}")
                return system_phpantom

            # resolving the bundled binary
            phpantom_version = self._custom_settings.get("phpantom_version", DEFAULT_PHPANTOM_VERSION)
            dependencies = _create_phpantom_dependencies(phpantom_version)
            binary_dirname = "phpantom-lsp" if phpantom_version == INITIAL_PHPANTOM_VERSION else f"phpantom-lsp-{phpantom_version}"
            binary_dir = os.path.join(self._ls_resources_dir, binary_dirname)
            binary_path = dependencies.binary_path(binary_dir)
            if not os.path.exists(binary_path):
                os.makedirs(binary_dir, exist_ok=True)
                dep = dependencies.get_single_dep_for_current_platform("phpantom_lsp")
                log.info(f"Downloading phpantom_lsp from {dep.url}")
                dependencies.install(binary_dir)

            if not os.path.exists(binary_path):
                raise FileNotFoundError(f"phpantom_lsp executable not found at {binary_path}")

            if PlatformUtils.get_platform_id() not in (PlatformId.WIN_x64, PlatformId.WIN_arm64):
                current_mode = os.stat(binary_path).st_mode
                os.chmod(binary_path, current_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

            return binary_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "--stdio"]

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(config, repository_root_path, None, "php", solidlsp_settings)
        self.request_id = 0
        self.language = Language.PHP_PHPANTOM

        self._ignored_dirnames = {"node_modules", "cache"}
        if self._custom_settings.get("ignore_vendor", True):
            self._ignored_dirnames.add("vendor")
        log.info(f"Ignoring the following directories for PHP (PHPantom): {', '.join(sorted(self._ignored_dirnames))}")

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    def _create_base_initialize_params(self) -> dict:
        """
        Returns the initialization params for the PHPantom Language Server.
        """
        # declaring client capabilities
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
                    "applyEdit": True,
                    "workspaceEdit": {
                        "documentChanges": True,
                        "resourceOperations": ["create", "rename", "delete"],
                        "failureHandling": "textOnlyTransactional",
                        "normalizesLineEndings": True,
                        "changeAnnotationSupport": {"groupsOnLabel": True},
                    },
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
        }
        return initialize_params

    def _start_server(self) -> None:
        """Start PHPantom server process."""

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

        log.info("Starting PHPantom server process")
        self.server.start()
        initialize_params = self._create_initialize_params()

        # negotiating server capabilities
        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.info("After sent initialize params")

        capabilities = init_response["capabilities"]
        assert "textDocumentSync" in capabilities
        assert "completionProvider" in capabilities
        assert "definitionProvider" in capabilities
        assert "documentSymbolProvider" in capabilities, "Server must support document symbols"
        assert capabilities.get("referencesProvider"), "PHPantom did not advertise references support"

        self.server.notify.initialized({})

    @override
    def _send_references_request(self, relative_file_path: str, line: int, column: int) -> list[protocol_lsp_types.Location] | None:
        # waiting for cross-file index updates
        sleep(1)
        return super()._send_references_request(relative_file_path, line, column)

    @override
    def _send_definition_request(self, definition_params: DefinitionParams) -> Definition | list[LocationLink] | None:
        # waiting for cross-file index updates
        sleep(1)
        return super()._send_definition_request(definition_params)

    @override
    def request_hover(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        file_buffer: LSPFileBuffer | None = None,
    ) -> ls_types.Hover | None:
        # requesting direct hover info
        hover = super().request_hover(relative_file_path, line, column, file_buffer=file_buffer)
        if hover is not None:
            return hover

        # falling back to a usage-site hover
        references = self.request_references(relative_file_path, line, column)
        for reference in references:
            ref_relative_path = reference.get("relativePath")
            if ref_relative_path is None:
                continue
            start = reference["range"]["start"]
            if ref_relative_path == relative_file_path and start["line"] == line and start["character"] == column:
                continue
            usage_hover = super().request_hover(ref_relative_path, start["line"], start["character"])
            if usage_hover is not None:
                return usage_hover

        return None
