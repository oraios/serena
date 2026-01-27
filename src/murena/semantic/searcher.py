"""
Semantic search functionality for code using embeddings.

This module provides functionality to search indexed code using semantic similarity.
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from murena.agent import MurenaAgent

log = logging.getLogger(__name__)

# Optional imports with graceful degradation
try:
    import chromadb
    from sentence_transformers import SentenceTransformer

    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False
    chromadb = None  # type: ignore
    SentenceTransformer = None  # type: ignore


class SemanticSearcher:
    """
    Provides semantic search capabilities over indexed code.

    This class uses the embeddings stored in ChromaDB to perform similarity
    searches and returns results in a compact, token-efficient format.
    """

    def __init__(self, agent: "MurenaAgent") -> None:
        """
        Initialize the semantic searcher.

        :param agent: The MurenaAgent instance to use for accessing the index
        """
        if not SEMANTIC_AVAILABLE:
            raise ImportError("Semantic search dependencies not installed. Install with: uv pip install 'murena-agent[semantic]'")

        self.agent = agent
        self._indexer: Optional[Any] = None
        self._query_expander: Optional[Any] = None  # Lazy load

    @property
    def indexer(self) -> Any:
        """Lazy-load the indexer for accessing model and collection."""
        if self._indexer is None:
            from murena.semantic.indexer import SemanticIndexer

            self._indexer = SemanticIndexer(self.agent)
        return self._indexer

    @property
    def query_expander(self) -> Any:
        """Lazy-load query expander."""
        if self._query_expander is None:
            from murena.semantic.query_expander import QueryExpander

            self._query_expander = QueryExpander(max_expansions=3)
        return self._query_expander

    def search(
        self,
        query: str,
        max_results: int = 10,
        min_score: float = 0.5,
        file_filter: Optional[str] = None,
        language_filter: Optional[str] = None,
        type_filter: Optional[str] = None,
        compact_format: bool = True,
        expand_query: bool = True,
    ) -> dict[str, Any]:
        """
        Perform semantic search over the indexed code.

        :param query: Natural language query or code description
        :param max_results: Maximum number of results to return
        :param min_score: Minimum similarity score (0.0 to 1.0)
        :param file_filter: Optional glob pattern to filter files (e.g., "src/auth/**")
        :param language_filter: Optional language filter (e.g., "python", "typescript")
        :param type_filter: Optional type filter ("symbol", "file_metadata", "chunk")
        :param compact_format: If True, return compact JSON format for token efficiency
        :param expand_query: If True, expand query with synonyms (default True)
        :return: Dictionary with search results and metadata
        """
        # Expand query if enabled
        original_query = query
        if expand_query:
            query = self.query_expander.expand(query, expand_enabled=True)

        log.info(f"Semantic search query: '{query}' (max_results={max_results}, min_score={min_score})")

        try:
            # Generate query embedding
            query_embedding = self.indexer.model.encode(query, convert_to_numpy=True).tolist()

            # Build where filter
            where_filter = self._build_where_filter(file_filter, language_filter, type_filter)

            # Perform search
            results = self.indexer.collection.query(
                query_embeddings=[query_embedding],
                n_results=max_results,
                where=where_filter if where_filter else None,
            )

            # Format results
            formatted_results = self._format_results(
                results,
                min_score=min_score,
                compact_format=compact_format,
            )

            result_dict = {
                "query": original_query,
                "results": formatted_results,
                "total_results": len(formatted_results),
                "max_results": max_results,
                "min_score": min_score,
            }

            # Include expanded query if different
            if expand_query and query != original_query:
                result_dict["expanded_query"] = query

            return result_dict

        except Exception as e:
            log.error(f"Error performing semantic search: {e}")
            return {
                "query": original_query,
                "results": [],
                "total_results": 0,
                "error": str(e),
            }

    def _build_where_filter(
        self,
        file_filter: Optional[str],
        language_filter: Optional[str],
        type_filter: Optional[str],
    ) -> Optional[dict[str, Any]]:
        """Build a ChromaDB where filter from search parameters."""
        filters = []

        if file_filter:
            # Simple prefix matching (more complex glob matching would require post-processing)
            filters.append({"relative_path": {"$contains": file_filter}})

        if language_filter:
            filters.append({"language": {"$eq": f".{language_filter}"}})

        if type_filter:
            filters.append({"type": {"$eq": type_filter}})

        if not filters:
            return None

        if len(filters) == 1:
            return filters[0]

        return {"$and": filters}

    def _format_results(
        self,
        results: dict[str, Any],
        min_score: float,
        compact_format: bool,
    ) -> list[dict[str, Any]]:
        """Format search results in standard or compact format."""
        formatted: list[dict[str, Any]] = []

        if not results or not results.get("ids"):
            return formatted

        # ChromaDB returns results in nested lists
        ids = results["ids"][0]
        distances = results["distances"][0]
        metadatas = results["metadatas"][0]
        documents = results["documents"][0]

        for idx, result_id in enumerate(ids):
            # Convert distance to similarity score (ChromaDB uses L2 distance)
            # For normalized embeddings: similarity = 1 - (distance^2 / 4)
            distance = distances[idx]
            score = max(0.0, 1.0 - (distance**2 / 4.0))

            # Filter by minimum score
            if score < min_score:
                continue

            metadata = metadatas[idx]
            document = documents[idx]

            if compact_format:
                result = self._format_compact(result_id, score, metadata, document)
            else:
                result = self._format_standard(result_id, score, metadata, document)

            formatted.append(result)

        return formatted

    def _format_compact(
        self,
        result_id: str,
        score: float,
        metadata: dict[str, Any],
        document: str,
    ) -> dict[str, Any]:
        """Format result in compact format (70% token savings)."""
        compact = {
            "sc": round(score, 3),  # score
            "fp": metadata.get("relative_path", ""),  # file_path
            "t": metadata.get("type", ""),  # type
        }

        # Add optional fields only if present
        if "name_path" in metadata:
            compact["np"] = metadata["name_path"]  # name_path

        if "kind" in metadata:
            compact["k"] = metadata["kind"]  # kind

        if "line" in metadata:
            compact["ln"] = metadata["line"]  # line

        # Add abbreviated document snippet
        doc_preview = document[:200] if len(document) > 200 else document
        compact["doc"] = doc_preview

        return compact

    def _format_standard(
        self,
        result_id: str,
        score: float,
        metadata: dict[str, Any],
        document: str,
    ) -> dict[str, Any]:
        """Format result in standard format."""
        result = {
            "id": result_id,
            "score": round(score, 3),
            "relative_path": metadata.get("relative_path", ""),
            "type": metadata.get("type", ""),
            "document": document,
        }

        # Add optional fields
        if "name_path" in metadata:
            result["name_path"] = metadata["name_path"]

        if "kind" in metadata:
            result["kind"] = metadata["kind"]

        if "line" in metadata:
            result["line"] = metadata["line"]

        if "language" in metadata:
            result["language"] = metadata["language"]

        return result

    def find_similar_code(
        self,
        code_snippet: str,
        max_results: int = 5,
        min_score: float = 0.7,
    ) -> dict[str, Any]:
        """
        Find code similar to the given snippet.

        :param code_snippet: Code snippet to find similar code for
        :param max_results: Maximum number of results
        :param min_score: Minimum similarity score
        :return: Search results
        """
        # For code similarity, we want exact symbol matches
        return self.search(
            query=code_snippet,
            max_results=max_results,
            min_score=min_score,
            type_filter="symbol",
            compact_format=True,
        )
