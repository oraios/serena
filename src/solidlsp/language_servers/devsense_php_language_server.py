"""
Provides PHP-specific instantiation of the language server published by Devsense.

The standalone ``devsense-php-ls`` npm package contains the platform-specific
language-server executable and communicates over LSP stdio.
"""

import logging
import os
import shutil
from time import sleep

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command

log = logging.getLogger(__name__)

INITIAL_DEVSENSE_PHP_LS_VERSION = "1.0.19197"
DEFAULT_DEVSENSE_PHP_LS_VERSION = "1.0.19197"


class DevsensePHPLanguageServer(SolidLanguageServer):
    """PHP Language Server provided by the standalone Devsense npm package.

    Devsense is an experimental alternative to Intelephense. Basic language
    features work without activation; premium features can be activated by
    setting ``DEVSENSE_PHP_LS_LICENSE`` in the environment.

    Supported ``ls_specific_settings["php_devsense"]`` keys are:

    * ``ls_path`` — path to an already-installed ``devsense-php-ls`` launcher.
    * ``devsense_php_ls_version`` — pinned npm package version.
    * ``npm_registry`` — optional npm registry override.
    * ``ignore_vendor`` — whether to ignore PHP ``vendor`` directories (default true).
    * ``file_filter`` — additional PHP source extensions, with leading dots.
    * ``php_version`` — optional PHP version forwarded in initialization options.
    """

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        _PLATFORM_PACKAGE_SUFFIXES: dict[PlatformId, str] = {
            PlatformId.LINUX_x64: "linux-x64",
            PlatformId.LINUX_arm64: "linux-arm64",
            PlatformId.LINUX_MUSL_x64: "linux-musl-x64",
            PlatformId.LINUX_MUSL_arm64: "linux-musl-arm64",
            PlatformId.OSX_x64: "darwin-x64",
            PlatformId.OSX_arm64: "darwin-arm64",
            PlatformId.WIN_x64: "win32-x64",
            PlatformId.WIN_arm64: "win32-arm64",
        }

        @classmethod
        def _platform_binary_path(cls, install_dir: str, platform_id: PlatformId) -> str:
            try:
                package_suffix = cls._PLATFORM_PACKAGE_SUFFIXES[platform_id]
            except KeyError as exc:
                raise RuntimeError(
                    f"Devsense PHP Language Server does not provide a binary for platform '{platform_id.value}'. "
                    "Supported platforms are Linux, macOS, and Windows x64/arm64."
                ) from exc

            binary_name = "devsense.php.ls.exe" if platform_id.is_windows() else "devsense.php.ls"
            return os.path.join(
                install_dir,
                "node_modules",
                f"devsense-php-ls-{package_suffix}",
                "dist",
                binary_name,
            )

        def _get_or_install_core_dependency(self) -> str:
            """Install the pinned Devsense npm package and return its platform binary.

            The package's documented platform binary is more reliable than npm's
            ``node_modules/.bin`` shim, which may be absent until a later npm rebuild.
            """
            platform_id = PlatformUtils.get_platform_id()
            if shutil.which("node") is None:
                raise RuntimeError("node is not installed or is not in PATH. Please install Node.js and try again.")
            if shutil.which("npm") is None:
                raise RuntimeError("npm is not installed or is not in PATH. Please install npm and try again.")

            version = self._custom_settings.get("devsense_php_ls_version", DEFAULT_DEVSENSE_PHP_LS_VERSION)
            registry = self._custom_settings.get("npm_registry")
            install_dir_name = "devsense-php-ls" if version == INITIAL_DEVSENSE_PHP_LS_VERSION else f"devsense-php-ls-{version}"
            install_dir = os.path.join(self._ls_resources_dir, install_dir_name)
            executable_path = self._platform_binary_path(install_dir, platform_id)

            if not os.path.exists(executable_path):
                dependencies = RuntimeDependencyCollection(
                    [
                        RuntimeDependency(
                            id="devsense-php-ls",
                            description="Devsense PHP Language Server",
                            command=build_npm_install_command("devsense-php-ls", version, registry),
                            platform_id="any",
                        )
                    ]
                )
                log.info("Installing devsense-php-ls %s into %s", version, install_dir)
                dependencies.install(install_dir)

            if not os.path.isfile(executable_path):
                raise FileNotFoundError(
                    f"devsense-php-ls platform binary not found at {executable_path}. "
                    "The npm install may have skipped the matching optional platform dependency."
                )
            return executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "--stdio"]

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in self._ignored_dirnames

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(config, repository_root_path, None, "php", solidlsp_settings)
        self._ignored_dirnames = {"node_modules", "cache"}
        if self._custom_settings.get("ignore_vendor", True):
            self._ignored_dirnames.add("vendor")

        file_filter = self._custom_settings.get("file_filter")
        if file_filter:
            self.ls_id.get_source_fn_matcher().add_extensions(*file_filter)

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    def _create_base_initialize_params(self) -> dict:
        """Return initialization parameters accepted by Devsense PHP LS."""
        initialize_options: dict[str, object] = {}
        license_key = os.environ.get("DEVSENSE_PHP_LS_LICENSE")
        if license_key:
            initialize_options["0"] = license_key

        php_version = self._custom_settings.get("php_version")
        if php_version is not None:
            initialize_options["php.version"] = php_version

        return {
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
            "initializationOptions": initialize_options,
        }

    def _start_server(self) -> None:
        """Start Devsense PHP LS and complete the LSP initialization handshake."""

        def register_capability_handler(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info("LSP: %s", msg)

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Devsense PHP Language Server")
        self.server.start()
        initialize_params = self._create_initialize_params()
        init_response = self.server.send.initialize(initialize_params)
        capabilities = init_response["capabilities"]
        assert "textDocumentSync" in capabilities
        assert "definitionProvider" in capabilities
        assert "documentSymbolProvider" in capabilities
        self.server.notify.initialized({})

    @override
    def _send_references_request(self, relative_file_path: str, line: int, column: int):
        sleep(1)
        return super()._send_references_request(relative_file_path, line, column)
