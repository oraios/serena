import logging
import threading
from collections.abc import Iterator

from sensai.util.logging import LogTime

from serena.config.serena_config import SerenaPaths
from serena.constants import SERENA_MANAGED_DIR_NAME
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class LanguageServerFactory:
    def __init__(
        self,
        project_root: str,
        encoding: str,
        ignored_patterns: list[str],
        ls_timeout: float | None = None,
        ls_specific_settings: dict | None = None,
        trace_lsp_communication: bool = False,
    ):
        self.project_root = project_root
        self.encoding = encoding
        self.ignored_patterns = ignored_patterns
        self.ls_timeout = ls_timeout
        self.ls_specific_settings = ls_specific_settings
        self.trace_lsp_communication = trace_lsp_communication

    def create_language_server(self, language: Language) -> SolidLanguageServer:
        ls_config = LanguageServerConfig(
            code_language=language,
            ignored_paths=self.ignored_patterns,
            trace_lsp_communication=self.trace_lsp_communication,
            encoding=self.encoding,
        )

        log.info(f"Creating language server instance for {self.project_root}, language={language}.")
        return SolidLanguageServer.create(
            ls_config,
            self.project_root,
            timeout=self.ls_timeout,
            solidlsp_settings=SolidLSPSettings(
                solidlsp_dir=SerenaPaths().serena_user_home_dir,
                project_data_relative_path=SERENA_MANAGED_DIR_NAME,
                ls_specific_settings=self.ls_specific_settings or {},
            ),
        )


class LanguageServerManager:
    """
    Manages one or more language servers for a project.
    """

    def __init__(
        self,
        language_servers: dict[Language, SolidLanguageServer],
        language_server_factory: LanguageServerFactory | None = None,
        project_root: str | None = None,
    ) -> None:
        """
        :param language_servers: a mapping from language to language server; the servers are assumed to be already started.
            The first server in the iteration order is used as the default server.
            All servers are assumed to serve the same project root.
            Can be empty when allow_no_language_servers is enabled.
        :param language_server_factory: factory for language server creation; if None, dynamic (re)creation of language servers
            is not supported
        :param project_root: the project root path; required when language_servers is empty
        """
        self._language_servers = language_servers
        self._language_server_factory = language_server_factory

        # Handle empty language servers (when allow_no_language_servers is enabled)
        if language_servers:
            self._default_language_server: SolidLanguageServer | None = next(iter(language_servers.values()))
            self._root_path = self._default_language_server.repository_root_path
        else:
            self._default_language_server = None
            if project_root is None:
                raise ValueError("project_root must be provided when no language servers are available")
            self._root_path = project_root

    @staticmethod
    def from_languages(languages: list[Language], factory: LanguageServerFactory) -> "LanguageServerManager":
        """
        Creates a manager with language servers for the given languages using the given factory.
        The language servers are started in parallel threads.

        :param languages: the languages for which to spawn language servers; can be empty when allow_no_language_servers is enabled
        :param factory: the factory for language server creation
        :return: the instance
        """
        language_servers: dict[Language, SolidLanguageServer] = {}

        # Handle empty languages list (when allow_no_language_servers is enabled)
        if not languages:
            return LanguageServerManager(language_servers, factory, project_root=factory.project_root)

        threads = []
        exceptions = {}
        lock = threading.Lock()

        def start_language_server(language: Language) -> None:
            try:
                with LogTime(f"Language server startup (language={language.value})"):
                    language_server = factory.create_language_server(language)
                    language_server.start()
                    if not language_server.is_running():
                        raise RuntimeError(f"Failed to start the language server for language {language.value}")
                    with lock:
                        language_servers[language] = language_server
            except Exception as e:
                log.error(f"Error starting language server for language {language.value}: {e}", exc_info=e)
                with lock:
                    exceptions[language] = e

        # start language servers in parallel threads
        for language in languages:
            thread = threading.Thread(target=start_language_server, args=(language,), name="StartLS:" + language.value)
            thread.start()
            threads.append(thread)
        for thread in threads:
            thread.join()

        # If any server failed to start up, raise an exception and stop all started language servers
        if exceptions:
            for ls in language_servers.values():
                ls.stop()
            failure_messages = "\n".join([f"{lang.value}: {e}" for lang, e in exceptions.items()])
            raise Exception(f"Failed to start language servers:\n{failure_messages}")

        return LanguageServerManager(language_servers, factory)

    def get_root_path(self) -> str:
        return self._root_path

    def _ensure_functional_ls(self, ls: SolidLanguageServer) -> SolidLanguageServer:
        if not ls.is_running():
            log.warning(f"Language server for language {ls.language} is not running; restarting ...")
            ls = self.restart_language_server(ls.language)
        return ls

    def get_language_server(self, relative_path: str) -> SolidLanguageServer:
        # Raise helpful error if no language servers are available
        if not self._language_servers:
            raise RuntimeError(
                "No language servers are available. This project was configured with an empty languages list. "
                "Symbolic operations (find_symbol, rename_symbol, etc.) are not available. "
                "Only file-based operations (read_file, list_dir, search_for_pattern, etc.) can be used."
            )

        ls: SolidLanguageServer | None = None
        if len(self._language_servers) > 1:
            for candidate in self._language_servers.values():
                if not candidate.is_ignored_path(relative_path, ignore_unsupported_files=True):
                    ls = candidate
                    break
        if ls is None:
            ls = self._default_language_server
        return self._ensure_functional_ls(ls)  # type: ignore[arg-type]

    def _create_and_start_language_server(self, language: Language) -> SolidLanguageServer:
        if self._language_server_factory is None:
            raise ValueError(f"No language server factory available to create language server for {language}")
        language_server = self._language_server_factory.create_language_server(language)
        language_server.start()
        self._language_servers[language] = language_server
        return language_server

    def restart_language_server(self, language: Language) -> SolidLanguageServer:
        """
        Forces recreation and restart of the language server for the given language.
        It is assumed that the language server for the given language is no longer running.

        :param language: the language
        :return: the newly created language server
        """
        if language not in self._language_servers:
            raise ValueError(f"No language server for language {language.value} present; cannot restart")
        return self._create_and_start_language_server(language)

    def add_language_server(self, language: Language) -> SolidLanguageServer:
        """
        Dynamically adds a new language server for the given language.

        :param language: the language
        :param factory: the factory to create the language server
        :return: the newly created language server
        """
        if language in self._language_servers:
            raise ValueError(f"Language server for language {language.value} already present")
        return self._create_and_start_language_server(language)

    def remove_language_server(self, language: Language, save_cache: bool = False) -> None:
        """
        Removes the language server for the given language, stopping it if it is running.

        :param language: the language
        """
        if language not in self._language_servers:
            raise ValueError(f"No language server for language {language.value} present; cannot remove")
        ls = self._language_servers.pop(language)
        self._stop_language_server(ls, save_cache=save_cache)

    def get_active_languages(self) -> list[Language]:
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
            log.info(f"Stopping language server for language {ls.language} ...")
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
