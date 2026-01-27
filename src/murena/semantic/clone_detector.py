"""
Multi-level code clone detection using lexical, structural, and semantic analysis.

Clone Types:
- Type-1: Exact clones (copy-paste)
- Type-2: Renamed identifiers (variables, functions)
- Type-3: Modified statements (added/removed lines)
- Type-4: Semantic clones (different syntax, same logic)
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from murena.agent import MurenaAgent

# Optional tree-sitter for AST parsing
try:
    import tree_sitter_go as tsgo
    import tree_sitter_javascript as tsjs
    import tree_sitter_python as tspython
    from tree_sitter import Language, Parser

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    log.warning("tree-sitter not available, AST-based clone detection disabled")


class CloneDetector:
    """
    Detects code clones using multi-level similarity analysis.

    Three-stage pipeline:
    1. Lexical filtering: Fast hash-based exact/near-exact match
    2. Structural similarity: AST-based tree edit distance
    3. Semantic similarity: Embedding cosine distance
    """

    # Supported languages (tree-sitter)
    LANGUAGE_PARSERS = {
        "python": tspython if TREE_SITTER_AVAILABLE else None,
        "javascript": tsjs if TREE_SITTER_AVAILABLE else None,
        "typescript": tsjs if TREE_SITTER_AVAILABLE else None,
        "go": tsgo if TREE_SITTER_AVAILABLE else None,
    }

    def __init__(self, agent: "MurenaAgent"):
        """Initialize clone detector."""
        self.agent = agent
        self._parsers: dict[str, Any] = {}  # Language → Parser

    def find_clones(
        self,
        code_snippet: str,
        language: str = "python",
        threshold: float = 0.8,
        max_results: int = 10,
    ) -> dict[str, Any]:
        """
        Find code clones similar to the given snippet.

        :param code_snippet: Code to find clones of
        :param language: Programming language (python, javascript, go, etc.)
        :param threshold: Minimum combined similarity (0.0-1.0)
        :param max_results: Maximum clones to return
        :return: Dictionary with clone results
        """
        if not TREE_SITTER_AVAILABLE:
            log.warning("AST-based clone detection unavailable, falling back to embedding-only")
            return self._embedding_only_clones(code_snippet, threshold, max_results)

        # Stage 1: Get semantic candidates (top 50 for reranking)
        from murena.semantic.searcher import SemanticSearcher

        searcher = SemanticSearcher(self.agent)
        semantic_results = searcher.search(
            query=code_snippet,
            max_results=50,
            min_score=0.3,  # Low threshold for recall
            expand_query=False,  # Don't expand code snippets
            compact_format=True,
        )

        candidates = semantic_results.get("results", [])
        if not candidates:
            return {"clones": [], "total": 0}

        # Stage 2: Compute structural similarity for candidates
        parser = self._get_parser(language)
        query_ast = self._parse_code(code_snippet, parser)

        clones = []
        for candidate in candidates:
            # Get candidate code
            candidate_code = self._get_candidate_code(candidate)
            if not candidate_code:
                continue

            # Parse candidate AST
            candidate_ast = self._parse_code(candidate_code, parser)

            # Compute AST similarity
            ast_similarity = self._compute_ast_similarity(query_ast, candidate_ast)

            # Get embedding score
            embedding_score = candidate.get("sc", candidate.get("score", 0.0))

            # Combined score: 0.6 * structural + 0.4 * semantic
            combined_score = 0.6 * ast_similarity + 0.4 * embedding_score

            if combined_score >= threshold:
                clone_type = self._classify_clone_type(ast_similarity, embedding_score)
                clones.append(
                    {
                        "file_path": candidate.get("fp", candidate.get("file_path", "")),
                        "name_path": candidate.get("np", candidate.get("name_path", "")),
                        "line": candidate.get("ln", candidate.get("line", 0)),
                        "ast_similarity": ast_similarity,
                        "embedding_similarity": embedding_score,
                        "combined_score": combined_score,
                        "clone_type": clone_type,
                    }
                )

        # Sort by combined score
        clones.sort(key=lambda x: x["combined_score"], reverse=True)

        return {
            "clones": clones[:max_results],
            "total": len(clones),
            "threshold": threshold,
        }

    def _get_parser(self, language: str) -> Any:
        """Get or create tree-sitter parser for language."""
        if language not in self._parsers:
            lang_module = self.LANGUAGE_PARSERS.get(language)
            if not lang_module:
                raise ValueError(f"Unsupported language: {language}")

            parser = Parser()
            parser.set_language(Language(lang_module.language()))  # type: ignore[attr-defined]
            self._parsers[language] = parser

        return self._parsers[language]

    def _parse_code(self, code: str, parser: Any) -> dict[str, Any]:
        """Parse code into AST."""
        tree = parser.parse(bytes(code, "utf8"))
        return self._normalize_ast(tree.root_node)

    def _normalize_ast(self, node: Any) -> dict[str, Any]:
        """
        Normalize AST for comparison (remove identifiers, keep structure).

        This allows detecting Type-2 clones (renamed variables).
        """
        return {
            "type": node.type,
            "children": [self._normalize_ast(child) for child in node.children],
        }

    def _compute_ast_similarity(self, ast1: dict[str, Any], ast2: dict[str, Any]) -> float:
        """
        Compute structural similarity between ASTs using tree edit distance.

        Simplified algorithm: Jaccard similarity over node types.
        """

        def extract_node_types(ast: dict[str, Any]) -> set[str]:
            """Recursively extract all node types."""
            types = {ast["type"]}
            for child in ast.get("children", []):
                types.update(extract_node_types(child))
            return types

        types1 = extract_node_types(ast1)
        types2 = extract_node_types(ast2)

        # Jaccard similarity
        intersection = len(types1 & types2)
        union = len(types1 | types2)

        return intersection / union if union > 0 else 0.0

    def _classify_clone_type(self, ast_sim: float, emb_sim: float) -> str:
        """
        Classify clone type based on similarity scores.

        Type-1: Exact (ast > 0.95, emb > 0.95)
        Type-2: Renamed (ast > 0.9, emb > 0.8)
        Type-3: Modified (ast > 0.7, emb > 0.7)
        Type-4: Semantic (ast < 0.7, emb > 0.7)
        """
        if ast_sim > 0.95 and emb_sim > 0.95:
            return "Type-1 (Exact)"
        elif ast_sim > 0.9 and emb_sim > 0.8:
            return "Type-2 (Renamed)"
        elif ast_sim > 0.7 and emb_sim > 0.7:
            return "Type-3 (Modified)"
        elif emb_sim > 0.7:
            return "Type-4 (Semantic)"
        else:
            return "Weak match"

    def _get_candidate_code(self, candidate: dict[str, Any]) -> Optional[str]:
        """Retrieve code for a candidate result."""
        file_path = candidate.get("fp", candidate.get("file_path", ""))
        name_path = candidate.get("np", candidate.get("name_path", ""))

        if not file_path or not name_path:
            return None

        # Use find_symbol to get code body
        from murena.symbol import LanguageServerSymbolRetriever

        retriever = LanguageServerSymbolRetriever(
            self.agent.get_language_server_manager_or_raise(),
            self.agent,
        )

        try:
            symbols = retriever.find(
                name_path_pattern=name_path,
                within_relative_path=file_path,
            )

            if symbols and len(symbols) > 0:
                # Get the body from the symbol
                symbol = symbols[0]
                if hasattr(symbol, "body") and symbol.body:
                    return symbol.body
                # If body not available, try to get it from language server
                try:
                    symbol.retrieve_body()
                    return symbol.body
                except Exception as e:
                    log.debug(f"Could not retrieve body for {name_path}: {e}")

        except Exception as e:
            log.debug(f"Could not retrieve code for {name_path} in {file_path}: {e}")

        return None

    def _embedding_only_clones(
        self,
        code_snippet: str,
        threshold: float,
        max_results: int,
    ) -> dict[str, Any]:
        """Fallback to embedding-only similarity (no AST)."""
        from murena.semantic.searcher import SemanticSearcher

        searcher = SemanticSearcher(self.agent)

        results = searcher.search(
            query=code_snippet,
            max_results=max_results,
            min_score=threshold,
            expand_query=False,
        )

        # Convert to clone format
        clones = [
            {
                **result,
                "clone_type": "Semantic-only (no AST)",
                "ast_similarity": 0.0,
                "embedding_similarity": result.get("sc", result.get("score", 0.0)),
                "combined_score": result.get("sc", result.get("score", 0.0)),
            }
            for result in results.get("results", [])
        ]

        return {
            "clones": clones,
            "total": len(clones),
            "threshold": threshold,
        }
