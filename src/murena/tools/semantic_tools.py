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
        use_ltr: bool = True,
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
        - "who calls authenticate?" → Call Graph (call hierarchy)

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
            search_mode, confidence = router.route_with_confidence(query, mode)
            routing_info = router.get_routing_explanation(query, mode)

            log.info(f"Intelligent search: '{query}' → {search_mode.value} (confidence: {confidence:.2f})")

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

            elif search_mode == SearchMode.CALL_GRAPH:
                # Call graph analysis mode
                results = self._call_graph_search(query, max_results, file_filter, compact_format)
                sources = ["call_graph"]

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
                results = reranker.merge_results(lsp_results, vector_results, max_results * 2)
                sources = ["lsp", "vector"]

            # Apply learned ranking if enabled
            reranker_used = "rrf"  # Default
            if use_ltr and len(results) > 0:
                try:
                    from murena.semantic.learned_ranker import LearnedRanker

                    learned_ranker = LearnedRanker(self.agent)
                    if learned_ranker.is_available:
                        results = learned_ranker.rerank(query, results, max_results, use_cold_start_fallback=True)
                        reranker_used = "ltr" if learned_ranker.is_trained else "cross_encoder"
                    else:
                        results = results[:max_results]
                except Exception as e:
                    log.warning(f"LTR reranking failed: {e}")
                    results = results[:max_results]
            else:
                results = results[:max_results]

            return self._to_json(
                {
                    "query": query,
                    "mode": search_mode.value,
                    "confidence": confidence,
                    "routing_reason": routing_info["reason"],
                    "reranker": reranker_used,
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

    def _call_graph_search(
        self,
        query: str,
        max_results: int,
        file_filter: Optional[str],
        compact_format: bool,
    ) -> list[dict[str, Any]]:
        """
        Perform call graph analysis search.

        Extracts symbol names from natural language queries like:
        - "who calls authenticate?"
        - "what does UserService call?"
        - "find callers of login"

        :param query: Natural language query about call relationships
        :param max_results: Maximum results
        :param file_filter: Optional file filter
        :param compact_format: Use compact format
        :return: List of results with call hierarchy info
        """
        import json
        import re

        try:
            # Extract symbol name from query using patterns
            # Patterns: "who calls X", "what calls X", "callers of X", "X calls what", etc.
            symbol_patterns = [
                r"(?:who|what)\s+calls?\s+([a-zA-Z_][a-zA-Z0-9_]*)",  # "who calls X"
                r"callers?\s+(?:of|for)\s+([a-zA-Z_][a-zA-Z0-9_]*)",  # "callers of X"
                r"called?\s+by\s+([a-zA-Z_][a-zA-Z0-9_]*)",  # "called by X"
                r"([a-zA-Z_][a-zA-Z0-9_]*)\s+calls?\s+(?:what|who)",  # "X calls what"
                r"([a-zA-Z_][a-zA-Z0-9_]*)\s+(?:uses|depends)",  # "X uses/depends"
                r"find\s+callers?\s+(?:of|for)?\s*([a-zA-Z_][a-zA-Z0-9_]*)",  # "find callers X"
            ]

            symbol_name = None
            for pattern in symbol_patterns:
                match = re.search(pattern, query, re.IGNORECASE)
                if match:
                    symbol_name = match.group(1)
                    break

            if not symbol_name:
                log.warning(f"Could not extract symbol name from call graph query: '{query}'")
                return []

            # Find the symbol using LSP
            retriever = self.create_language_server_symbol_retriever()
            symbols = retriever.find(
                name_path_pattern=symbol_name,
                within_relative_path=file_filter or None,
                substring_matching=True,
            )

            if not symbols:
                log.warning(f"Symbol '{symbol_name}' not found for call graph analysis")
                return []

            # Use first matching symbol
            symbol = symbols[0]

            # Determine direction: incoming (who calls) vs outgoing (what calls)
            query_lower = query.lower()
            is_incoming = any(
                kw in query_lower for kw in ["who calls", "called by", "callers", "incoming", "uses of", "used by", "depends on"]
            )

            # Get call graph data
            from murena.tools.call_graph_tools import GetIncomingCallsTool, GetOutgoingCallsTool

            if is_incoming:
                tool: GetIncomingCallsTool | GetOutgoingCallsTool = GetIncomingCallsTool(self.agent)
            else:
                tool = GetOutgoingCallsTool(self.agent)

            # Ensure relative_path is not None
            relative_path = symbol.relative_path
            if not relative_path:
                log.warning(f"Symbol '{symbol_name}' has no relative path")
                return []

            call_result = tool.apply(
                name_path=symbol.get_name_path(),
                relative_path=relative_path,
                include_call_sites=True,
                max_depth=2,  # Limited depth for intelligent search
                compact_format=False,  # Use verbose for easier parsing
                max_answer_chars=-1,
            )

            call_data = json.loads(call_result)

            # Check for errors
            if "error" in call_data:
                log.warning(f"Call graph analysis failed: {call_data.get('error')}")
                return []

            # Extract results from call graph data
            results = []
            call_list = call_data.get("incoming_calls", []) if is_incoming else call_data.get("outgoing_calls", [])

            for call_info in call_list[:max_results]:
                if compact_format:
                    result = {
                        "fp": call_info.get("file"),
                        "np": call_info.get("name_path"),
                        "k": call_info.get("kind", "Unknown"),
                        "ln": call_info.get("line"),
                        "t": "call_graph",
                        "sc": 1.0,
                        # Add call graph specific features
                        "is_direct_caller": 1,
                        "call_depth": 0,
                        "call_frequency": len(call_info.get("call_sites", [])),
                        "is_test_caller": "test" in call_info.get("file", "").lower(),
                    }
                else:
                    result = {
                        "relative_path": call_info.get("file"),
                        "name_path": call_info.get("name_path"),
                        "kind": call_info.get("kind", "Unknown"),
                        "line": call_info.get("line"),
                        "type": "call_graph",
                        "score": 1.0,
                        "call_sites": call_info.get("call_sites", []),
                        "is_direct_caller": True,
                        "call_depth": 0,
                    }
                results.append(result)

            return results

        except Exception as e:
            log.exception(f"Call graph search failed: {e}")
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
        language: str = "python",
        use_ast: bool = True,
    ) -> str:
        """
        Find code similar to the given snippet.

        This tool uses semantic embeddings and optional AST-based structural analysis
        to find code that is similar to the provided snippet, useful for:
        - Detecting code duplication (Type-1 through Type-4 clones)
        - Finding similar implementations
        - Identifying refactoring opportunities

        When use_ast=True (default), performs multi-level clone detection:
        - Semantic similarity via embeddings
        - Structural similarity via AST analysis (tree-sitter)
        - Combined scoring: 0.6 * structural + 0.4 * semantic
        - Clone type classification: Type-1 (Exact), Type-2 (Renamed),
          Type-3 (Modified), Type-4 (Semantic)

        When use_ast=False, falls back to embedding-only similarity.

        :param code_snippet: Code snippet to find similar code for
        :param max_results: Maximum number of results to return. Default 5.
        :param min_score: Minimum similarity score (0.0 to 1.0). Default 0.7 (high similarity).
        :param file_filter: Optional glob-style pattern to filter files. Default None.
        :param language_filter: Optional language filter (e.g., "python"). Default None.
        :param compact_format: If True, return compact JSON format. Default True.
        :param language: Programming language for AST parsing (python, javascript, typescript, go). Default "python".
        :param use_ast: If True, use AST-based clone detection. If False, use embedding-only. Default True.
        :return: A JSON string with similar code results including:
            - code_snippet: The original code snippet
            - results: List of similar code locations with:
                - sc (score): Similarity score (0.0 to 1.0)
                - fp (file_path): Relative path to file
                - np (name_path): Symbol name path
                - k (kind): Symbol kind
                - ln (line): Line number
                - doc: Code preview
                - ast_similarity: AST similarity score (if use_ast=True)
                - embedding_similarity: Embedding similarity score (if use_ast=True)
                - combined_score: Combined score (if use_ast=True)
                - clone_type: Clone type classification (if use_ast=True)
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

            if use_ast:
                # Use CloneDetector for AST-based clone detection
                from murena.semantic.clone_detector import CloneDetector

                detector = CloneDetector(self.agent)
                results = detector.find_clones(
                    code_snippet=code_snippet,
                    language=language,
                    threshold=min_score,
                    max_results=max_results,
                )

                # Add snippet to response
                snippet_preview = code_snippet[:100] + "..." if len(code_snippet) > 100 else code_snippet
                results["code_snippet"] = snippet_preview

                # Rename 'clones' to 'results' for consistent API
                if "clones" in results:
                    results["results"] = results.pop("clones")
                    results["total_results"] = results.pop("total", len(results["results"]))

            else:
                # Use SemanticSearcher for embedding-only similarity
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
