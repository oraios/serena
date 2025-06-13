import logging
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager

from pathspec import PathSpec

from multilspy import SyncLanguageServer
from multilspy.language_server import LSPFileBuffer, ReferenceInSymbol
from multilspy.multilspy_config import Language
from multilspy.multilspy_types import Position, UnifiedSymbolInformation
from serena.text_utils import MatchedConsecutiveLines

log = logging.getLogger(__name__)


class MultiLanguageServer:
    def __init__(self, servers: dict[Language, SyncLanguageServer]):
        self._servers = servers
        # assume all servers use same repo root
        self.repository_root_path = next(iter(servers.values())).repository_root_path

    def start(self) -> None:
        for lang, server in self._servers.items():
            log.info("Starting language server for %s", lang.value)
            server.start()

    def stop(self) -> None:
        for lang, server in self._servers.items():
            if server.is_running():
                log.info("Stopping language server for %s", lang.value)
                server.stop()

    def save_cache(self) -> None:
        for server in self._servers.values():
            try:
                server.save_cache()
            except Exception as e:
                log.error("Error saving cache for %s: %s", server, e)

    def is_running(self) -> bool:
        return all(server.is_running() for server in self._servers.values())

    def get_ignore_spec(self) -> PathSpec:
        return next(iter(self._servers.values())).get_ignore_spec()

    def get_server(self, language: Language) -> SyncLanguageServer:
        return self._servers[language]

    def _server_for_path(self, relative_path: str) -> SyncLanguageServer:
        filename = os.path.basename(relative_path)
        for lang, server in self._servers.items():
            if lang.get_source_fn_matcher().is_relevant_filename(filename):
                return server
        log.debug("No specific language server for %s, using first", relative_path)
        return next(iter(self._servers.values()))

    @contextmanager
    def open_file(self, relative_file_path: str) -> Iterator[LSPFileBuffer]:
        server = self._server_for_path(relative_file_path)
        log.debug("Opening %s with %s", relative_file_path, server)
        with server.open_file(relative_file_path) as fb:
            yield fb

    # request methods
    def request_document_symbols(
        self, relative_file_path: str, include_body: bool = False
    ) -> tuple[list[UnifiedSymbolInformation], list[UnifiedSymbolInformation]]:
        server = self._server_for_path(relative_file_path)
        log.debug("Requesting document symbols for %s", relative_file_path)
        return server.request_document_symbols(relative_file_path, include_body)

    def request_full_symbol_tree(
        self, within_relative_path: str | None = None, include_body: bool = False, language: Language | None = None
    ) -> list[UnifiedSymbolInformation]:
        if language is not None:
            server = self.get_server(language)
            return server.request_full_symbol_tree(within_relative_path, include_body)
        if within_relative_path is not None:
            server = self._server_for_path(within_relative_path)
            return server.request_full_symbol_tree(within_relative_path, include_body)
        results = []
        for server in self._servers.values():
            results.extend(server.request_full_symbol_tree(None, include_body))
        return results

    def request_referencing_symbols(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        include_imports: bool = True,
        include_self: bool = False,
        include_body: bool = False,
        include_file_symbols: bool = False,
    ) -> list[ReferenceInSymbol]:
        server = self._server_for_path(relative_file_path)
        return server.request_referencing_symbols(
            relative_file_path=relative_file_path,
            line=line,
            column=column,
            include_imports=include_imports,
            include_self=include_self,
            include_body=include_body,
            include_file_symbols=include_file_symbols,
        )

    def retrieve_full_file_content(self, relative_file_path: str) -> str:
        server = self._server_for_path(relative_file_path)
        return server.retrieve_full_file_content(relative_file_path)

    def insert_text_at_position(self, relative_file_path: str, line: int, column: int, text_to_be_inserted: str) -> Position:
        server = self._server_for_path(relative_file_path)
        return server.insert_text_at_position(relative_file_path, line, column, text_to_be_inserted)

    def delete_text_between_positions(self, relative_file_path: str, start: Position, end: Position) -> str:
        server = self._server_for_path(relative_file_path)
        return server.delete_text_between_positions(relative_file_path, start, end)

    def retrieve_content_around_line(
        self, relative_file_path: str, line: int, context_lines_before: int = 0, context_lines_after: int = 0
    ) -> "MatchedConsecutiveLines":
        server = self._server_for_path(relative_file_path)
        return server.retrieve_content_around_line(relative_file_path, line, context_lines_before, context_lines_after)

    def search_files_for_pattern(
        self,
        pattern: str | re.Pattern,
        context_lines_before: int = 0,
        context_lines_after: int = 0,
        paths_include_glob: str | None = None,
        paths_exclude_glob: str | None = None,
    ) -> list[MatchedConsecutiveLines]:
        results: list[MatchedConsecutiveLines] = []
        for server in self._servers.values():
            results.extend(
                server.search_files_for_pattern(
                    pattern,
                    context_lines_before,
                    context_lines_after,
                    paths_include_glob,
                    paths_exclude_glob,
                )
            )
        return results

    def request_overview(self, within_relative_path: str) -> dict:
        if os.path.isfile(os.path.join(self.repository_root_path, within_relative_path)):
            server = self._server_for_path(within_relative_path)
            return server.request_overview(within_relative_path)
        results = {}
        for server in self._servers.values():
            results.update(server.request_overview(within_relative_path))
        return results
