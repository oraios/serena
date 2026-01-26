"""
Tools for semantic search functionality.

Provides tools for indexing projects and performing semantic searches using embeddings.
"""

import logging
from typing import Any, Optional

from murena.tools.tools_base import Tool, ToolMarkerOptional

log = logging.getLogger(__name__)


class IndexProjectSemanticTool(Tool, ToolMarkerOptional):
    """
    Index the project for semantic search using embeddings.
    """

    def apply(
        self,
        incremental: bool = False,
        rebuild: bool = False,
        skip_tests: bool = True,
        skip_generated: bool = True,
        max_file_size: int = 10000,
    ) -> str:
        """
        Index the entire project for semantic search.

        This tool creates vector embeddings of your code (file metadata, symbols, and code chunks)
        and stores them in a local ChromaDB instance for fast semantic search.

        :param incremental: If True, only index files that have changed since last indexing. Default False.
        :param rebuild: If True, clear existing index and rebuild from scratch. Default False.
        :param skip_tests: If True, skip test files. Default True.
        :param skip_generated: If True, skip generated/build files. Default True.
        :param max_file_size: Maximum file size in lines to index. Default 10000.
        :return: A JSON string with indexing statistics including:
            - total_files: Total number of source files found
            - indexed_files: Number of files successfully indexed
            - skipped_files: Number of files skipped
            - total_symbols: Number of symbols indexed
            - total_chunks: Number of code chunks indexed
            - errors: Number of indexing errors
            - duration_seconds: Time taken for indexing
            - embedding_model: Name of the embedding model used
        """
        try:
            from murena.semantic import SEMANTIC_AVAILABLE

            if not SEMANTIC_AVAILABLE:
                return self._to_json(
                    {
                        "error": "Semantic search dependencies not installed",
                        "message": "Install with: uv pip install 'murena-agent[semantic]'",
                        "success": False,
                    }
                )

            from murena.semantic.indexer import SemanticIndexer

            indexer = SemanticIndexer(self.agent)
            stats = indexer.index_project(
                incremental=incremental,
                rebuild=rebuild,
                skip_tests=skip_tests,
                skip_generated=skip_generated,
                max_file_size=max_file_size,
            )

            stats["success"] = True
            return self._to_json(stats)

        except Exception as e:
            log.exception(f"Error indexing project: {e}")
            return self._to_json(
                {
                    "error": str(e),
                    "success": False,
                }
            )


class SemanticSearchTool(Tool, ToolMarkerOptional):
    """
    Perform semantic search over the indexed codebase.
    """

    def apply(
        self,
        query: str,
        max_results: int = 10,
        min_score: float = 0.5,
        file_filter: Optional[str] = None,
        language_filter: Optional[str] = None,
        type_filter: Optional[str] = None,
        compact_format: bool = True,
    ) -> str:
        """
        Search the codebase using natural language or code descriptions.

        This tool performs semantic search over your indexed code, finding relevant symbols
        and code sections based on meaning rather than exact keyword matches.

        Example queries:
        - "find all authentication logic"
        - "error handling for API requests"
        - "database connection initialization"
        - "user input validation"

        :param query: Natural language query or code description to search for
        :param max_results: Maximum number of results to return. Default 10.
        :param min_score: Minimum similarity score (0.0 to 1.0) for results. Default 0.5.
        :param file_filter: Optional glob-style pattern to filter files (e.g., "src/auth/**"). Default None.
        :param language_filter: Optional language filter (e.g., "python", "typescript"). Default None.
        :param type_filter: Optional type filter: "symbol", "file_metadata", or "chunk". Default None.
        :param compact_format: If True, return compact JSON format for token efficiency. Default True.
        :return: A JSON string with search results including:
            - query: The original search query
            - results: List of matching code locations with:
                - sc (score): Similarity score (0.0 to 1.0)
                - fp (file_path): Relative path to file
                - np (name_path): Symbol name path (if applicable)
                - k (kind): Symbol kind (if applicable)
                - ln (line): Line number (if applicable)
                - doc: Document preview/description
                - t (type): Result type (symbol/file_metadata/chunk)
            - total_results: Number of results returned
            - max_results: Maximum results requested
            - min_score: Minimum score threshold used
        """
        try:
            from murena.semantic import SEMANTIC_AVAILABLE

            if not SEMANTIC_AVAILABLE:
                return self._to_json(
                    {
                        "error": "Semantic search dependencies not installed",
                        "message": "Install with: uv pip install 'murena-agent[semantic]'",
                        "query": query,
                        "results": [],
                        "total_results": 0,
                    }
                )

            from murena.semantic.searcher import SemanticSearcher

            searcher = SemanticSearcher(self.agent)
            results = searcher.search(
                query=query,
                max_results=max_results,
                min_score=min_score,
                file_filter=file_filter,
                language_filter=language_filter,
                type_filter=type_filter,
                compact_format=compact_format,
            )

            return self._to_json(results)

        except Exception as e:
            log.exception(f"Error performing semantic search: {e}")
            return self._to_json(
                {
                    "error": str(e),
                    "query": query,
                    "results": [],
                    "total_results": 0,
                }
            )


class GetSemanticIndexStatusTool(Tool, ToolMarkerOptional):
    """
    Get the status of the semantic search index.
    """

    def apply(self) -> str:
        """
        Check the current status of the semantic search index.

        Returns information about:
        - Whether the project has been indexed
        - Number of embeddings in the index
        - Embedding model used
        - Index location and disk size

        :return: A JSON string with index status including:
            - indexed: Boolean indicating if index exists
            - embedding_count: Number of embeddings stored (if indexed)
            - embedding_model: Name of the embedding model used (if indexed)
            - collection_name: Name of the ChromaDB collection (if indexed)
            - index_path: Path to the index directory (if indexed)
            - disk_size_mb: Index size in megabytes (if indexed)
            - message: Status message (if not indexed)
            - error: Error message (if applicable)
        """
        try:
            from murena.semantic import SEMANTIC_AVAILABLE

            if not SEMANTIC_AVAILABLE:
                return self._to_json(
                    {
                        "indexed": False,
                        "error": "Semantic search dependencies not installed",
                        "message": "Install with: uv pip install 'murena-agent[semantic]'",
                    }
                )

            from murena.semantic.indexer import SemanticIndexer

            indexer = SemanticIndexer(self.agent)
            status = indexer.get_index_status()

            return self._to_json(status)

        except Exception as e:
            log.exception(f"Error getting index status: {e}")
            return self._to_json(
                {
                    "indexed": False,
                    "error": str(e),
                }
            )


class IntelligentSearchTool(Tool, ToolMarkerOptional):
    """
    Intelligent search with automatic routing between LSP, vector, and hybrid modes.
    """

    def apply(
        self,
        query: str,
        max_results: int = 10,
        min_score: float = 0.5,
        mode: Optional[str] = None,
        file_filter: Optional[str] = None,
        language_filter: Optional[str] = None,
        compact_format: bool = True,
    ) -> str:
        """
        Perform intelligent search with automatic mode selection.

        This tool automatically routes queries to the most appropriate search backend:
        - LSP (structural): For exact symbol names and identifiers
        - Vector (semantic): For natural language exploratory queries
        - Hybrid: For mixed queries combining structure and semantics

        The routing is automatic based on query analysis, but can be overridden with
        the 'mode' parameter.

        Example queries:
        - "UserService" → LSP (exact identifier)
        - "find all authentication logic" → Vector (exploratory)
        - "login method with JWT validation" → Hybrid (mixed)

        :param query: Search query (natural language or identifier)
        :param max_results: Maximum number of results to return. Default 10.
        :param min_score: Minimum similarity score (0.0 to 1.0) for vector results. Default 0.5.
        :param mode: Optional explicit mode: "lsp", "vector", "hybrid", or "auto" (default).
        :param file_filter: Optional glob-style pattern to filter files. Default None.
        :param language_filter: Optional language filter (e.g., "python"). Default None.
        :param compact_format: If True, return compact JSON format. Default True.
        :return: A JSON string with search results including:
            - query: The original search query
            - mode: Search mode used (lsp/vector/hybrid)
            - routing_reason: Explanation of mode selection
            - results: List of matching code locations
            - total_results: Number of results returned
            - sources: Source backends used (lsp, vector, or both)
        """
        try:
            from murena.semantic import SEMANTIC_AVAILABLE

            if not SEMANTIC_AVAILABLE:
                return self._to_json(
                    {
                        "error": "Semantic search dependencies not installed",
                        "message": "Install with: uv pip install 'murena-agent[semantic]'",
                        "query": query,
                        "results": [],
                        "total_results": 0,
                    }
                )

            from murena.semantic.reranker import ResultReranker
            from murena.semantic.router import QueryRouter, SearchMode
            from murena.semantic.searcher import SemanticSearcher

            # Route query
            router = QueryRouter()
            search_mode = router.route(query, mode)
            routing_info = router.get_routing_explanation(query, mode)

            log.info(f"Intelligent search: '{query}' → {search_mode.value}")

            # Execute search based on mode
            if search_mode == SearchMode.LSP:
                results = self._lsp_search(query, max_results, file_filter, compact_format)
                sources = ["lsp"]

            elif search_mode == SearchMode.VECTOR:
                searcher = SemanticSearcher(self.agent)
                search_results = searcher.search(
                    query=query,
                    max_results=max_results,
                    min_score=min_score,
                    file_filter=file_filter,
                    language_filter=language_filter,
                    compact_format=compact_format,
                )
                results = search_results["results"]
                sources = ["vector"]

            else:  # HYBRID
                # Get both LSP and vector results
                lsp_results = self._lsp_search(query, max_results * 2, file_filter, compact_format)

                searcher = SemanticSearcher(self.agent)
                vector_search = searcher.search(
                    query=query,
                    max_results=max_results * 2,
                    min_score=min_score,
                    file_filter=file_filter,
                    language_filter=language_filter,
                    compact_format=compact_format,
                )
                vector_results = vector_search["results"]

                # Merge with RRF
                reranker = ResultReranker()
                results = reranker.merge_results(lsp_results, vector_results, max_results)
                sources = ["lsp", "vector"]

            return self._to_json(
                {
                    "query": query,
                    "mode": search_mode.value,
                    "routing_reason": routing_info["reason"],
                    "results": results,
                    "total_results": len(results),
                    "sources": sources,
                }
            )

        except Exception as e:
            log.exception(f"Error in intelligent search: {e}")
            return self._to_json(
                {
                    "error": str(e),
                    "query": query,
                    "results": [],
                    "total_results": 0,
                }
            )

    def _lsp_search(
        self,
        query: str,
        max_results: int,
        file_filter: Optional[str],
        compact_format: bool,
    ) -> list[dict[str, Any]]:
        """
        Perform LSP symbol search.

        :param query: Symbol name or pattern
        :param max_results: Maximum results
        :param file_filter: Optional file filter
        :param compact_format: Use compact format
        :return: List of results
        """
        try:
            retriever = self.create_language_server_symbol_retriever()
            symbols = retriever.find(
                name_path_pattern=query,
                within_relative_path=file_filter or None,
                substring_matching=True,
            )

            results = []
            for symbol in symbols[:max_results]:
                if compact_format:
                    result = {
                        "fp": symbol.relative_path,
                        "np": symbol.get_name_path(),
                        "k": symbol.kind,
                        "ln": symbol.line,
                        "t": "symbol",
                        "sc": 1.0,  # LSP results have perfect score
                    }
                else:
                    result = {
                        "relative_path": symbol.relative_path,
                        "name_path": symbol.get_name_path(),
                        "kind": symbol.kind,
                        "line": symbol.line,
                        "type": "symbol",
                        "score": 1.0,
                    }
                results.append(result)

            return results

        except Exception as e:
            log.warning(f"LSP search failed: {e}")
            return []


class FindSimilarCodeTool(Tool, ToolMarkerOptional):
    """
    Find code similar to a given snippet for duplication detection.
    """

    def apply(
        self,
        code_snippet: str,
        max_results: int = 5,
        min_score: float = 0.7,
        file_filter: Optional[str] = None,
        language_filter: Optional[str] = None,
        compact_format: bool = True,
    ) -> str:
        """
        Find code similar to the given snippet.

        This tool uses semantic embeddings to find code that is semantically similar
        to the provided snippet, useful for:
        - Detecting code duplication
        - Finding similar implementations
        - Identifying refactoring opportunities

        :param code_snippet: Code snippet to find similar code for
        :param max_results: Maximum number of results to return. Default 5.
        :param min_score: Minimum similarity score (0.0 to 1.0). Default 0.7 (high similarity).
        :param file_filter: Optional glob-style pattern to filter files. Default None.
        :param language_filter: Optional language filter (e.g., "python"). Default None.
        :param compact_format: If True, return compact JSON format. Default True.
        :return: A JSON string with similar code results including:
            - code_snippet: The original code snippet
            - results: List of similar code locations with:
                - sc (score): Similarity score (0.0 to 1.0)
                - fp (file_path): Relative path to file
                - np (name_path): Symbol name path
                - k (kind): Symbol kind
                - ln (line): Line number
                - doc: Code preview
            - total_results: Number of results returned
            - min_score: Minimum score threshold used
        """
        try:
            from murena.semantic import SEMANTIC_AVAILABLE

            if not SEMANTIC_AVAILABLE:
                return self._to_json(
                    {
                        "error": "Semantic search dependencies not installed",
                        "message": "Install with: uv pip install 'murena-agent[semantic]'",
                        "code_snippet": code_snippet[:100] + "..." if len(code_snippet) > 100 else code_snippet,
                        "results": [],
                        "total_results": 0,
                    }
                )

            from murena.semantic.searcher import SemanticSearcher

            searcher = SemanticSearcher(self.agent)
            results = searcher.find_similar_code(
                code_snippet=code_snippet,
                max_results=max_results,
                min_score=min_score,
            )

            # Add snippet to response
            results["code_snippet"] = code_snippet[:100] + "..." if len(code_snippet) > 100 else code_snippet

            return self._to_json(results)

        except Exception as e:
            log.exception(f"Error finding similar code: {e}")
            return self._to_json(
                {
                    "error": str(e),
                    "code_snippet": code_snippet[:100] + "..." if len(code_snippet) > 100 else code_snippet,
                    "results": [],
                    "total_results": 0,
                }
            )
