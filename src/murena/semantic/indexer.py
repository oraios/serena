"""
Semantic indexing for code using embeddings and vector storage.

This module provides functionality to index code at multiple levels (file metadata, symbols, chunks)
and store embeddings in ChromaDB for semantic search.
"""

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from sensai.util.logging import datetime_tag

if TYPE_CHECKING:
    from murena.agent import MurenaAgent

log = logging.getLogger(__name__)

# Optional imports with graceful degradation
try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer

    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False
    chromadb = None  # type: ignore
    Settings = None  # type: ignore
    SentenceTransformer = None  # type: ignore


class SemanticIndexer:
    """
    Manages semantic indexing of code projects using embeddings and vector storage.

    This class integrates with LSP symbol retrieval to extract code structure,
    generates embeddings using sentence-transformers models, and stores them
    in ChromaDB for efficient semantic search.
    """

    DEFAULT_EMBEDDING_MODEL = "jinaai/jina-embeddings-v2-base-code"
    FALLBACK_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    DEFAULT_COLLECTION_NAME = "code_embeddings"
    CHUNK_SIZE = 150  # tokens for chunking large function bodies
    MAX_FILE_SIZE_LINES = 10000  # skip files larger than this

    def __init__(self, agent: "MurenaAgent") -> None:
        """
        Initialize the semantic indexer.

        :param agent: The MurenaAgent instance to use for accessing project and LSP
        """
        if not SEMANTIC_AVAILABLE:
            raise ImportError("Semantic search dependencies not installed. Install with: uv pip install 'murena-agent[semantic]'")

        self.agent = agent
        self._model: Optional[SentenceTransformer] = None
        self._client: Optional[chromadb.ClientAPI] = None  # type: ignore
        self._collection: Optional[chromadb.Collection] = None  # type: ignore

    @property
    def model(self) -> SentenceTransformer:  # type: ignore
        """Lazy-load the embedding model."""
        if self._model is None:
            log.info(f"Loading embedding model: {self.DEFAULT_EMBEDDING_MODEL}")
            try:
                self._model = SentenceTransformer(self.DEFAULT_EMBEDDING_MODEL)
                log.info("Successfully loaded Jina Code V2 embedding model")
            except Exception as e:
                log.warning(f"Failed to load {self.DEFAULT_EMBEDDING_MODEL}: {e}. Falling back to {self.FALLBACK_EMBEDDING_MODEL}")
                self._model = SentenceTransformer(self.FALLBACK_EMBEDDING_MODEL)
                log.info(f"Successfully loaded fallback model: {self.FALLBACK_EMBEDDING_MODEL}")
        return self._model

    @property
    def chroma_client(self) -> chromadb.ClientAPI:  # type: ignore
        """Lazy-load the ChromaDB client."""
        if self._client is None:
            project = self.agent.get_active_project_or_raise()
            persist_dir = Path(project.project_root) / ".murena" / "semantic_index"
            persist_dir.mkdir(parents=True, exist_ok=True)

            log.info(f"Initializing ChromaDB client at {persist_dir}")
            self._client = chromadb.PersistentClient(
                path=str(persist_dir),
                settings=Settings(anonymized_telemetry=False),
            )
        return self._client

    @property
    def collection(self) -> chromadb.Collection:  # type: ignore
        """Get or create the embeddings collection."""
        if self._collection is None:
            self._collection = self.chroma_client.get_or_create_collection(
                name=self.DEFAULT_COLLECTION_NAME,
                metadata={"description": "Code embeddings for semantic search"},
            )
            log.info(f"Initialized collection: {self.DEFAULT_COLLECTION_NAME}")
        return self._collection

    def index_project(
        self,
        incremental: bool = False,
        rebuild: bool = False,
        skip_tests: bool = True,
        skip_generated: bool = True,
        max_file_size: int = 10000,
        cleanup_orphans: bool = True,
    ) -> dict[str, Any]:
        """
        Index the entire project for semantic search.

        :param incremental: If True, only index files that have changed since last indexing
        :param rebuild: If True, clear existing index and rebuild from scratch
        :param skip_tests: If True, skip test files
        :param skip_generated: If True, skip generated/build files
        :param max_file_size: Maximum file size in lines to index
        :param cleanup_orphans: If True, remove deleted files from index during incremental updates
        :return: Dictionary with indexing statistics
        """
        start_time = datetime.now()
        log.info(
            f"[{datetime_tag()}] Starting semantic indexing (incremental={incremental}, rebuild={rebuild}, cleanup_orphans={cleanup_orphans})"
        )

        project = self.agent.get_active_project_or_raise()
        ls_manager = self.agent.get_language_server_manager_or_raise()

        # Rebuild if requested
        if rebuild:
            log.info("Rebuilding index from scratch")
            self.chroma_client.delete_collection(self.DEFAULT_COLLECTION_NAME)
            self._collection = None  # Force recreation

        # Gather source files
        source_files = project.gather_source_files()
        log.info(f"Found {len(source_files)} source files")

        # Cleanup orphaned files if requested and in incremental mode
        orphans_removed = 0
        if cleanup_orphans and incremental and not rebuild:
            try:
                collection = self.collection
                all_data = collection.get()
                indexed_metadata = all_data.get("metadatas")
                if indexed_metadata:
                    indexed_paths = {str(m.get("relative_path")) for m in indexed_metadata if m and "relative_path" in m}

                    current_paths = set(source_files)  # source_files are already relative path strings
                    orphaned = indexed_paths - current_paths

                    if orphaned:
                        log.info(f"Removing {len(orphaned)} orphaned files from index")
                        for path in orphaned:
                            try:
                                self._remove_file_embeddings(path)
                                orphans_removed += 1
                            except Exception as e:
                                log.warning(f"Error removing orphaned file {path}: {e}")
            except Exception as e:
                log.warning(f"Error during orphan cleanup: {e}")

        # Filter files
        filtered_files = self._filter_files(
            source_files,
            skip_tests=skip_tests,
            skip_generated=skip_generated,
            max_file_size=max_file_size,
        )
        log.info(f"Filtered to {len(filtered_files)} files for indexing")

        # Index files
        stats: dict[str, Any] = {
            "total_files": len(source_files),
            "indexed_files": 0,
            "skipped_files": len(source_files) - len(filtered_files),
            "orphans_removed": orphans_removed,
            "total_symbols": 0,
            "total_chunks": 0,
            "errors": 0,
            "start_time": start_time.isoformat(),
        }

        embeddings_batch = []
        documents_batch = []
        metadatas_batch = []
        ids_batch = []

        for file_path in filtered_files:
            try:
                file_embeddings = self._index_file(file_path, ls_manager, incremental)
                if file_embeddings:
                    embeddings_batch.extend([e["embedding"] for e in file_embeddings])
                    documents_batch.extend([e["document"] for e in file_embeddings])
                    metadatas_batch.extend([e["metadata"] for e in file_embeddings])
                    ids_batch.extend([e["id"] for e in file_embeddings])

                    stats["indexed_files"] += 1
                    stats["total_symbols"] += sum(1 for e in file_embeddings if e["metadata"]["type"] == "symbol")
                    stats["total_chunks"] += sum(1 for e in file_embeddings if e["metadata"]["type"] == "chunk")

                # Batch insert every 100 items
                if len(embeddings_batch) >= 100:
                    self._insert_batch(embeddings_batch, documents_batch, metadatas_batch, ids_batch)
                    embeddings_batch = []
                    documents_batch = []
                    metadatas_batch = []
                    ids_batch = []

            except Exception as e:
                log.error(f"Error indexing {file_path}: {e}")
                stats["errors"] += 1

        # Insert remaining batch
        if embeddings_batch:
            self._insert_batch(embeddings_batch, documents_batch, metadatas_batch, ids_batch)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        stats["end_time"] = end_time.isoformat()
        stats["duration_seconds"] = duration
        stats["embedding_model"] = self.DEFAULT_EMBEDDING_MODEL

        log.info(
            f"Indexing complete: {stats['indexed_files']} files, {stats['total_symbols']} symbols, {orphans_removed} orphans removed in {duration:.2f}s"
        )

        return stats

    def _filter_files(
        self,
        files: list[str],
        skip_tests: bool,
        skip_generated: bool,
        max_file_size: int,
    ) -> list[str]:
        """Filter files based on criteria."""
        project = self.agent.get_active_project_or_raise()
        filtered = []
        for file_path_str in files:
            file_path = Path(project.project_root) / file_path_str

            # Skip test files
            if skip_tests and self._is_test_file(file_path):
                continue

            # Skip generated files
            if skip_generated and self._is_generated_file(file_path):
                continue

            # Skip large files
            try:
                line_count = len(file_path.read_text(encoding="utf-8", errors="ignore").splitlines())
                if line_count > max_file_size:
                    log.debug(f"Skipping large file: {file_path} ({line_count} lines)")
                    continue
            except Exception:
                continue

            filtered.append(file_path_str)

        return filtered

    def _is_test_file(self, file_path: Path) -> bool:
        """Check if file is a test file."""
        parts = file_path.parts
        name = file_path.name.lower()
        return "test" in parts or "tests" in parts or name.startswith("test_") or name.endswith(("_test.py", ".test.ts", ".spec.ts"))

    def _is_generated_file(self, file_path: Path) -> bool:
        """Check if file is generated."""
        parts = file_path.parts
        name = file_path.name.lower()
        return "generated" in parts or "build" in parts or "dist" in parts or ".generated." in name or name.endswith((".pb.py", ".g.dart"))

    def _index_file(
        self,
        file_path_str: str,
        ls_manager: Any,
        incremental: bool,
    ) -> list[dict[str, Any]]:
        """
        Index a single file at multiple levels.

        Returns list of embedding dictionaries with keys: id, embedding, document, metadata
        """
        project = self.agent.get_active_project_or_raise()
        file_path = Path(project.project_root) / file_path_str
        relative_path = file_path_str

        # Check if file needs indexing (for incremental mode)
        if incremental:
            file_hash = self._compute_file_hash(file_path)
            existing_metadata = self._get_file_metadata(str(relative_path))
            if existing_metadata and existing_metadata.get("file_hash") == file_hash:
                log.debug(f"Skipping unchanged file: {relative_path}")
                return []
            # File has changed - remove old embeddings
            if existing_metadata:
                log.debug(f"File changed, removing old embeddings: {relative_path}")
                self._remove_file_embeddings(relative_path)

        embeddings = []

        # Try to get symbols via LSP
        try:
            from murena.symbol import LanguageServerSymbolRetriever

            retriever = LanguageServerSymbolRetriever(ls_manager, self.agent)
            symbols = retriever.get_symbol_overview(relative_path, depth=2)

            # Index each symbol
            for symbol_dict in symbols[relative_path]:
                symbol_embedding = self._index_symbol(symbol_dict, relative_path, file_path)
                if symbol_embedding:
                    embeddings.append(symbol_embedding)

        except Exception as e:
            log.debug(f"Could not retrieve symbols for {relative_path}: {e}")

        # Fallback: index file metadata only
        if not embeddings:
            file_metadata_embedding = self._index_file_metadata(file_path, relative_path)
            if file_metadata_embedding:
                embeddings.append(file_metadata_embedding)

        return embeddings

    def _index_symbol(self, symbol_dict: dict[str, Any], relative_path: str, file_path: Path) -> Optional[dict[str, Any]]:
        """Index a single symbol (function/class/method)."""
        try:
            name_path = symbol_dict.get("name_path", "")
            kind = symbol_dict.get("kind", "")

            # Create document text for embedding
            document_parts = [
                f"Symbol: {name_path}",
                f"Kind: {kind}",
                f"File: {relative_path}",
            ]

            # Add docstring if available
            if "docstring" in symbol_dict:
                document_parts.append(f"Documentation: {symbol_dict['docstring']}")

            # Add signature if available
            if "signature" in symbol_dict:
                document_parts.append(f"Signature: {symbol_dict['signature']}")

            document = "\n".join(document_parts)

            # Generate embedding
            embedding = self.model.encode(document, convert_to_numpy=True).tolist()

            # Create unique ID
            symbol_id = self._generate_id(relative_path, name_path)

            # Metadata
            metadata = {
                "type": "symbol",
                "relative_path": relative_path,
                "name_path": name_path,
                "kind": kind,
                "file_hash": self._compute_file_hash(file_path),
                "indexed_at": datetime.now().isoformat(),
            }

            if "location" in symbol_dict:
                metadata["line"] = symbol_dict["location"].get("line", 0)

            return {
                "id": symbol_id,
                "embedding": embedding,
                "document": document,
                "metadata": metadata,
            }

        except Exception as e:
            log.warning(f"Error indexing symbol {symbol_dict.get('name_path')}: {e}")
            return None

    def _index_file_metadata(self, file_path: Path, relative_path: str) -> Optional[dict[str, Any]]:
        """Index file-level metadata."""
        try:
            # Read file content (limited)
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
            preview = "\n".join(lines[:20])  # First 20 lines

            # Create document
            document = f"File: {relative_path}\nLanguage: {file_path.suffix}\nPreview:\n{preview}"

            # Generate embedding
            embedding = self.model.encode(document, convert_to_numpy=True).tolist()

            # Create unique ID
            file_id = self._generate_id(relative_path, "file_metadata")

            # Metadata
            metadata = {
                "type": "file_metadata",
                "relative_path": relative_path,
                "language": file_path.suffix,
                "line_count": len(lines),
                "file_hash": self._compute_file_hash(file_path),
                "indexed_at": datetime.now().isoformat(),
            }

            return {
                "id": file_id,
                "embedding": embedding,
                "document": document,
                "metadata": metadata,
            }

        except Exception as e:
            log.warning(f"Error indexing file metadata for {relative_path}: {e}")
            return None

    def _insert_batch(
        self,
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str],
    ) -> None:
        """Insert a batch of embeddings into ChromaDB."""
        try:
            self.collection.upsert(  # type: ignore[call-arg]
                embeddings=embeddings,  # type: ignore[arg-type]
                documents=documents,
                metadatas=metadatas,  # type: ignore[arg-type]
                ids=ids,
            )
            log.debug(f"Inserted batch of {len(ids)} embeddings")
        except Exception as e:
            log.error(f"Error inserting batch: {e}")

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file content."""
        try:
            content = file_path.read_bytes()
            return hashlib.sha256(content).hexdigest()
        except Exception:
            return ""

    def _compute_freshness(self, stale_files: list[str], deleted_files: list[str], current_files: dict[str, str]) -> str:
        """Compute index freshness rating.

        Args:
            stale_files: List of files that have changed since indexing
            deleted_files: List of files that were deleted but still in index
            current_files: Dictionary of current files

        Returns:
            Freshness rating: "fresh", "mostly_fresh", "stale", "very_stale", or "unknown"

        """
        if not current_files:
            return "unknown"

        total_issues = len(stale_files) + len(deleted_files)
        issue_ratio = total_issues / len(current_files)

        if issue_ratio == 0:
            return "fresh"
        elif issue_ratio < 0.1:
            return "mostly_fresh"
        elif issue_ratio < 0.3:
            return "stale"
        else:
            return "very_stale"

    def _generate_id(self, relative_path: str, identifier: str) -> str:
        """Generate unique ID for an embedding."""
        combined = f"{relative_path}::{identifier}"
        return hashlib.md5(combined.encode()).hexdigest()

    def _get_file_metadata(self, relative_path: str) -> Optional[dict[str, Any]]:
        """Get existing metadata for a file from the index."""
        try:
            results = self.collection.get(
                where={"relative_path": relative_path, "type": "file_metadata"},
                limit=1,
            )
            if results and results["metadatas"]:
                return results["metadatas"][0]  # type: ignore[return-value]
        except Exception:
            pass
        return None

    def _remove_file_embeddings(self, relative_path: str) -> None:
        """Remove all embeddings for a file from the index."""
        try:
            # Get all embeddings for this file
            results = self.collection.get(
                where={"relative_path": relative_path},
            )

            if results and results["ids"]:
                ids_to_delete = results["ids"]
                self.collection.delete(ids=ids_to_delete)
                log.debug(f"Removed {len(ids_to_delete)} embeddings for {relative_path}")

        except Exception as e:
            log.warning(f"Error removing embeddings for {relative_path}: {e}")

    def get_index_status(self) -> dict[str, Any]:
        """Get the current status of the semantic index with freshness analysis."""
        project = self.agent.get_active_project_or_raise()
        index_path = Path(project.project_root) / ".murena" / "semantic_index"

        if not index_path.exists():
            return {
                "indexed": False,
                "message": "No semantic index found",
            }

        try:
            collection = self.collection
            count = collection.count()

            # Get indexed files from ChromaDB
            all_data = collection.get()
            indexed_metadata = all_data.get("metadatas")
            indexed_files: dict[str, str] = {}
            if indexed_metadata:
                for metadata in indexed_metadata:
                    if metadata and "relative_path" in metadata and "file_hash" in metadata:
                        rel_path = metadata.get("relative_path")
                        file_hash = metadata.get("file_hash")
                        if isinstance(rel_path, str) and isinstance(file_hash, str):
                            indexed_files[rel_path] = file_hash

            # Get current files from project
            current_files: dict[str, str] = {}
            for rel_path in project.gather_source_files():
                try:
                    abs_path = Path(project.project_root) / rel_path
                    file_hash = self._compute_file_hash(abs_path)
                    if file_hash:
                        current_files[rel_path] = file_hash
                except Exception:
                    continue

            # Analyze freshness
            stale_files = []
            for path, current_hash in current_files.items():
                indexed_hash = indexed_files.get(path)
                if indexed_hash and indexed_hash != current_hash:
                    stale_files.append(path)

            # Detect deletions
            deleted_files = [p for p in indexed_files if p not in current_files]

            # Compute freshness rating
            freshness = self._compute_freshness(stale_files, deleted_files, current_files)

            # Calculate disk size
            disk_size = sum(f.stat().st_size for f in index_path.rglob("*") if f.is_file())
            disk_size_mb = disk_size / (1024 * 1024)

            return {
                "indexed": True,
                "embedding_count": count,
                "total_files": len(current_files),
                "indexed_files": len(indexed_files),
                "stale_files": len(stale_files),
                "deleted_files": len(deleted_files),
                "freshness": freshness,
                "embedding_model": self.DEFAULT_EMBEDDING_MODEL,
                "collection_name": self.DEFAULT_COLLECTION_NAME,
                "index_path": str(index_path),
                "disk_size_mb": round(disk_size_mb, 2),
            }

        except Exception as e:
            return {
                "indexed": False,
                "error": str(e),
            }
