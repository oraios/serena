"""
Provides PHP specific instantiation of the LanguageServer class using Intelephense.
"""
# SPDX-License-Identifier: MIT

import logging
import os
import re
import shutil
from pathlib import PurePath
from time import sleep

from overrides import override

from serena.util.file_system import match_path
from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
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


class Intelephense(SolidLanguageServer):
    """
    Provides PHP specific instantiation of the LanguageServer class using Intelephense.

    You can pass the following entries in ls_specific_settings["php"]:
        - maxMemory: the maximum heap size of the server process in MB, applied as Node.js option
          --max-old-space-size (like VS Code's intelephense.maxMemory)
        - maxFileSize: sets intelephense.files.maxSize, the maximum size (in bytes) of files to index
        - ignore_vendor: whether or ignore directories named "vendor" (default: true)
        - file_filter: list of additional file extensions (with leading dot) to treat as PHP
          sources, e.g. [".module", ".inc"]. The extensions are added to the defaults (".php",
          ".phtml") of Serena's PHP source-file matcher and are pushed to Intelephense via
          files.associations, such that the symbol tools and the language server treat the
          same files as PHP sources (see #1710).
    """

    _DEFAULT_FILES_EXCLUDE = (
        "**/.git/**",
        "**/.svn/**",
        "**/.hg/**",
        "**/CVS/**",
        "**/.DS_Store/**",
        "**/node_modules/**",
        "**/bower_components/**",
        "**/vendor/**/{Tests,tests}/**",
        "**/.history/**",
        "**/vendor/**/vendor/**",
    )
    """
    Intelephense's default value of the ``files.exclude`` setting (as of version 1.14.4).
    A configured value replaces the default rather than extending it.
    """

    _INDEXED_DIRNAMES = frozenset({"vendor"})
    """
    names of directories which Intelephense indexes even if they are ignored, because the Composer dependencies
    they contain are needed to resolve the types used in the project's sources
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in self._ignored_dirnames

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Setup runtime dependencies for Intelephense and return the path to the executable.
            """
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

        @override
        def create_launch_command_env(self) -> dict[str, str]:
            # the heap size is an option of the Node.js process, which Intelephense cannot change once started
            max_memory = self._custom_settings.get("maxMemory")
            if max_memory is None:
                return {}
            existing_node_options = os.environ.get("NODE_OPTIONS", "").strip()
            return {"NODE_OPTIONS": f"{existing_node_options} --max-old-space-size={int(max_memory)}".strip()}

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

        # extend the source-file matcher with any additional extensions configured via `file_filter`,
        # such that Serena's symbol tools treat the added extensions as PHP sources as well (#1710)
        file_filter = self._custom_settings.get("file_filter")
        if file_filter:
            self.ls_id.get_source_fn_matcher().add_extensions(*file_filter)

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

        # push the files configuration: the file associations derived from the source-file matcher
        # (the default extensions plus any configured via `file_filter`), such that Intelephense
        # indexes the same set of files that Serena's symbol tools treat as PHP sources (#1710),
        # and the configured maximum file size. This cannot be passed in
        # the initialize request: Intelephense reads configuration exclusively from
        # workspace/didChangeConfiguration (its initializationOptions only cover storagePath,
        # globalStoragePath, clearCache and licenceKey).
        associations = [f"*{ext}" for ext in self.ls_id.get_source_fn_matcher().file_extensions]
        files_config: dict[str, list[str] | int] = {"associations": associations}
        max_file_size = self._custom_settings.get("maxFileSize")
        if max_file_size is not None:
            files_config["maxSize"] = int(max_file_size)

        # exclude the ignored directories from Intelephense's index; its globs are relative to the repository root
        excluded_dirs = self._find_excluded_dirs()
        if excluded_dirs:
            files_config["exclude"] = [*self._DEFAULT_FILES_EXCLUDE, *(self._escape_glob(d) + "/**" for d in excluded_dirs)]
            log.info(f"Excluding {len(excluded_dirs)} ignored directories from Intelephense's index: {excluded_dirs}")

        intelephense_config: DidChangeConfigurationParams = {"settings": {"intelephense": {"files": files_config}}}
        log.info(f"Sending workspace/didChangeConfiguration with files configuration: {files_config}")
        self.server.notify.workspace_did_change_configuration(intelephense_config)

        # Intelephense server is typically ready immediately after initialization
        # TODO: This is probably incorrect; the server does send an initialized notification, which we could wait for!

    def _find_excluded_dirs(self) -> list[str]:
        """
        Finds the directories to exclude from Intelephense's index.

        Intelephense indexes all PHP files below the repository root and does not know the ignored paths, so
        these directories are passed to it via ``files.exclude``. Directories named in ``_INDEXED_DIRNAMES`` are
        neither excluded nor searched.

        :return: the topmost directories matched by the ignored paths, as POSIX paths relative to the repository root
        """
        excluded_dirs: list[str] = []
        for dir_path, dir_names, _ in os.walk(self.repository_root_path):
            rel_dir_path = os.path.relpath(dir_path, self.repository_root_path)
            searched_dir_names = []
            for dir_name in dir_names:
                if dir_name in self._INDEXED_DIRNAMES:
                    continue
                rel_path = PurePath(rel_dir_path, dir_name).as_posix()
                if match_path(rel_path, self.get_ignore_spec(), root_path=self.repository_root_path, is_dir=True):
                    excluded_dirs.append(rel_path)
                else:
                    searched_dir_names.append(dir_name)
            dir_names[:] = searched_dir_names
        return excluded_dirs

    @staticmethod
    def _escape_glob(path: str) -> str:
        """
        :param path: a POSIX path
        :return: the glob pattern matching exactly the given path
        """
        return re.sub(r"([\\*?\[\]{}()!+@])", r"\\\1", path)

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
