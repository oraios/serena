"""
Document symbol cache repository (Phase 4 deep module).

This module owns:
- Raw document symbols cache (raw LSP responses)
- High-level DocumentSymbols cache (unified trees)
- Load/save/versioning/fingerprint logic
- The request_document_symbols orchestration (cache check → _request → convert → cache)

The DocumentSymbolRepository collaborates with the facade via narrow callbacks:
- get_raw_document_symbols: calls facade._request_document_symbols (policy hook)
- normalize_name: calls facade._normalize_symbol_name (policy hook)
- create_body: calls facade.create_symbol_body
- get_fingerprint: calls facade._document_symbols_cache_fingerprint
- open_file_context: uses facade._open_file_context for reading file content when needed

The facade retains:
- save_cache() public API (delegates to repository)
- _normalize_symbol_name and _document_symbols_cache_fingerprint as override hooks
- _request_document_symbols as an override hook (for raw post-processing)

Backward-compatible re-exports of cache-related names are not required; the main
pickle-stable classes (DocumentSymbols, SymbolBody, etc.) are re-exported from
solidlsp.ls via ls_symbol_model.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Hashable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sensai.util.pickle import load_pickle

from solidlsp.ls_symbol_model import (
    DocumentSymbols,
    RawDocumentSymbol,
    SymbolBodyFactory,
    convert_raw_document_symbols_to_unified,
)
from solidlsp.util.cache import load_cache, save_cache

if TYPE_CHECKING:
    from solidlsp.ls_documents import LSPFileBuffer

log = logging.getLogger(__name__)


class DocumentSymbolRepository:
    """
    Owns raw and high-level document symbol caches, their load/save/versioning,
    and the orchestration of request_document_symbols.

    The repository is a collaborator of SolidLanguageServer. It receives narrow
    callbacks for:
    - opening files (to read content and create body factories)
    - requesting raw symbols via the facade's _request_document_symbols hook
    - normalizing names via the facade's _normalize_symbol_name hook
    - creating bodies via the facade's create_symbol_body
    - obtaining cache fingerprint via the facade's _document_symbols_cache_fingerprint
    """

    # Filenames and legacy fallback are defined here as module-level constants
    # to keep them co-located with the cache logic. The facade re-exports the
    # version constants for backward compatibility.
    RAW_DOCUMENT_SYMBOL_CACHE_FILENAME = "raw_document_symbols.pkl"
    RAW_DOCUMENT_SYMBOL_CACHE_FILENAME_LEGACY_FALLBACK = "document_symbols_cache_v23-06-25.pkl"
    DOCUMENT_SYMBOL_CACHE_FILENAME = "document_symbols.pkl"

    def __init__(
        self,
        *,
        cache_dir: Path,
        raw_cache_version: Callable[[], tuple[Hashable, ...]],
        doc_cache_version: Callable[[], Hashable],
        get_fingerprint: Callable[[], Hashable | None],
        # NOTE: Accept the historical hook signature (and any adapter overrides) via a permissive
        # callable. The repository owns normalization/caching; the facade hook may return the
        # classic union-of-lists form or a flat union depending on overrides.
        request_raw_symbols: Callable[..., Any],
        normalize_name: Callable[[RawDocumentSymbol, str], str],
        create_body: Callable[..., Any],  # matches SolidLanguageServer.create_symbol_body signature
        open_file_context: Callable[..., Any],  # context manager like facade._open_file_context
        repository_root_path: str,
    ) -> None:
        self._cache_dir = cache_dir
        self._raw_cache_version = raw_cache_version
        self._doc_cache_version = doc_cache_version
        self._get_fingerprint = get_fingerprint
        self._request_raw_symbols = request_raw_symbols
        self._normalize_name = normalize_name
        self._create_body = create_body
        self._open_file_context = open_file_context
        self._repository_root_path = repository_root_path

        # Raw document symbols cache
        self._raw_document_symbols_cache: dict[str, tuple[str, list[RawDocumentSymbol] | None]] = {}
        self._raw_document_symbols_cache_is_modified: bool = False

        # High-level document symbols cache
        self._document_symbols_cache: dict[str, tuple[str, DocumentSymbols]] = {}
        self._document_symbols_cache_is_modified: bool = False

        # Load caches at construction time (mirrors prior behavior in facade __init__)
        self._load_raw_document_symbols_cache()
        self._load_document_symbols_cache()

    # ------------------------------------------------------------------
    # Public surface used by facade delegation
    # ------------------------------------------------------------------

    @property
    def raw_cache(self) -> dict[str, tuple[str, list[RawDocumentSymbol] | None]]:
        return self._raw_document_symbols_cache

    @property
    def doc_cache(self) -> dict[str, tuple[str, DocumentSymbols]]:
        return self._document_symbols_cache

    def request_document_symbols(
        self,
        relative_file_path: str,
        file_buffer: "LSPFileBuffer | None" = None,
    ) -> DocumentSymbols:
        """
        Retrieves the collection of symbols in the given file (high-level unified form).

        Mirrors the prior SolidLanguageServer.request_document_symbols behavior.
        """
        with self._open_file_context(relative_file_path, file_buffer, open_in_ls=False) as file_data:
            cache_key = relative_file_path
            file_hash_and_result = self._document_symbols_cache.get(cache_key)
            if file_hash_and_result is None:
                log.debug("No cache hit for document symbols in %s", relative_file_path)
                log.debug("perf: document_symbols_cache MISS path=%s", relative_file_path)
            else:
                file_hash, document_symbols = file_hash_and_result
                if file_hash == file_data.content_hash:
                    log.debug("Returning cached document symbols for %s", relative_file_path)
                    log.debug("perf: document_symbols_cache HIT path=%s", relative_file_path)
                    return document_symbols

                log.debug("Cached document symbol content for %s has changed", relative_file_path)
                log.debug("perf: document_symbols_cache STALE path=%s", relative_file_path)

            # no cached result: request the root symbols from the language server
            root_symbols = self._request_raw_symbols(relative_file_path, file_data)

            if root_symbols is None:
                log.warning(
                    f"Received None response from the Language Server for document symbols in {relative_file_path}. "
                    f"This means the language server can't understand this file (possibly due to syntax errors). It may also be due to a bug or misconfiguration of the LS. "
                    f"Returning empty list",
                )
                return DocumentSymbols([])

            assert isinstance(root_symbols, list), f"Unexpected response from Language Server: {root_symbols}"
            log.debug("Received %d root symbols for %s from the language server", len(root_symbols), relative_file_path)

            body_factory = SymbolBodyFactory(file_data)

            # Use the extracted conversion helper; pass facade callbacks for normalize/create_body
            unified_root_symbols = convert_raw_document_symbols_to_unified(
                root_symbols=root_symbols,
                relative_file_path=relative_file_path,
                repository_root_path=self._repository_root_path,
                normalize_name=self._normalize_name,
                create_body=self._create_body,
                body_factory=body_factory,
            )

            document_symbols = DocumentSymbols(unified_root_symbols)

            # update cache
            log.debug("Updating cached document symbols for %s", relative_file_path)
            self._document_symbols_cache[cache_key] = (file_data.content_hash, document_symbols)
            self._document_symbols_cache_is_modified = True

            return document_symbols

    # ------------------------------------------------------------------
    # Raw symbols (used by request_document_symbols and some direct callers)
    # ------------------------------------------------------------------

    def request_raw_document_symbols(
        self,
        relative_file_path: str,
        file_data: "LSPFileBuffer | None",
    ) -> list[RawDocumentSymbol] | None:
        """
        Sends a documentSymbol request or returns a cached raw result.

        Mirrors the prior SolidLanguageServer._request_document_symbols behavior
        (cache check, server call, conditional store).
        """

        def get_cached_raw_document_symbols(cache_key: str, fd: "LSPFileBuffer") -> list[RawDocumentSymbol] | None:
            file_hash_and_result = self._raw_document_symbols_cache.get(cache_key)
            if file_hash_and_result is None:
                log.debug("No cache hit for raw document symbols in %s", relative_file_path)
                log.debug("perf: raw_document_symbols_cache MISS path=%s", relative_file_path)
                return None

            file_hash, result = file_hash_and_result
            if file_hash == fd.content_hash:
                log.debug("Returning cached raw document symbols for %s", relative_file_path)
                log.debug("perf: raw_document_symbols_cache HIT path=%s", relative_file_path)
                return result

            log.debug("Document content for %s has changed (raw symbol cache is not up-to-date)", relative_file_path)
            log.debug("perf: raw_document_symbols_cache STALE path=%s", relative_file_path)
            return None

        def get_raw_document_symbols(fd: "LSPFileBuffer") -> list[RawDocumentSymbol] | None:
            cache_key = relative_file_path
            response = get_cached_raw_document_symbols(cache_key, fd)
            if response is not None:
                return response

            # Delegate to facade-provided raw requester (which calls server and may be overridden)
            log.debug(f"Requesting document symbols for {relative_file_path} from the Language Server")
            response = self._request_raw_symbols(relative_file_path, fd)

            # Only cache non-empty results. An empty or None response can occur when the language server
            # has not yet finished indexing or building the project (e.g. Lean 4 before `lake build`),
            # and caching it would permanently serve stale data even after the project is ready.
            if response:
                self._raw_document_symbols_cache[cache_key] = (fd.content_hash, response)
                self._raw_document_symbols_cache_is_modified = True

            return response

        with self._open_file_context(relative_file_path, file_buffer=file_data) as fd:
            return get_raw_document_symbols(fd)

    # ------------------------------------------------------------------
    # Save / Load
    # ------------------------------------------------------------------

    def save_raw_cache(self) -> None:
        cache_file = self._cache_dir / self.RAW_DOCUMENT_SYMBOL_CACHE_FILENAME

        if not self._raw_document_symbols_cache_is_modified:
            log.debug("No changes to raw document symbols cache, skipping save")
            return

        log.info("Saving updated raw document symbols cache to %s", cache_file)
        try:
            save_cache(str(cache_file), self._raw_cache_version(), self._raw_document_symbols_cache)
            self._raw_document_symbols_cache_is_modified = False
        except Exception as e:
            log.error(
                "Failed to save raw document symbols cache to %s: %s. Note: this may have resulted in a corrupted cache file.",
                cache_file,
                e,
            )

    def save_doc_cache(self) -> None:
        cache_file = self._cache_dir / self.DOCUMENT_SYMBOL_CACHE_FILENAME

        if not self._document_symbols_cache_is_modified:
            log.debug("No changes to document symbols cache, skipping save")
            return

        log.info("Saving updated document symbols cache to %s", cache_file)
        try:
            save_cache(str(cache_file), self._doc_cache_version(), self._document_symbols_cache)
            self._document_symbols_cache_is_modified = False
        except Exception as e:
            log.error(
                "Failed to save document symbols cache to %s: %s. Note: this may have resulted in a corrupted cache file.",
                cache_file,
                e,
            )

    def save_all(self) -> None:
        """Save both raw and document symbol caches."""
        self.save_raw_cache()
        self.save_doc_cache()

    def _load_raw_document_symbols_cache(self) -> None:
        cache_file = self._cache_dir / self.RAW_DOCUMENT_SYMBOL_CACHE_FILENAME

        if not cache_file.exists():
            # check for legacy cache to load to migrate
            legacy_cache_file = self._cache_dir / self.RAW_DOCUMENT_SYMBOL_CACHE_FILENAME_LEGACY_FALLBACK
            if legacy_cache_file.exists():
                try:
                    legacy_cache: dict[str, tuple[str, tuple[list[Any], list[Any]]]] = load_pickle(legacy_cache_file)
                    log.info("Migrating legacy document symbols cache with %d entries", len(legacy_cache))
                    num_symbols_migrated = 0
                    migrated_cache: dict[str, tuple[str, Any]] = {}
                    for cache_key, (file_hash, (all_symbols, root_symbols)) in legacy_cache.items():
                        if cache_key.endswith("-True"):  # include_body=True
                            new_cache_key = cache_key[:-5]
                            migrated_cache[new_cache_key] = (file_hash, root_symbols)
                            num_symbols_migrated += len(all_symbols)
                    log.info("Migrated %d document symbols from legacy cache", num_symbols_migrated)
                    self._raw_document_symbols_cache = migrated_cache
                    self._raw_document_symbols_cache_is_modified = True
                    self.save_raw_cache()
                    legacy_cache_file.unlink()
                    return
                except Exception as e:
                    log.error("Error during cache migration: %s", e)
                    return

        # load existing cache (if any)
        if cache_file.exists():
            log.info("Loading document symbols cache from %s", cache_file)
            try:
                saved_cache = load_cache(str(cache_file), self._raw_cache_version())
                if saved_cache is not None:
                    self._raw_document_symbols_cache = saved_cache
                    log.info(f"Loaded {len(self._raw_document_symbols_cache)} entries from raw document symbols cache.")
            except Exception as e:
                # cache can become corrupt, so just skip loading it
                log.warning(
                    "Failed to load raw document symbols cache from %s (%s); Ignoring cache.",
                    cache_file,
                    e,
                )

    def _load_document_symbols_cache(self) -> None:
        cache_file = self._cache_dir / self.DOCUMENT_SYMBOL_CACHE_FILENAME
        if cache_file.exists():
            log.info("Loading document symbols cache from %s", cache_file)
            try:
                saved_cache = load_cache(str(cache_file), self._doc_cache_version())
                if saved_cache is not None:
                    self._document_symbols_cache = saved_cache
                    log.info(f"Loaded {len(self._document_symbols_cache)} entries from document symbols cache.")
            except Exception as e:
                # cache can become corrupt, so just skip loading it
                log.warning(
                    "Failed to load document symbols cache from %s (%s); Ignoring cache.",
                    cache_file,
                    e,
                )
