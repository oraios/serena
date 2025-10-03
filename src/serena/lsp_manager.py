"""
LSPManager - Manages multiple language server instances for polyglot projects.

This module provides the LSPManager class which handles:
- Multiple LSP instances (one per language)
- Lazy initialization (LSPs start on-demand)
- Graceful degradation (one LSP failure doesn't crash the project)
- File routing (correct LSP for each file based on extension)
- Async startup with timeout
- Shutdown cleanup

Issue: #221 - Enable Multi-Language (Polyglot) Support in Serena
"""

import asyncio
import logging
from typing import Optional

from serena.config.serena_config import DEFAULT_TOOL_TIMEOUT, ProjectConfig
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class LSPManager:
    """
    Manages multiple language server instances for polyglot projects.

    Features:
    - Lazy initialization: LSPs start on-demand (default) or eagerly
    - Graceful degradation: One LSP failure doesn't crash the project
    - File routing: Routes files to appropriate LSP based on extension
    - Async startup: LSPs start asynchronously with timeout
    - Shutdown cleanup: Properly shuts down all LSPs

    Example:
        manager = LSPManager(
            languages=[Language.PYTHON, Language.RUST, Language.HASKELL],
            project_root="/path/to/project",
            config=project_config,
            logger=logger,
            settings=settings,
        )

        # Lazy initialization (default)
        await manager.start_all(lazy=True)

        # Get LSP for a specific file
        lsp = manager.get_language_server_for_file("src/main.rs")

        # Get all working LSPs
        working_lsps = manager.get_all_working_language_servers()

        # Shutdown all LSPs
        manager.shutdown_all()
    """

    def __init__(
        self,
        languages: list[Language],
        project_root: str,
        config: ProjectConfig,
        logger: LanguageServerLogger,
        settings: SolidLSPSettings,
        timeout: Optional[float] = None,
    ):
        """
        Initialize LSPManager with multiple languages.

        Args:
            languages: List of languages to support (must not be empty)
            project_root: Root directory of the project
            config: Project configuration
            logger: Logger for language server operations
            settings: SolidLSP settings
            timeout: Timeout for LSP requests (defaults to DEFAULT_TOOL_TIMEOUT)

        Raises:
            ValueError: If languages list is empty
        """
        if not languages:
            raise ValueError("LSPManager requires at least one language")

        self.languages = languages
        self.project_root = project_root
        self.config = config
        self.logger = logger
        self.settings = settings
        self.timeout = timeout if timeout is not None else DEFAULT_TOOL_TIMEOUT

        # Language server instances (populated on-demand or eagerly)
        self._language_servers: dict[Language, Optional[SolidLanguageServer]] = {}

        # Track failed languages to avoid repeated startup attempts
        self._failed_languages: set[Language] = set()

        # FIX #1: Add asyncio.Lock per language to prevent race conditions in lazy initialization
        self._startup_locks: dict[Language, asyncio.Lock] = {lang: asyncio.Lock() for lang in languages}

        # FIX #5: Cache file extension to language mapping for O(1) lookups
        self._extension_to_language: dict[str, Language] = {}
        self._build_extension_cache()

        log.info(f"LSPManager initialized for {len(languages)} languages: {[lang.value for lang in languages]}")

    def _build_extension_cache(self) -> None:
        """Build cache mapping file extensions to languages for fast lookups."""
        for language in self.languages:
            matcher = language.get_source_fn_matcher()
            for pattern in matcher.patterns:
                # Extract extension from pattern (e.g., "*.py" -> ".py")
                if pattern.startswith("*."):
                    ext = pattern[1:]  # Remove the "*"
                    # First match wins (no language priorities per user requirement)
                    if ext not in self._extension_to_language:
                        self._extension_to_language[ext] = language

    async def start_all(self, lazy: bool = True) -> None:
        """
        Start all language servers.

        Args:
            lazy: If True, LSPs are not started immediately (start on first use).
                  If False, all LSPs are started eagerly.

        Note:
            Failures are logged but don't raise exceptions (graceful degradation).
        """
        if lazy:
            log.info("LSPManager configured for lazy initialization (LSPs will start on first use)")
            return

        log.info(f"Starting {len(self.languages)} language servers eagerly...")

        # Start all LSPs concurrently
        tasks = [self._start_language_server(lang) for lang in self.languages]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # FIX #4: Handle and log results from asyncio.gather()
        success_count = 0
        failure_count = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                log.error(f"Failed to start {self.languages[i].value} LSP: {result}", exc_info=result)
                failure_count += 1
            elif result is not None:
                log.info(f"{self.languages[i].value} LSP started successfully")
                success_count += 1
            else:
                # None result means it was already started or failed
                if self.languages[i] in self._failed_languages:
                    failure_count += 1

        log.info(f"LSP startup complete: {success_count} succeeded, {failure_count} failed")

        if failure_count > 0:
            failed_langs = [lang.value for lang in self._failed_languages]
            log.warning(f"Failed to start LSPs for: {failed_langs}")

    async def _start_language_server(self, language: Language) -> Optional[SolidLanguageServer]:
        """
        Start a single language server with race condition protection.

        Args:
            language: The language to start LSP for

        Returns:
            The started language server, or None if startup failed
        """
        # FIX #1: Use asyncio.Lock to prevent race conditions in concurrent startup
        async with self._startup_locks[language]:
            # Check again after acquiring lock (another task may have started it)
            if language in self._failed_languages:
                log.debug(f"Skipping {language.value} LSP (previously failed)")
                return None

            if language in self._language_servers:
                log.debug(f"{language.value} LSP already started")
                return self._language_servers[language]

            try:
                log.info(f"Starting {language.value} language server...")

                # Create language server configuration
                ls_config = LanguageServerConfig(code_language=language)

                # Create language server instance
                lsp = SolidLanguageServer.create(
                    config=ls_config,
                    logger=self.logger,
                    repository_root_path=self.project_root,
                    timeout=self.timeout,
                    solidlsp_settings=self.settings,
                )

                # Start the language server
                await asyncio.wait_for(
                    asyncio.to_thread(lsp.start_server),
                    timeout=self.timeout,
                )

                self._language_servers[language] = lsp
                log.info(f"{language.value} language server started successfully")
                return lsp

            except asyncio.TimeoutError:
                # FIX #2: Proper logging for TimeoutError
                log.error(f"Timeout starting {language.value} language server (timeout={self.timeout}s)", exc_info=True)
                self._failed_languages.add(language)
                self._language_servers[language] = None
                return None

            except Exception as e:
                # FIX #2: Already has proper logging with exc_info=True
                log.error(f"Failed to start {language.value} language server: {e}", exc_info=True)
                self._failed_languages.add(language)
                self._language_servers[language] = None
                return None

    def get_language_for_file(self, file_path: str) -> Optional[Language]:
        """
        Determine which language a file belongs to based on its extension.

        Args:
            file_path: Path to the file (relative or absolute)

        Returns:
            The language for the file, or None if:
            - File extension doesn't match any language
            - File's language is not in the project's languages

        Example:
            >>> manager.get_language_for_file("src/main.rs")
            Language.RUST
            >>> manager.get_language_for_file("README.md")
            None
        """
        # FIX #5: Use cached extension mapping for O(1) lookup instead of O(n) linear search
        import os

        filename = os.path.basename(file_path)

        # Try cache first (fast path for common extensions like .py, .rs, .hs)
        for ext, language in self._extension_to_language.items():
            if filename.endswith(ext):
                return language

        # Fallback to full pattern matching for complex patterns (e.g., .test.ts, .spec.js)
        for language in self.languages:
            matcher = language.get_source_fn_matcher()
            if matcher.is_relevant_filename(filename):
                return language

        return None

    async def get_language_server_for_file(self, file_path: str) -> Optional[SolidLanguageServer]:
        """
        Get the language server for a specific file.

        This method implements lazy initialization: if the LSP hasn't been started yet,
        it will be started on first use.

        Args:
            file_path: Path to the file (relative or absolute)

        Returns:
            The language server for the file, or None if:
            - File's language cannot be determined
            - File's language is not in the project
            - LSP failed to start

        Example:
            >>> lsp = await manager.get_language_server_for_file("src/main.rs")
            >>> if lsp:
            ...     symbols = lsp.request_document_symbols("src/main.rs")
        """
        language = self.get_language_for_file(file_path)
        if language is None:
            return None

        # Check if LSP is already started
        if language in self._language_servers:
            return self._language_servers[language]

        # Lazy initialization: start LSP on first use
        log.debug(f"Lazy-starting {language.value} LSP for file: {file_path}")
        return await self._start_language_server(language)

    def get_all_working_language_servers(self) -> list[SolidLanguageServer]:
        """
        Get all successfully started language servers.

        Returns:
            List of working language servers (excludes failed/not-started LSPs)

        Example:
            >>> working_lsps = manager.get_all_working_language_servers()
            >>> for lsp in working_lsps:
            ...     print(f"Working LSP: {lsp.language.value}")
        """
        return [lsp for lang, lsp in self._language_servers.items() if lsp is not None and lang not in self._failed_languages]

    async def shutdown_all(self) -> None:
        """
        Shutdown all language servers and cleanup resources.

        FIX #3: Made async to properly handle async cleanup if needed.

        This should be called when the project is closed or the manager is no longer needed.

        Example:
            >>> await manager.shutdown_all()
        """
        log.info(f"Shutting down {len(self._language_servers)} language servers...")

        # Shutdown all LSPs concurrently for faster cleanup
        shutdown_tasks = []
        for language, lsp in self._language_servers.items():
            if lsp is not None:
                shutdown_tasks.append(self._shutdown_single_lsp(language, lsp))

        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)

        self._language_servers.clear()
        self._failed_languages.clear()
        log.info("All language servers shut down")

    async def _shutdown_single_lsp(self, language: Language, lsp: SolidLanguageServer) -> None:
        """Shutdown a single LSP with proper error handling."""
        try:
            log.debug(f"Shutting down {language.value} LSP...")
            # Use asyncio.to_thread in case stop_server is blocking
            await asyncio.to_thread(lsp.stop_server)
            log.debug(f"{language.value} LSP shut down successfully")
        except Exception as e:
            log.error(f"Error shutting down {language.value} LSP: {e}", exc_info=True)

    # FIX #3: Implement async context manager pattern for proper resource management
    async def __aenter__(self) -> "LSPManager":
        """
        Async context manager entry.

        Example:
            async with LSPManager(...) as manager:
                lsp = await manager.get_language_server_for_file("main.rs")
        """
        # Don't start servers eagerly - let lazy initialization handle it
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - ensures cleanup happens."""
        await self.shutdown_all()
        return None

    def __repr__(self) -> str:
        """String representation of LSPManager."""
        started = len(self._language_servers)
        failed = len(self._failed_languages)
        total = len(self.languages)
        return f"LSPManager(languages={total}, started={started}, failed={failed})"
