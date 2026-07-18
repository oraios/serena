"""
Provides PHP specific instantiation of the LanguageServer class using Intelephense.
"""

import logging
import os
import shutil
from time import sleep

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import Definition, DefinitionParams, DidChangeConfigurationParams, LocationLink
from solidlsp.settings import SolidLSPSettings

from ..lsp_protocol_handler import lsp_types
from .common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command

log = logging.getLogger(__name__)

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_INTELEPHENSE_VERSION = "1.14.4"
DEFAULT_INTELEPHENSE_VERSION = "1.14.4"

# Default file extensions treated as PHP sources. Exposed for override via
# `ls_specific_settings["php"]` (key `file_filter`). Extensions added via `file_filter` are also
# synced into Language.PHP.get_source_fn_matcher() (a cached singleton) and, when customized,
# pushed to Intelephense as `intelephense.files.associations` globs, so Serena's symbol index and
# the language server agree on which files are PHP sources (#1710).
_DEFAULT_FILE_FILTER: list[str] = [".php"]


class Intelephense(SolidLanguageServer):
    """
    Provides PHP specific instantiation of the LanguageServer class using Intelephense.

    You can pass the following entries in ls_specific_settings["php"]:
        - maxMemory: sets intelephense.maxMemory
        - maxFileSize: sets intelephense.files.maxSize
        - ignore_vendor: whether or ignore directories named "vendor" (default: true)
        - file_filter: list of file extensions (with leading dot) to treat as PHP sources,
          e.g. [".php", ".phtml", ".module"]. Defaults to [".php"]. The extensions are added to
          Serena's PHP source-file matcher and a custom list is pushed to Intelephense as
          intelephense.files.associations globs, so find_symbol and the language server treat
          the same files as PHP sources (see #1710).
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
            intelephense_version = self._custom_settings.get("intelephense_version", DEFAULT_INTELEPHENSE_VERSION)
            npm_registry = self._custom_settings.get("npm_registry")

            # legacy unversioned dir reserved for INITIAL; every other version goes into a versioned subdir
            ls_dirname = "php-lsp" if intelephense_version == INITIAL_INTELEPHENSE_VERSION else f"php-lsp-{intelephense_version}"
            intelephense_ls_dir = os.path.join(self._ls_resources_dir, ls_dirname)
            os.makedirs(intelephense_ls_dir, exist_ok=True)
            intelephense_executable_path = os.path.join(intelephense_ls_dir, "node_modules", ".bin", "intelephense")
            if not os.path.exists(intelephense_executable_path):
                deps = RuntimeDependencyCollection(
                    [
                        RuntimeDependency(
                            id="intelephense",
                            command=build_npm_install_command("intelephense", intelephense_version, npm_registry),
                            platform_id="any",
                        )
                    ]
                )
                deps.install(intelephense_ls_dir)

            assert os.path.exists(intelephense_executable_path), (
                f"intelephense executable not found at {intelephense_executable_path}, something went wrong."
            )

            return intelephense_executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "--stdio"]

    @staticmethod
    def _resolve_file_filter(solidlsp_settings: SolidLSPSettings) -> list[str]:
        """Resolve the file extensions to treat as PHP sources.

        Reads an optional override from ``ls_specific_settings["php"]`` (key ``file_filter``);
        falls back to the default otherwise. Extracted as a pure function so the configuration
        plumbing can be unit-tested without starting the language server.
        """
        php_settings = solidlsp_settings.get_ls_specific_settings(Language.PHP)
        return php_settings.get("file_filter", list(_DEFAULT_FILE_FILTER))

    @staticmethod
    def _sync_source_fn_matcher(file_filter: list[str]) -> None:
        """Keep Serena's PHP source-file matcher in sync with the configured ``file_filter``.

        ``Language.PHP.get_source_fn_matcher()`` is a ``@cache``d per-language singleton, so adding
        the configured extensions here propagates to every consumer of the matcher - symbol index
        traversal, ignore checks, and language composition detection. Without this, ``find_symbol``
        would not surface symbols in files whose extensions were added to ``file_filter`` (#1710).
        """
        Language.PHP.get_source_fn_matcher().add_extensions(*file_filter)

    @staticmethod
    def _resolve_files_associations(file_filter: list[str]) -> list[str] | None:
        """The ``intelephense.files.associations`` globs to push for ``file_filter``, or ``None``.

        Returns ``None`` for the default filter: the pushed list replaces Intelephense's built-in
        associations (``["*.php", "*.phtml"]``), so pushing globs derived from ``[".php"]`` would
        silently drop ``*.phtml`` indexing and change default behavior (unlike Perl::LanguageServer,
        whose defaults match Serena's and allow an unconditional push). A customized filter is
        pushed and fully defines what the server indexes (#1710).
        """
        if file_filter == _DEFAULT_FILE_FILTER:
            return None
        return [f"*{ext}" for ext in file_filter]

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

        self._file_filter = self._resolve_file_filter(solidlsp_settings)
        # Sync Serena's source-file matcher with the configured extensions so find_symbol and the
        # language server agree on which files are PHP sources (see #1710).
        self._sync_source_fn_matcher(self._file_filter)

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    def _create_base_initialize_params(self) -> dict:
        """
        Returns the initialization params for the Intelephense Language Server.
        """
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
        return initialize_params

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
        initialize_params = self._create_initialize_params()

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

        associations = self._resolve_files_associations(self._file_filter)
        if associations is not None:
            # Intelephense only indexes files matching its `files.associations` globs, so a custom
            # file_filter must also be pushed to the server; otherwise cross-file features
            # (references, definitions) would skip the extra files even though Serena's matcher
            # accepts them (#1710). User-configured size/memory settings are carried along so the
            # pushed section stays self-consistent regardless of the server's merge semantics.
            files_settings: dict = {"associations": associations}
            max_file_size = self._custom_settings.get("maxFileSize")
            if max_file_size is not None:
                files_settings["maxSize"] = max_file_size
            intelephense_settings: dict = {"files": files_settings}
            max_memory = self._custom_settings.get("maxMemory")
            if max_memory is not None:
                intelephense_settings["maxMemory"] = max_memory
            intelephense_config: DidChangeConfigurationParams = {"settings": {"intelephense": intelephense_settings}}
            log.info(f"Sending workspace/didChangeConfiguration with file associations: {associations}")
            self.server.notify.workspace_did_change_configuration(intelephense_config)

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
