"""
LSP Manager for handling multiple language servers in multi-language projects with memory budgeting.
"""

import logging
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language

if TYPE_CHECKING:
    from serena.project import Project

log = logging.getLogger(__name__)


@dataclass
class LSPInfo:
    """Information about a running language server."""

    lsp: SolidLanguageServer
    memory_mb: float  # Estimated memory usage
    last_used: datetime
    use_count: int


class LSPManager:
    """
    Manages multiple language servers for multi-language projects with memory budgeting.

    Uses an LRU (Least Recently Used) cache to keep multiple LSPs running simultaneously
    up to a memory budget. When the budget is exceeded, least recently used LSPs are evicted.
    """

    # Memory estimates based on repo size and real-world data from web search
    # Small repo: < 1,000 files
    # Medium repo: 1,000 - 10,000 files
    # Large repo: > 10,000 files

    MEMORY_ESTIMATES_SMALL = {
        Language.TYPESCRIPT: 200,
        Language.RUST: 300,
        Language.JAVA: 400,
        Language.PYTHON: 150,
        Language.GO: 100,
        Language.CPP: 250,
        Language.CSHARP: 300,
        Language.KOTLIN: 250,
        Language.SWIFT: 200,
        Language.PHP: 150,
        Language.RUBY: 150,
        Language.ELIXIR: 200,
        Language.BASH: 80,
        Language.LUA: 80,
        Language.PERL: 120,
        Language.R: 150,
        Language.CLOJURE: 250,
        Language.SCALA: 300,
        Language.ELM: 120,
        Language.NIX: 120,
        Language.ERLANG: 200,
        Language.AL: 150,
        Language.ZIG: 150,
    }

    MEMORY_ESTIMATES_MEDIUM = {
        Language.TYPESCRIPT: 600,  # Based on web search: 600MB-3GB range
        Language.RUST: 1200,  # Based on web search: 1-4GB typical, use lower bound
        Language.JAVA: 800,
        Language.PYTHON: 400,
        Language.GO: 250,
        Language.CPP: 600,
        Language.CSHARP: 700,
        Language.KOTLIN: 600,
        Language.SWIFT: 500,
        Language.PHP: 350,
        Language.RUBY: 350,
        Language.ELIXIR: 400,
        Language.BASH: 150,
        Language.LUA: 150,
        Language.PERL: 250,
        Language.R: 350,
        Language.CLOJURE: 500,
        Language.SCALA: 700,
        Language.ELM: 250,
        Language.NIX: 250,
        Language.ERLANG: 400,
        Language.AL: 350,
        Language.ZIG: 300,
    }

    MEMORY_ESTIMATES_LARGE = {
        Language.TYPESCRIPT: 1500,  # Based on web search: up to 3GB
        Language.RUST: 2500,  # Based on web search: 2-4GB for large projects
        Language.JAVA: 1500,
        Language.PYTHON: 800,
        Language.GO: 500,
        Language.CPP: 1200,
        Language.CSHARP: 1200,
        Language.KOTLIN: 1000,
        Language.SWIFT: 900,
        Language.PHP: 600,
        Language.RUBY: 600,
        Language.ELIXIR: 700,
        Language.BASH: 300,
        Language.LUA: 300,
        Language.PERL: 400,
        Language.R: 600,
        Language.CLOJURE: 800,
        Language.SCALA: 1200,
        Language.ELM: 400,
        Language.NIX: 400,
        Language.ERLANG: 700,
        Language.AL: 600,
        Language.ZIG: 500,
    }

    DEFAULT_MEMORY_ESTIMATE = 500  # MB (conservative for medium repos)

    def __init__(
        self,
        project: "Project",
        memory_budget_mb: int = 2048,
        log_level: int = logging.INFO,
        ls_timeout: float | None = None,
        trace_lsp_communication: bool = False,
        ls_specific_settings: dict[Language, Any] | None = None,
    ):
        """
        Initialize the LSP Manager.

        :param project: The project containing language configuration
        :param memory_budget_mb: Total memory budget for all LSPs in MB
        :param log_level: Log level for language servers
        :param ls_timeout: Timeout for LSP operations
        :param trace_lsp_communication: Whether to trace LSP communication
        :param ls_specific_settings: Language-specific LSP settings
        """
        self.project = project
        self.memory_budget_mb = memory_budget_mb
        self.log_level = log_level
        self.ls_timeout = ls_timeout
        self.trace_lsp_communication = trace_lsp_communication
        self.ls_specific_settings = ls_specific_settings or {}

        # Get available languages from project configuration
        self.available_languages = self._get_available_languages()

        # Use repo size from project config (no scanning needed!)
        self.repo_size = project.project_config.repo_size_category
        log.info(f"Repository size category from config: {self.repo_size}")

        # Select memory estimates based on repo size
        if self.repo_size == "small":
            self.memory_estimates = self.MEMORY_ESTIMATES_SMALL
            log.info("Using SMALL repo memory estimates")
        elif self.repo_size == "medium":
            self.memory_estimates = self.MEMORY_ESTIMATES_MEDIUM
            log.info("Using MEDIUM repo memory estimates")
        else:  # large
            self.memory_estimates = self.MEMORY_ESTIMATES_LARGE
            log.info("Using LARGE repo memory estimates")

        # Currently running LSPs
        self.active_lsps: dict[Language, LSPInfo] = {}

        # LRU tracker - OrderedDict maintains insertion order, we move to end on access
        self.lsp_usage_order: OrderedDict[Language, None] = OrderedDict()

        # Learned estimates from actual measurements (updated as LSPs start)
        self.learned_estimates: dict[Language, float] = {}

        # Validate memory budget and warn if excessive
        self._validate_memory_budget()

        log.info(f"LSPManager initialized with memory budget {memory_budget_mb}MB")
        log.info(f"Available languages: {[str(lang) for lang in self.available_languages.keys()]}")

    def _validate_memory_budget(self) -> None:
        """Validate memory budget and warn if it might exceed system resources."""
        try:
            import psutil

            # Get available system memory
            available_memory_mb = psutil.virtual_memory().available / (1024 * 1024)
            total_memory_mb = psutil.virtual_memory().total / (1024 * 1024)

            log.info(f"System memory: {total_memory_mb:.0f}MB total, {available_memory_mb:.0f}MB available")

            # Warn if budget exceeds available memory
            if self.memory_budget_mb > available_memory_mb:
                log.warning(
                    f"LSP memory budget ({self.memory_budget_mb}MB) exceeds available system memory ({available_memory_mb:.0f}MB)! "
                    f"This may cause swapping or OOM errors. Consider reducing --lsp-memory-budget."
                )

            # Warn if budget is more than 50% of total memory
            if self.memory_budget_mb > total_memory_mb * 0.5:
                log.warning(
                    f"LSP memory budget ({self.memory_budget_mb}MB) is more than 50% of total system memory ({total_memory_mb:.0f}MB). "
                    f"This may impact system performance."
                )

        except ImportError:
            log.debug("psutil not available, skipping memory validation")
        except Exception as e:
            log.debug(f"Could not validate memory budget: {e}")

    def _get_available_languages(self) -> dict[Language, float]:
        """Get the available languages and their composition from the project."""
        if self.project.project_config.languages_composition:
            return self.project.project_config.languages_composition
        else:
            # Fallback to single language for backwards compatibility
            return {self.project.project_config.language: 100.0}

    def _estimate_lsp_memory(self, language: Language) -> float:
        """
        Estimate memory needed for an LSP.

        Uses learned estimates if available (from previous measurements),
        otherwise uses repo-size-based estimates.
        """
        # If we've measured this LSP before in this session, use that
        if language in self.learned_estimates:
            estimate = self.learned_estimates[language]
            log.debug(f"Using learned estimate for {language}: {estimate:.1f}MB")
            return estimate

        # Otherwise use repo-size-based estimate
        estimate = self.memory_estimates.get(language, self.DEFAULT_MEMORY_ESTIMATE)
        log.debug(f"Using {self.repo_size} repo estimate for {language}: {estimate}MB")
        return estimate

    def _measure_actual_memory(self, lsp: SolidLanguageServer) -> float | None:
        """
        Measure actual memory usage of an LSP process.

        Requires psutil to be installed. If not available, returns None.
        """
        try:
            import psutil

            if lsp.server.process and lsp.server.process.pid:
                process = psutil.Process(lsp.server.process.pid)
                # Get RSS (Resident Set Size) in MB
                memory_mb = process.memory_info().rss / (1024 * 1024)
                log.debug(f"Measured actual memory for LSP: {memory_mb:.1f}MB")
                return memory_mb
        except ImportError:
            log.debug("psutil not available, using estimate")
            return None
        except Exception as e:
            log.debug(f"Could not measure memory: {e}")
            return None
        return None

    def _get_total_memory_usage(self) -> float:
        """Get total memory usage of all running LSPs."""
        return sum(info.memory_mb for info in self.active_lsps.values())

    def _mark_used(self, language: Language) -> None:
        """Mark an LSP as recently used (move to end of LRU queue)."""
        if language in self.lsp_usage_order:
            self.lsp_usage_order.move_to_end(language)
        else:
            self.lsp_usage_order[language] = None

        if language in self.active_lsps:
            info = self.active_lsps[language]
            info.last_used = datetime.now()
            info.use_count += 1
            log.debug(f"LSP {language} marked as used (count: {info.use_count})")

    def _evict_lru_lsp(self, needed_memory: float) -> None:
        """Evict least recently used LSPs until we have enough memory."""
        current_usage = self._get_total_memory_usage()

        log.info(f"Need to free memory: current={current_usage}MB, needed={needed_memory}MB, budget={self.memory_budget_mb}MB")

        while current_usage + needed_memory > self.memory_budget_mb and self.lsp_usage_order:
            # Get least recently used language (first in OrderedDict)
            lru_language = next(iter(self.lsp_usage_order))
            lsp_info = self.active_lsps[lru_language]

            log.info(
                f"Evicting {lru_language} LSP (LRU, last used: {lsp_info.last_used.strftime('%H:%M:%S')}, "
                f"use count: {lsp_info.use_count}, memory: {lsp_info.memory_mb}MB)"
            )

            # Stop and remove the LSP
            lsp_info.lsp.stop()
            del self.active_lsps[lru_language]
            del self.lsp_usage_order[lru_language]

            current_usage = self._get_total_memory_usage()
            log.info(f"After eviction: memory usage = {current_usage}MB")

        if current_usage + needed_memory > self.memory_budget_mb:
            raise MemoryError(
                f"Cannot fit LSP in memory budget. "
                f"Need {needed_memory}MB but only {self.memory_budget_mb - current_usage}MB available. "
                f"Consider increasing lsp_memory_budget_mb in config."
            )

    def get_lsp_for_language(self, language: Language) -> SolidLanguageServer:
        """
        Get or create a language server for the specified language.

        Multiple LSPs can run simultaneously up to the memory budget.
        If budget is exceeded, least recently used LSPs are evicted.

        :param language: The language to get the LSP for
        :return: The language server instance
        """
        log.info(f"get_lsp_for_language called for: {language}")
        log.info(f"Current active LSPs: {list(self.active_lsps.keys())}")
        log.info(f"Current memory usage: {self._get_total_memory_usage()}MB / {self.memory_budget_mb}MB")

        if language not in self.available_languages:
            raise ValueError(
                f"Language {language} not found in project. Available languages: "
                f"{[str(lang) for lang in self.available_languages.keys()]}"
            )

        # If already running, mark as used and return
        if language in self.active_lsps:
            log.info(f"LSP for {language} already running, reusing")
            self._mark_used(language)
            return self.active_lsps[language].lsp

        # Estimate memory needed for this LSP
        needed_memory = self._estimate_lsp_memory(language)
        log.info(f"Need {needed_memory}MB for {language} LSP")

        # Check if we need to evict LSPs to free memory
        current_usage = self._get_total_memory_usage()
        if current_usage + needed_memory > self.memory_budget_mb:
            self._evict_lru_lsp(needed_memory)

        # Create and start the new LSP
        log.info(f"Creating new {language} LSP")
        lsp = self._create_lsp_for_language(language)

        log.info(f"Starting {language} LSP...")
        lsp.start()
        log.info(f"LSP start() completed for {language}")

        if not lsp.is_running():
            log.error(f"Failed to start {language} language server - is_running() returned False")
            raise RuntimeError(f"Failed to start {language} language server")

        log.info(f"Successfully started {language} LSP")

        # Try to measure actual memory, fall back to estimate
        actual_memory = self._measure_actual_memory(lsp)
        final_memory = actual_memory if actual_memory is not None else needed_memory

        if actual_memory is not None:
            log.info(f"Actual memory usage for {language}: {actual_memory:.1f}MB (estimated: {needed_memory}MB)")
            # Learn from this measurement for future use
            self.learned_estimates[language] = actual_memory
            log.info(f"Learned estimate saved for {language}: {actual_memory:.1f}MB")
        else:
            log.info(f"Using estimated memory for {language}: {needed_memory}MB (psutil not available for measurement)")

        # Track the new LSP
        lsp_info = LSPInfo(lsp=lsp, memory_mb=final_memory, last_used=datetime.now(), use_count=1)
        self.active_lsps[language] = lsp_info
        self.lsp_usage_order[language] = None

        log.info(f"New memory usage: {self._get_total_memory_usage():.1f}MB / {self.memory_budget_mb}MB")
        log.info(f"Active LSPs: {list(self.active_lsps.keys())}")

        return lsp

    def _create_lsp_for_language(self, language: Language) -> SolidLanguageServer:
        """
        Create a new language server instance for the specified language.

        :param language: The language to create the LSP for
        :return: The created language server instance
        """
        # Temporarily override the project's language to create the LSP
        original_language = self.project.project_config.language
        self.project.project_config.language = language

        try:
            lsp = self.project.create_language_server(
                log_level=self.log_level,
                ls_timeout=self.ls_timeout,
                trace_lsp_communication=self.trace_lsp_communication,
                ls_specific_settings=self.ls_specific_settings,
            )
            return lsp
        finally:
            # Restore original language
            self.project.project_config.language = original_language

    def get_lsp_for_file(self, file_path: str) -> SolidLanguageServer:
        """
        Get the appropriate language server for a given file.

        Automatically detects the language from the file extension and
        returns the LSP for that language (creating/starting it if needed).

        :param file_path: Path to the file
        :return: The language server for that file
        """
        from serena.util.inspection import detect_language_from_file

        log.info(f"get_lsp_for_file called for: {file_path}")
        detected_language = detect_language_from_file(file_path)
        log.info(f"Detected language for {file_path}: {detected_language}")

        if detected_language is None:
            # Fall back to primary language if detection fails
            detected_language = self.project.project_config.language
            log.warning(f"Could not detect language for {file_path}, using primary language {detected_language}")

        # Check if detected language is available in the project
        if detected_language not in self.available_languages:
            # Fall back to primary language
            log.warning(
                f"Detected language {detected_language} not in available languages {list(self.available_languages.keys())}, falling back to primary"
            )
            detected_language = self.project.project_config.language
            log.info(f"Using primary language: {detected_language}")

        log.info(f"Calling get_lsp_for_language with: {detected_language}")
        return self.get_lsp_for_language(detected_language)

    def stop_all(self) -> None:
        """Stop all running language servers."""
        log.info(f"Stopping all LSPs ({len(self.active_lsps)} running)")
        for language, lsp_info in list(self.active_lsps.items()):
            log.info(f"Stopping {language} LSP")
            lsp_info.lsp.stop()

        self.active_lsps.clear()
        self.lsp_usage_order.clear()
        log.info("All LSPs stopped")

    def is_running(self) -> bool:
        """Check if any language server is currently running."""
        return len(self.active_lsps) > 0

    def get_active_language_server(self) -> SolidLanguageServer | None:
        """Get the most recently used language server, if any."""
        if not self.lsp_usage_order:
            return None
        # Get most recently used (last in OrderedDict)
        most_recent = list(self.lsp_usage_order.keys())[-1]
        return self.active_lsps[most_recent].lsp
