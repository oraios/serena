import logging
import threading
from collections.abc import Iterator

from sensai.util.logging import LogTime

from murena.config.murena_config import MurenaPaths, PerformanceConfig
from murena.constants import MURENA_MANAGED_DIR_NAME
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.settings import SolidLSPSettings
from solidlsp.util.async_cache import AsyncCachePersister

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
        performance_config: PerformanceConfig | None = None,
    ):
        self.project_root = project_root
        self.encoding = encoding
        self.ignored_patterns = ignored_patterns
        self.ls_timeout = ls_timeout
        self.ls_specific_settings = ls_specific_settings
        self.trace_lsp_communication = trace_lsp_communication
        self.performance_config = performance_config or PerformanceConfig()

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
                solidlsp_dir=MurenaPaths().serena_user_home_dir,
                project_data_relative_path=MURENA_MANAGED_DIR_NAME,
                ls_specific_settings=self.ls_specific_settings or {},
                performance=self.performance_config,
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
        async_cache_enabled: bool = True,
        async_cache_debounce_interval: float = 5.0,
        lsp_rate_limiting_enabled: bool = True,
        lsp_rate_limiting_rate: float = 50.0,
        lsp_rate_limiting_burst: int = 100,
    ) -> None:
        """
        :param language_servers: a mapping from language to language server; the servers are assumed to be already started.
            The first server in the iteration order is used as the default server.
            All servers are assumed to serve the same project root.
        :param language_server_factory: factory for language server creation; if None, dynamic (re)creation of language servers
            is not supported
        :param async_cache_enabled: whether to use async cache persistence (non-blocking writes)
        :param async_cache_debounce_interval: minimum time between cache writes (debouncing)
        :param lsp_rate_limiting_enabled: whether to enable rate limiting for LSP calls
        :param lsp_rate_limiting_rate: maximum LSP operations per second
        :param lsp_rate_limiting_burst: maximum burst capacity for rate limiting
        """
        self._language_servers = language_servers
        self._language_server_factory = language_server_factory
        self._default_language_server = next(iter(language_servers.values()))
        self._root_path = self._default_language_server.repository_root_path

        # Initialize async cache persister with configuration
        self._async_cache_persister = AsyncCachePersister(debounce_interval=async_cache_debounce_interval, enabled=async_cache_enabled)

        # Initialize LSP rate limiter
        self._lsp_rate_limiter: "RateLimiter | None" = None
        if lsp_rate_limiting_enabled:
            from murena.util.rate_limiter import RateLimiter

            self._lsp_rate_limiter = RateLimiter(rate=lsp_rate_limiting_rate, burst=lsp_rate_limiting_burst)
            log.debug(f"LSP rate limiting enabled: {lsp_rate_limiting_rate} ops/sec, burst={lsp_rate_limiting_burst}")

    @staticmethod
    def from_languages(
        languages: list[Language],
        factory: LanguageServerFactory,
        async_cache_enabled: bool = True,
        async_cache_debounce_interval: float = 5.0,
        lsp_rate_limiting_enabled: bool = True,
        lsp_rate_limiting_rate: float = 50.0,
        lsp_rate_limiting_burst: int = 100,
    ) -> "LanguageServerManager":
        """
        Creates a manager with language servers for the given languages using the given factory.
        The language servers are started in parallel threads.

        :param languages: the languages for which to spawn language servers
        :param factory: the factory for language server creation
        :param async_cache_enabled: whether to use async cache persistence
        :param async_cache_debounce_interval: minimum time between cache writes
        :param lsp_rate_limiting_enabled: whether to enable rate limiting
        :param lsp_rate_limiting_rate: maximum LSP ops/sec
        :param lsp_rate_limiting_burst: maximum burst capacity
        :return: the instance
        """
        language_servers: dict[Language, SolidLanguageServer] = {}
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

        return LanguageServerManager(
            language_servers,
            factory,
            async_cache_enabled=async_cache_enabled,
            async_cache_debounce_interval=async_cache_debounce_interval,
            lsp_rate_limiting_enabled=lsp_rate_limiting_enabled,
            lsp_rate_limiting_rate=lsp_rate_limiting_rate,
            lsp_rate_limiting_burst=lsp_rate_limiting_burst,
        )

    def get_root_path(self) -> str:
        return self._root_path

    def _ensure_functional_ls(self, ls: SolidLanguageServer) -> SolidLanguageServer:
        if not ls.is_running():
            log.warning(f"Language server for language {ls.language} is not running; restarting ...")
            ls = self.restart_language_server(ls.language)
        return ls

    def get_language_server(self, relative_path: str) -> SolidLanguageServer:
        ls: SolidLanguageServer | None = None
        if len(self._language_servers) > 1:
            for candidate in self._language_servers.values():
                if not candidate.is_ignored_path(relative_path, ignore_unsupported_files=True):
                    ls = candidate
                    break
        if ls is None:
            ls = self._default_language_server
        return self._ensure_functional_ls(ls)

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
        # Flush any pending async cache writes before stopping
        if save_cache:
            log.debug("Flushing pending async cache writes before shutdown")
            self._async_cache_persister.flush_all(timeout=10.0)

        for ls in self.iter_language_servers():
            self._stop_language_server(ls, save_cache=save_cache, timeout=timeout)

        # Shutdown the async cache persister
        self._async_cache_persister.shutdown(timeout=5.0)

    def save_all_caches(self) -> None:
        """
        Saves the caches of all managed language servers.
        """
        for ls in self.iter_language_servers():
            if ls.is_running():
                ls.save_cache()

    def schedule_async_cache_writes(self) -> None:
        """
        Schedule asynchronous cache writes for all language servers.

        This is a non-blocking alternative to save_all_caches() that schedules
        cache writes to happen in the background. Cache writes are debounced
        (default 5s) to batch multiple rapid updates.

        This method returns immediately (<1ms) compared to save_all_caches()
        which can block for 100-500ms.
        """
        for ls in self.iter_language_servers():
            if ls.is_running():
                # Schedule async save for each cache type
                self._schedule_ls_cache_write(ls)

    def _schedule_ls_cache_write(self, ls: SolidLanguageServer) -> None:
        """
        Schedule async write for a specific language server's caches.

        :param ls: The language server whose caches should be saved
        """
        # Schedule raw document symbols cache
        if ls._raw_document_symbols_cache_is_modified:
            cache_key = f"{ls.language.value}_raw_symbols"
            cache_file = ls.cache_dir / ls.RAW_DOCUMENT_SYMBOL_CACHE_FILENAME

            def save_raw_symbols(data: dict) -> None:
                from solidlsp.util.cache import save_cache

                save_cache(str(cache_file), ls._raw_document_symbols_cache_version(), data)
                ls._raw_document_symbols_cache_is_modified = False

            self._async_cache_persister.schedule_write(cache_key, ls._raw_document_symbols_cache, save_raw_symbols)

        # Schedule document symbols cache
        if ls._document_symbols_cache_is_modified:
            cache_key = f"{ls.language.value}_document_symbols"
            cache_file = ls.cache_dir / ls.DOCUMENT_SYMBOL_CACHE_FILENAME

            def save_document_symbols(data: dict) -> None:
                from solidlsp.util.cache import save_cache

                save_cache(str(cache_file), ls._document_symbols_cache_version(), data)
                ls._document_symbols_cache_is_modified = False

            self._async_cache_persister.schedule_write(cache_key, ls._document_symbols_cache, save_document_symbols)
