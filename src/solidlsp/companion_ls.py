"""Language server base class for frameworks requiring companion servers (Vue, Svelte, Astro)."""

from __future__ import annotations

import logging
import os
from abc import abstractmethod
from fnmatch import fnmatch
from pathlib import Path
from time import sleep

from overrides import override

from solidlsp import ls_types
from solidlsp.embedded_language_config import EmbeddedLanguageConfig
from solidlsp.ls import LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_utils import PathUtils

log = logging.getLogger(__name__)


class CompanionLanguageServer(SolidLanguageServer):
    """
    Abstract base class for language servers coordinating with companion servers.

    Manages companion server lifecycle, delegates LSP operations, and handles cross-file indexing.
    Subclasses must implement _get_domain_file_extension(), _get_embedded_language_configs(),
    and _create_companion_server().
    """

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self._companions: dict[str, SolidLanguageServer] = {}
        self._companion_configs: dict[str, EmbeddedLanguageConfig] = {}
        self._domain_files_indexed: bool = False
        self._indexed_file_uris: list[str] = []

    @abstractmethod
    def _get_domain_file_extension(self) -> str:
        pass

    @abstractmethod
    def _get_embedded_language_configs(self) -> list[EmbeddedLanguageConfig]:
        pass

    @abstractmethod
    def _create_companion_server(self, config: EmbeddedLanguageConfig) -> SolidLanguageServer:
        """
        Create companion server for given configuration. Server must not be started.

        :param config: Configuration for the embedded language
        :return: Configured but not yet started SolidLanguageServer instance
        """

    def _get_domain_specific_references(self, relative_file_path: str) -> list[ls_types.Location]:
        """
        Override to add domain-specific reference finding.

        :param relative_file_path: Path to file relative to repository root
        :return: List of domain-specific references
        """
        return []

    def _setup_domain_protocol_handlers(self) -> None:
        """Override to register domain-specific LSP handlers."""

    def _on_companions_ready(self) -> None:
        """Hook called after all companion servers are started."""

    def _merge_references(
        self,
        companion_refs: list[ls_types.Location],
        domain_refs: list[ls_types.Location],
    ) -> list[ls_types.Location]:
        """
        Merge and deduplicate references from companion and domain sources.

        :param companion_refs: References from companion language servers
        :param domain_refs: References from domain-specific sources
        :return: Deduplicated list of all references
        """
        seen: set[tuple[str, int, int]] = set()
        result: list[ls_types.Location] = []

        for ref in companion_refs + domain_refs:
            key = (
                ref["uri"],
                ref["range"]["start"]["line"],
                ref["range"]["start"]["character"],
            )
            if key not in seen:
                result.append(ref)
                seen.add(key)

        return result

    def _find_companion_for_operation(self, operation: str) -> SolidLanguageServer | None:
        """
        Find highest-priority companion server for the given operation.

        :param operation: Operation name (e.g., "definitions", "references", "rename")
        :return: Companion server with highest priority for operation, or None if none found
        """
        candidates: list[tuple[int, str]] = []

        for lang_id, config in self._companion_configs.items():
            handles_attr = f"handles_{operation}"
            if getattr(config, handles_attr, False):
                candidates.append((config.priority, lang_id))

        if not candidates:
            return None

        candidates.sort(reverse=True)
        return self._companions.get(candidates[0][1])

    def _find_all_domain_files(self) -> list[str]:
        """
        Find all domain files in repository, excluding ignored directories.

        :return: List of relative paths to domain files
        """
        ext = self._get_domain_file_extension()
        domain_files: list[str] = []
        repo_path = self.repository_root_path

        for dirpath, dirnames, filenames in os.walk(repo_path):
            dirnames[:] = [d for d in dirnames if not self.is_ignored_dirname(d)]

            for filename in filenames:
                if filename.endswith(ext):
                    abs_path = os.path.join(dirpath, filename)
                    relative_path = os.path.relpath(abs_path, repo_path)

                    try:
                        if not self.is_ignored_path(relative_path, ignore_unsupported_files=False):
                            domain_files.append(relative_path)
                    except Exception as e:
                        log.debug(f"Error checking if {relative_path} is ignored: {e}")

        return domain_files

    def _ensure_domain_files_indexed(self) -> None:
        """
        Index domain files on companion servers for cross-file references.

        Opens all domain files matching companion patterns on respective servers
        to enable cross-file symbol resolution.
        """
        if self._domain_files_indexed:
            return

        domain_files = self._find_all_domain_files()
        log.debug(f"Indexing {len(domain_files)} domain files on companion servers")

        for lang_id, config in self._companion_configs.items():
            companion = self._companions.get(lang_id)
            if companion is None:
                continue

            for domain_file in domain_files:
                matches = any(fnmatch(domain_file, pattern) for pattern in config.file_patterns)
                if not matches:
                    continue

                try:
                    absolute_file_path = os.path.join(companion.repository_root_path, domain_file)
                    uri = PathUtils.path_to_uri(absolute_file_path)

                    if uri in companion.open_file_buffers:
                        companion.open_file_buffers[uri].ref_count += 1
                        # Track URI so cleanup can decrement the ref-count we just added
                        self._indexed_file_uris.append(uri)
                    else:
                        with open(absolute_file_path, encoding=companion._encoding) as f:
                            contents = f.read()
                        language_id = companion._get_language_id_for_file(domain_file)
                        file_buffer = LSPFileBuffer(uri, contents, 0, language_id, 1)
                        companion.open_file_buffers[uri] = file_buffer

                        companion.server.notify.did_open_text_document(
                            {
                                "textDocument": {
                                    "uri": uri,
                                    "languageId": language_id,
                                    "version": 0,
                                    "text": contents,
                                }
                            }
                        )
                        self._indexed_file_uris.append(uri)
                except Exception as e:
                    log.debug(f"Failed to index {domain_file} on {lang_id} server: {e}")

        self._domain_files_indexed = True
        log.debug("Domain file indexing complete")

    def _cleanup_indexed_files(self) -> None:
        """
        Clean up indexed files on companion servers.

        Closes files that were opened for cross-file indexing and removes them
        from companion server buffers.
        """
        if not self._indexed_file_uris:
            return

        log.debug(f"Cleaning up {len(self._indexed_file_uris)} indexed files")

        failed_cleanups: list[tuple[str, str]] = []
        for uri in list(self._indexed_file_uris):
            for companion in self._companions.values():
                try:
                    if uri in companion.open_file_buffers:
                        file_buffer = companion.open_file_buffers[uri]
                        file_buffer.ref_count -= 1

                        if file_buffer.ref_count == 0:
                            companion.server.notify.did_close_text_document({"textDocument": {"uri": uri}})
                            del companion.open_file_buffers[uri]
                except Exception as e:
                    log.error(f"Error cleaning up indexed file {uri}: {e}")
                    failed_cleanups.append((uri, str(e)))

        if failed_cleanups:
            log.warning(f"Failed to cleanup {len(failed_cleanups)} indexed files - potential resource leak")

        self._indexed_file_uris.clear()

    def _send_companion_references_request(
        self,
        companion: SolidLanguageServer,
        relative_file_path: str,
        line: int,
        column: int,
    ) -> list[ls_types.Location]:
        """
        Send references request to companion, filtering to repository files.

        :param companion: Companion language server to query
        :param relative_file_path: Path to file relative to repository root
        :param line: Line number of symbol
        :param column: Column number of symbol
        :return: List of references within repository
        """
        uri = PathUtils.path_to_uri(os.path.join(self.repository_root_path, relative_file_path))
        request_params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": column},
            "context": {"includeDeclaration": True},
        }

        with companion.open_file(relative_file_path):
            response = companion.handler.send.references(request_params)  # type: ignore[arg-type]

        result: list[ls_types.Location] = []
        if response is None:
            return result

        for item in response:
            abs_path = PathUtils.uri_to_path(item["uri"])
            if not Path(abs_path).is_relative_to(self.repository_root_path):
                log.debug(f"Skipping reference outside repository: {abs_path}")
                continue

            rel_path = Path(abs_path).relative_to(self.repository_root_path)
            if self.is_ignored_path(str(rel_path)):
                log.debug(f"Skipping ignored reference: {rel_path}")
                continue

            new_item: dict = dict(item)  # type: ignore[arg-type]
            new_item["absolutePath"] = str(abs_path)
            new_item["relativePath"] = str(rel_path)
            result.append(ls_types.Location(**new_item))  # type: ignore[typeddict-item]

        return result

    @override
    def request_definition(
        self,
        relative_file_path: str,
        line: int,
        column: int,
    ) -> list[ls_types.Location]:
        if not self.server_started:
            log.error("request_definition called before language server started")
            raise SolidLSPException("Language Server not started")

        companion = self._find_companion_for_operation("definitions")
        if companion:
            with companion.open_file(relative_file_path):
                definitions = companion.request_definition(relative_file_path, line, column)

            if len(definitions) > 1:
                preferred = self._get_preferred_definition(definitions)
                return [preferred]

            return definitions

        return super().request_definition(relative_file_path, line, column)

    @override
    def request_references(
        self,
        relative_file_path: str,
        line: int,
        column: int,
    ) -> list[ls_types.Location]:
        if not self.server_started:
            log.error("request_references called before language server started")
            raise SolidLSPException("Language Server not started")

        if not self._has_waited_for_cross_file_references:
            sleep(self._get_wait_time_for_cross_file_referencing())
            self._has_waited_for_cross_file_references = True

        self._ensure_domain_files_indexed()

        companion_refs: list[ls_types.Location] = []
        companion = self._find_companion_for_operation("references")
        if companion:
            companion_refs = self._send_companion_references_request(companion, relative_file_path, line, column)

        domain_refs = self._get_domain_specific_references(relative_file_path)

        return self._merge_references(companion_refs, domain_refs)

    @override
    def request_rename_symbol_edit(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        new_name: str,
    ) -> ls_types.WorkspaceEdit | None:
        if not self.server_started:
            log.error("request_rename_symbol_edit called before language server started")
            raise SolidLSPException("Language Server not started")

        companion = self._find_companion_for_operation("rename")
        if companion:
            with companion.open_file(relative_file_path):
                return companion.request_rename_symbol_edit(relative_file_path, line, column, new_name)

        return super().request_rename_symbol_edit(relative_file_path, line, column, new_name)

    def _start_companions(self) -> None:
        """
        Start all companion language servers.

        Creates and starts each companion server defined by embedded language configs.
        """
        for config in self._get_embedded_language_configs():
            log.info(f"Creating companion server for {config.language_id}")
            companion = self._create_companion_server(config)

            log.info(f"Starting companion server for {config.language_id}")
            companion.start()

            self._companions[config.language_id] = companion
            self._companion_configs[config.language_id] = config
            log.info(f"Companion server for {config.language_id} ready")

        self._on_companions_ready()
        self._setup_domain_protocol_handlers()

    @override
    def stop(self, shutdown_timeout: float = 2.0) -> None:
        self._cleanup_indexed_files()

        failed_companions: list[str] = []
        for lang_id, companion in list(self._companions.items()):
            try:
                log.info(f"Stopping companion server for {lang_id}")
                companion.stop()
                del self._companions[lang_id]
                if lang_id in self._companion_configs:
                    del self._companion_configs[lang_id]
            except Exception as e:
                log.error(f"Error stopping companion server {lang_id}: {e}")
                failed_companions.append(lang_id)

        if failed_companions:
            log.error(f"Failed to stop companion servers: {', '.join(failed_companions)}")

        self._domain_files_indexed = False

        super().stop(shutdown_timeout)
