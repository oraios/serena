import logging
import os.path
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from sensai.util.logging import LogTime

from serena.config.serena_config import ProjectConfig, SerenaPaths
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig, LanguageServerId
from solidlsp.lsp_protocol_handler.lsp_types import DidChangeWatchedFilesParams, FileChangeType, FileEvent
from solidlsp.settings import SolidLSPSettings

if TYPE_CHECKING:
    from .project import Project

log = logging.getLogger(__name__)


class LanguageServerManagerInitialisationError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class LanguageServerFactory:
    def __init__(
        self,
        project_root: str,
        project_config: ProjectConfig,
        project_data_path: str,
        encoding: str,
        ignored_patterns: list[str],
        ls_timeout: float | None = None,
        ls_specific_settings: dict | None = None,
        trace_lsp_communication: bool = False,
    ):
        self.project_root = project_root
        self.project_config = project_config
        self.project_data_path = project_data_path
        self.encoding = encoding
        self.ignored_patterns = ignored_patterns
        self.ls_timeout = ls_timeout
        self.ls_specific_settings = ls_specific_settings
        self.trace_lsp_communication = trace_lsp_communication

    def create_language_server(self, ls_id: LanguageServerId) -> SolidLanguageServer:
        ls_config = LanguageServerConfig(
            workspace_folders=self.project_config.ls_workspace_folders,
            additional_workspace_folders=self.project_config.ls_additional_workspace_folders,
            ls_id=ls_id,
            ignored_paths=self.ignored_patterns,
            trace_lsp_communication=self.trace_lsp_communication,
            encoding=self.encoding,
        )

        log.info(f"Creating language server instance for {self.project_root}, language={ls_id}.")
        return SolidLanguageServer.create(
            ls_config,
            self.project_root,
            timeout=self.ls_timeout,
            solidlsp_settings=SolidLSPSettings(
                solidlsp_dir=SerenaPaths().serena_user_home_dir,
                project_data_path=self.project_data_path,
                ls_specific_settings=self.ls_specific_settings or {},
            ),
        )


class LanguageServerManager:
    """
    Manages one or more language servers for a project.
    """

    def __init__(
        self,
        language_servers: dict[LanguageServerId, SolidLanguageServer],
        language_server_factory: LanguageServerFactory,
        project: "Project",
    ) -> None:
        """
        :param language_servers: a mapping from language to language server; the servers are assumed to be already started.
            The first server in the iteration order is used as the default server.
            All servers are assumed to serve the same project root.
        :param language_server_factory: factory for language server creation; if None, dynamic (re)creation of language servers
            is not supported
        """
        self._language_servers = language_servers
        self._language_server_factory = language_server_factory
        self._file_change_notifier = LanguageServerFileChangeNotifier(project, self)

    @property
    def _default_language_server(self) -> SolidLanguageServer:
        if len(self._language_servers) == 0:
            raise ValueError("No language servers available in the manager")
        return next(iter(self._language_servers.values()))

    @staticmethod
    def from_languages(languages: list[LanguageServerId], factory: LanguageServerFactory, project: "Project") -> "LanguageServerManager":
        """
        Creates a manager with language servers for the given languages using the given factory.
        The language servers are started in parallel threads.

        :param languages: the languages for which to spawn language servers
        :param factory: the factory for language server creation
        :param project: the project for which the language servers are created
        :return: the instance
        """

        class StartLSThread(threading.Thread):
            def __init__(self, ls_id: LanguageServerId):
                super().__init__(target=self._start_language_server, name="StartLS:" + ls_id.value)
                self.ls_id = ls_id
                self.language_server: SolidLanguageServer | None = None
                self.exception: Exception | None = None

            def _start_language_server(self) -> None:
                try:
                    with LogTime(f"Language server startup (language={self.ls_id.value})"):
                        self.language_server = factory.create_language_server(self.ls_id)
                        self.language_server.start()
                        if not self.language_server.is_running():
                            raise RuntimeError(f"Failed to start the language server for language {self.ls_id.value}")
                except Exception as e:
                    log.error(f"Error starting language server for language {self.ls_id.value}: {e}", exc_info=e)
                    self.exception = e

        # start language servers in parallel threads
        threads = []
        for language in languages:
            thread = StartLSThread(language)
            thread.start()
            threads.append(thread)

        # collect language servers and exceptions
        language_servers: dict[LanguageServerId, SolidLanguageServer] = {}
        exceptions: dict[LanguageServerId, Exception] = {}
        for thread in threads:
            thread.join()
            if thread.exception is not None:
                exceptions[thread.ls_id] = thread.exception
            elif thread.language_server is not None:
                language_servers[thread.ls_id] = thread.language_server

        # If any server failed to start up, raise an exception and stop all started language servers.
        # We intentionally fail fast here. The user's intention is to work with all the specified languages,
        # so if any of them is not available, it is better to make symbolic tool calls fail, bringing the issue to the
        # user's attention instead of silently continuing with a subset of the language servers and potentially
        # causing suboptimal agent behaviour.
        if exceptions:
            for ls in language_servers.values():
                ls.stop()
            failure_messages = "\n".join([f"{lang.value}: {e}" for lang, e in exceptions.items()])
            raise LanguageServerManagerInitialisationError(f"Failed to start {len(exceptions)} language server(s):\n{failure_messages}")

        return LanguageServerManager(language_servers, factory, project)

    def _ensure_functional_ls(self, ls: SolidLanguageServer) -> SolidLanguageServer:
        if not ls.is_running():
            log.warning(f"Language server for language {ls.ls_id} is not running; restarting ...")
            ls = self.restart_language_server(ls.ls_id)
        return ls

    def _get_suitable_language_server(self, relative_path: str) -> SolidLanguageServer | None:
        """:param relative_path: relative path to a file"""
        for candidate in self._language_servers.values():
            if not candidate.is_ignored_path(relative_path, ignore_unsupported_files=True):
                return candidate
        return None

    def get_language_server(self, relative_path: str) -> SolidLanguageServer:
        """:param relative_path: relative path to a file"""
        ls: SolidLanguageServer | None = None
        if len(self._language_servers) > 1:
            if os.path.isdir(relative_path):
                raise ValueError(f"Expected a file path, but got a directory: {relative_path}")
            ls = self._get_suitable_language_server(relative_path)
        if ls is None:
            ls = self._default_language_server
        return self._ensure_functional_ls(ls)

    def _create_and_start_language_server(self, ls_id: LanguageServerId) -> SolidLanguageServer:
        if self._language_server_factory is None:
            raise ValueError(f"No language server factory available to create language server for {ls_id}")
        language_server = self._language_server_factory.create_language_server(ls_id)
        language_server.start()
        self._language_servers[ls_id] = language_server
        return language_server

    def restart_language_server(self, language: LanguageServerId) -> SolidLanguageServer:
        """
        Forces recreation and restart of the language server for the given language.
        It is assumed that the language server for the given language is no longer running.

        :param language: the language
        :return: the newly created language server
        """
        if language not in self._language_servers:
            raise ValueError(f"No language server for language {language.value} present; cannot restart")
        return self._create_and_start_language_server(language)

    def add_language_server(self, ls_id: LanguageServerId) -> SolidLanguageServer:
        """
        Dynamically adds a new language server for the given language.

        :param ls_id: the language server to add
        :return: the newly created language server
        """
        if ls_id in self._language_servers:
            raise ValueError(f"Language server for language {ls_id.value} already present")
        return self._create_and_start_language_server(ls_id)

    def remove_language_server(self, language: LanguageServerId, save_cache: bool = False) -> None:
        """
        Removes the language server for the given language, stopping it if it is running.

        :param language: the language
        """
        if language not in self._language_servers:
            raise ValueError(f"No language server for language {language.value} present; cannot remove")
        ls = self._language_servers.pop(language)
        self._stop_language_server(ls, save_cache=save_cache)

    def get_active_language_server_ids(self) -> list[LanguageServerId]:
        """
        Returns the list of languages for which language servers are currently managed.

        :return: list of languages
        """
        return list(self._language_servers.keys())

    @staticmethod
    def _stop_language_server(ls: SolidLanguageServer, save_cache: bool = False, timeout: float = 2.0) -> None:
        if ls.is_running():
            if save_cache:
                ls.save_cache()
            log.info(f"Stopping language server for language {ls.ls_id} ...")
            ls.stop(shutdown_timeout=timeout)

    def iter_language_servers(self) -> Iterator[SolidLanguageServer]:
        for ls in self._language_servers.values():
            yield self._ensure_functional_ls(ls)

    def stop_all(self, save_cache: bool = False, timeout: float = 2.0) -> None:
        """
        Stops all managed language servers.

        :param save_cache: whether to save the cache before stopping
        :param timeout: timeout for shutdown of each language server
        """
        for ls in self.iter_language_servers():
            self._stop_language_server(ls, save_cache=save_cache, timeout=timeout)

    def save_all_caches(self) -> None:
        """
        Saves the caches of all managed language servers.
        """
        for ls in self.iter_language_servers():
            if ls.is_running():
                ls.save_cache()

    def has_suitable_ls_for_file(self, relative_file_path: str) -> bool:
        return self._get_suitable_language_server(relative_file_path) is not None

    def sync_file_system_changes(self) -> int:
        """
        Polls the file system for changes to source files and notifies the language servers of any changes
        (particularly changes that happened outside of Serena's own file tools, which are not covered by
        the notifications sent by those tools/CodeEditor).

        :return: the number of individual file change events detected (0 if nothing changed).
        """
        log.info("Polling file system for changes to source files ...")
        num_changes = self._file_change_notifier.poll_and_notify()
        log.info(f"File system polling complete; {num_changes} change events sent to language servers.")
        return num_changes


class LanguageServerFileChangeNotifier:
    """
    Detects changes to source files on disk and notifies language servers of those changes.
    """

    def __init__(self, project: "Project", language_server_manager: LanguageServerManager, initial_poll: bool = True) -> None:
        self._project = project
        self._language_server_manager = language_server_manager
        self._freshness_last_seen_mtimes: dict[str, float] | None = None
        self._freshness_lock = threading.Lock()

        if initial_poll:
            # Establish the baseline for the first poll; no notifications are sent on the first call.
            with LogTime("Initialising file change notifier (polling for baseline)"):
                self.poll_and_notify()

    def poll_and_notify(self) -> int:
        """
        Detects source files that were changed, created or deleted on disk since the last call
        and notifies every language server managed for this project via the LSP
        ``workspace/didChangeWatchedFiles`` notification.

        This exists because Serena's own file and symbol tools notify the language server inline
        (via didOpen/didChange/didClose) when they edit a file, but edits made through any other
        channel (another editor, a second agent, a git checkout, a build step) are otherwise
        invisible to a warm language server, causing symbolic queries to answer from a stale index.

        The set of files considered is exactly the set Serena itself tracks (see
        :meth:`gather_source_files`), so no separate file-discovery logic has to be kept in sync.
        The dominant cost is the directory walk plus one ``os.stat`` per tracked file; this is
        intended to be called before symbolic tool invocations rather than on a timer.

        :return: the number of change events sent (0 if nothing changed, if no language server is
            running yet, or on the first call, which only establishes the baseline).
        """
        current: dict[str, float] = {}
        for rel_path in self._project.gather_source_files():
            try:
                current[rel_path] = os.stat(os.path.join(self._project.project_root, rel_path)).st_mtime
            except OSError:
                continue

        # Read-diff-swap under the lock only; the filesystem walk above and the LSP notifications
        # below stay outside it so concurrent callers do not serialize on I/O.
        with self._freshness_lock:
            previous = self._freshness_last_seen_mtimes
            self._freshness_last_seen_mtimes = current

            if previous is None:
                return 0

            # compute the set of individual events (created, changed, deleted)
            events: list[tuple[str, FileChangeType]] = []
            for rel_path, mtime in current.items():
                prev_mtime = previous.get(rel_path)
                if prev_mtime is None:
                    events.append((rel_path, FileChangeType.Created))
                elif mtime > prev_mtime:
                    events.append((rel_path, FileChangeType.Changed))
            events.extend((rel_path, FileChangeType.Deleted) for rel_path in previous if rel_path not in current)

        if not events:
            return 0

        # create the change didChangeWatchedFiles notification
        changes: list[FileEvent] = [
            {"uri": Path(self._project.project_root, rel_path).resolve().as_uri(), "type": change_type} for rel_path, change_type in events
        ]
        params: DidChangeWatchedFilesParams = {"changes": changes}
        created_paths = [rel_path for rel_path, change_type in events if change_type == FileChangeType.Created]

        for ls in self._language_server_manager.iter_language_servers():
            # send the didChangeWatchedFiles notification to the language server
            try:
                ls.server.notify.did_change_watched_files(params)
            except Exception as e:
                log.error("Failed to notify language server of watched file changes", exc_info=e)

            # A didChangeWatchedFiles(Created) notification alone is not enough for every backend
            # (observed with pyright) to fold a brand-new file into its cross-file reference graph;
            # an open/close cycle forces the parse+bind that Serena's own file tools trigger via
            # SolidLanguageServer.open_file().
            for rel_path in created_paths:
                if ls.is_ignored_path(rel_path, ignore_unsupported_files=True):
                    continue
                try:
                    with ls.open_file(rel_path):
                        pass
                except Exception as e:
                    log.error(f"Failed to refresh newly created file {rel_path!r} in language server", exc_info=e)

        return len(events)
