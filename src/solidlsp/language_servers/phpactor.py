"""
Provides PHP specific instantiation of the LanguageServer class using Phpactor.
"""

import hashlib
import logging
import os
import re
import shutil
import stat
import threading

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_utils import FileUtils
from solidlsp.settings import SolidLSPSettings
from solidlsp.util.subprocess_util import subprocess_run

log = logging.getLogger(__name__)

PHPACTOR_ALLOWED_HOSTS = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_PHPACTOR_VERSION = "2025.12.21.1"
INITIAL_PHPACTOR_PHAR_SHA256 = "53bbe9625cd9b5e9b394bc2f595fbad13dbbe6dfc96950c56dea3b5d9a246cc3"
DEFAULT_PHPACTOR_VERSION = "2025.12.21.1"
DEFAULT_PHPACTOR_PHAR_SHA256 = "53bbe9625cd9b5e9b394bc2f595fbad13dbbe6dfc96950c56dea3b5d9a246cc3"

# Phpactor's own default `indexer.supported_extensions`; overriding that setting replaces the
# defaults rather than extending them, so they have to be carried over explicitly.
PHPACTOR_DEFAULT_INDEXED_EXTENSIONS = ("php", "phar")


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
        - file_filter: list of additional file extensions (with leading dot) to treat as PHP
          sources, e.g. [".module", ".inc"]; these are also pushed to Phpactor's indexer, so
          references contained in such files are found as well
        - indexing_timeout: float, seconds to wait for Phpactor's initial workspace index before
          the first cross-file query (default: 120.0)
        - indexing_start_grace: float, seconds to wait for Phpactor to start reporting indexing
          progress at all (default: 5.0)

    Serena keeps Phpactor's index in the project's cache directory, one directory per set of
    indexed extensions, so the first cross-file query of a project (or the first one after
    `file_filter` changed) waits for a full index, PHP's bundled stubs included.

    On Windows, Phpactor's indexer does not deliver: it announces "Indexing workspace" and then
    makes no progress at all (measured on the Windows CI runners: no progress report and an empty
    index 600s in, where the same workspace takes ~9s elsewhere). Cross-file queries there return
    nothing once `indexing_timeout` expires -- symbol queries, which do not use the index, are
    unaffected. Prefer Intelephense or PHPantom on Windows.
    """

    # Phpactor indexes the workspace once at startup and reports it as work-done progress; a
    # cross-file query before that index exists comes back empty (see
    # `_wait_for_cross_file_references_if_needed`). The timeouts only bound the pathological case
    # of a server that never reports.
    INDEXING_TIMEOUT = 120.0
    INDEXING_START_GRACE = 5.0

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
            result = subprocess_run(["php", "--version"], capture_output=True, text=True, check=False)
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

        self._ignored_dirnames = {"node_modules", "cache"}
        if self._custom_settings.get("ignore_vendor", True):
            self._ignored_dirnames.add("vendor")
        log.info(f"Ignoring the following directories for PHP (Phpactor): {', '.join(sorted(self._ignored_dirnames))}")

        # extending Serena's source matcher with project-specific PHP extensions
        file_filter = self._custom_settings.get("file_filter")
        if file_filter:
            self.ls_id.get_source_fn_matcher().add_extensions(*file_filter)

        # tracking the workspace indexing that Phpactor reports as work-done progress
        self._progress_lock = threading.Lock()
        self._active_progress_tokens: set[str] = set()
        self._indexing_started = threading.Event()
        self._indexing_complete = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    def _create_base_initialize_params(self) -> dict:
        """
        Returns the initialization params for the Phpactor Language Server.
        """
        # union of Phpactor's own indexer extensions with everything Serena's source-file matcher
        # treats as PHP (the defaults plus any configured via `file_filter`)
        indexed_extensions = list(
            dict.fromkeys(
                [*PHPACTOR_DEFAULT_INDEXED_EXTENSIONS, *(ext.lstrip(".") for ext in self.ls_id.get_source_fn_matcher().file_extensions)]
            )
        )

        initialization_options: dict[str, object] = {
            "language_server_phpstan.enabled": False,
            "language_server_psalm.enabled": False,
            "language_server_php_cs_fixer.enabled": False,
            # Phpactor's indexer only walks its own default extensions, so the extra extensions
            # Serena treats as PHP sources (`file_filter`, #1710) would be missing from the index
            # and cross-file requests such as `textDocument/references` would not see them.
            # These keys replace Phpactor's defaults, hence the union with them.
            "indexer.include_patterns": [f"/**/*.{ext}" for ext in indexed_extensions],
            "indexer.supported_extensions": indexed_extensions,
        }

        # Phpactor's dirty-document tracker appends to `<indexer.index_path>/dirty` whenever a
        # references request reconciles the open documents with the index, and raises if that
        # directory does not exist yet -- which is the case until its background index has flushed
        # for the first time. A `find_referencing_symbols` early in the session therefore failed
        # outright (observed on Windows CI). Pointing the index at a directory Serena creates up
        # front removes the race and keeps the index next to the other cached state of the project.
        #
        # The indexed extensions are part of the directory name because Phpactor's indexer skips
        # files that are older than the index: widening `file_filter` for an already indexed
        # project would otherwise leave the newly included files out of the index indefinitely.
        index_key = hashlib.sha256(",".join(indexed_extensions).encode()).hexdigest()[:8]
        index_path = self.cache_dir / f"phpactor-index-{index_key}"
        if re.search(r"%.*%", str(index_path)):
            # Phpactor expands `%token%` pairs in path settings and aborts on unknown tokens, so
            # such a path cannot be passed on; the project keeps Phpactor's default index location.
            log.warning(f"Not configuring Phpactor's index path: '{index_path}' would be read as containing a placeholder")
        else:
            index_path.mkdir(parents=True, exist_ok=True)
            initialization_options["indexer.index_path"] = str(index_path)

        return {
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
                # Phpactor reports its workspace indexing as work-done progress, which is what the
                # first cross-file query waits on
                "window": {"workDoneProgress": True},
            },
            "initializationOptions": initialization_options,
        }

    def _on_progress(self, params: dict) -> None:
        """Track the work-done progress tokens Phpactor reports, the workspace index among them.

        :param params: the `$/progress` notification's `ProgressParams`
        """
        token = str(params.get("token", ""))
        value = params.get("value") or {}
        kind = value.get("kind")
        if kind == "begin":
            with self._progress_lock:
                self._active_progress_tokens.add(token)
                self._indexing_complete.clear()
            self._indexing_started.set()
            log.info(f"Phpactor progress [{token}] started: {value.get('title')}")
        elif kind == "end":
            with self._progress_lock:
                self._active_progress_tokens.discard(token)
                if not self._active_progress_tokens:
                    self._indexing_complete.set()
            log.info(f"Phpactor progress [{token}] ended: {value.get('message')}")

    @override
    def _wait_for_cross_file_references_if_needed(self) -> None:
        if self._has_waited_for_cross_file_references:
            return

        # Phpactor answers reference queries from its index and reconciles the open documents with
        # it first, so a query issued before the initial index has been written returns nothing at
        # all -- and its dirty-document tracker even raises if the index directory is still absent.
        # Wait for the indexing progress Phpactor reports rather than for a fixed period.
        timeout = float(self._custom_settings.get("indexing_timeout", self.INDEXING_TIMEOUT))
        start_grace = float(self._custom_settings.get("indexing_start_grace", self.INDEXING_START_GRACE))
        if not self._indexing_started.wait(timeout=start_grace):
            log.warning(f"Phpactor reported no indexing progress within {start_grace:.0f}s; proceeding")
        elif not self._indexing_complete.wait(timeout=timeout):
            with self._progress_lock:
                outstanding = ", ".join(sorted(self._active_progress_tokens)) or "<none>"
            log.warning(f"Phpactor indexing did not complete within {timeout:.0f}s; proceeding (outstanding tokens: {outstanding})")
        else:
            log.info("Phpactor indexing complete")
        self._has_waited_for_cross_file_references = True

    def _start_server(self) -> None:
        """Start Phpactor server process."""

        def register_capability_handler(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("window/workDoneProgress/create", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", self._on_progress)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Phpactor server process")
        self.server.start()
        initialize_params = self._create_initialize_params()

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.info("After sent initialize params")

        # Verify server capabilities
        assert "capabilities" in init_response
        assert init_response["capabilities"].get("definitionProvider"), "Phpactor did not advertise definition support"

        self.server.notify.initialized({})
