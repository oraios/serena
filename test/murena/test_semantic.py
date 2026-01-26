"""
Tests for semantic search functionality.

These tests verify indexing, searching, routing, and reranking capabilities.
"""

import pytest

# Check if semantic dependencies are available
try:
    from murena.semantic import SEMANTIC_AVAILABLE

    if not SEMANTIC_AVAILABLE:
        pytest.skip("Semantic search dependencies not installed", allow_module_level=True)
except ImportError:
    pytest.skip("Semantic search dependencies not installed", allow_module_level=True)


from murena.semantic.reranker import ResultReranker
from murena.semantic.router import QueryRouter, SearchMode


class TestQueryRouter:
    """Test query routing logic."""

    def test_route_single_identifier_to_lsp(self) -> None:
        """Single identifiers should route to LSP."""
        router = QueryRouter()

        assert router.route("UserService") == SearchMode.LSP
        assert router.route("authenticate") == SearchMode.LSP
        assert router.route("my_function") == SearchMode.LSP
        assert router.route("MAX_RETRIES") == SearchMode.LSP

    def test_route_symbol_path_to_lsp(self) -> None:
        """Symbol paths should route to LSP."""
        router = QueryRouter()

        assert router.route("UserService/authenticate") == SearchMode.LSP
        assert router.route("models/User") == SearchMode.LSP

    def test_route_natural_language_to_vector(self) -> None:
        """Natural language queries should route to vector."""
        router = QueryRouter()

        assert router.route("find all authentication logic") == SearchMode.VECTOR
        assert router.route("search for error handling") == SearchMode.VECTOR
        assert router.route("where is user validation") == SearchMode.VECTOR

    def test_route_mixed_query_to_hybrid(self) -> None:
        """Mixed queries should route to hybrid."""
        router = QueryRouter()

        assert router.route("login method with JWT validation") == SearchMode.HYBRID
        assert router.route("find class that handles authentication") == SearchMode.HYBRID
        assert router.route("search for method using database") == SearchMode.HYBRID

    def test_explicit_mode_override(self) -> None:
        """Explicit mode should override auto-routing."""
        router = QueryRouter()

        # Override natural language to LSP
        assert router.route("find authentication", mode="lsp") == SearchMode.LSP

        # Override identifier to vector
        assert router.route("UserService", mode="vector") == SearchMode.VECTOR

    def test_routing_explanation(self) -> None:
        """Routing explanation should provide reasoning."""
        router = QueryRouter()

        explanation = router.get_routing_explanation("UserService")
        assert explanation["query"] == "UserService"
        assert explanation["selected_mode"] == "lsp"
        assert "identifier" in explanation["reason"].lower() or "pattern" in explanation["reason"].lower()

    def test_route_short_queries(self) -> None:
        """Short queries without clear indicators should route to LSP."""
        router = QueryRouter()

        assert router.route("auth") == SearchMode.LSP
        assert router.route("user model") == SearchMode.LSP

    def test_route_vector_keywords(self) -> None:
        """Queries with multiple vector keywords should route to vector."""
        router = QueryRouter()

        assert router.route("find where authentication logic is implemented") == SearchMode.VECTOR
        assert router.route("search for all error handling code") == SearchMode.VECTOR


class TestResultReranker:
    """Test RRF result reranking."""

    def test_merge_empty_results(self) -> None:
        """Merging empty results should return empty list."""
        reranker = ResultReranker()
        merged = reranker.merge_results([], [], max_results=10)
        assert merged == []

    def test_merge_lsp_only(self) -> None:
        """Merging LSP-only results should preserve order."""
        reranker = ResultReranker()
        lsp_results = [
            {"fp": "file1.py", "np": "func1", "sc": 1.0},
            {"fp": "file2.py", "np": "func2", "sc": 1.0},
        ]

        merged = reranker.merge_results(lsp_results, [], max_results=10)
        assert len(merged) == 2
        assert merged[0]["fp"] == "file1.py"
        assert merged[0]["sources"] == ["lsp"]

    def test_merge_vector_only(self) -> None:
        """Merging vector-only results should preserve order."""
        reranker = ResultReranker()
        vector_results = [
            {"fp": "file1.py", "np": "func1", "sc": 0.9},
            {"fp": "file2.py", "np": "func2", "sc": 0.8},
        ]

        merged = reranker.merge_results([], vector_results, max_results=10)
        assert len(merged) == 2
        assert merged[0]["fp"] == "file1.py"
        assert merged[0]["sources"] == ["vector"]

    def test_merge_deduplicate_results(self) -> None:
        """Same result in both sources should be deduplicated."""
        reranker = ResultReranker()
        lsp_results = [{"fp": "file1.py", "np": "func1", "sc": 1.0}]
        vector_results = [{"fp": "file1.py", "np": "func1", "sc": 0.9}]

        merged = reranker.merge_results(lsp_results, vector_results, max_results=10)
        assert len(merged) == 1
        assert merged[0]["fp"] == "file1.py"
        assert set(merged[0]["sources"]) == {"lsp", "vector"}

    def test_merge_rrf_scoring(self) -> None:
        """RRF scoring should boost items appearing in both sources."""
        reranker = ResultReranker()

        # Item A appears in both (rank 1 in LSP, rank 2 in vector)
        # Item B appears only in vector (rank 1)
        # Item C appears only in LSP (rank 2)
        lsp_results = [
            {"fp": "file_a.py", "np": "func_a", "sc": 1.0},
            {"fp": "file_c.py", "np": "func_c", "sc": 1.0},
        ]
        vector_results = [
            {"fp": "file_b.py", "np": "func_b", "sc": 0.95},
            {"fp": "file_a.py", "np": "func_a", "sc": 0.90},
        ]

        merged = reranker.merge_results(lsp_results, vector_results, max_results=10)

        # Item A should rank highest (appears in both)
        assert merged[0]["fp"] == "file_a.py"
        assert merged[0]["rrf_score"] > merged[1]["rrf_score"]

    def test_merge_max_results_limit(self) -> None:
        """Merged results should respect max_results."""
        reranker = ResultReranker()

        lsp_results = [{"fp": f"file{i}.py", "np": f"func{i}", "sc": 1.0} for i in range(10)]
        vector_results = [{"fp": f"file{i}.py", "np": f"func{i}", "sc": 0.9} for i in range(10, 20)]

        merged = reranker.merge_results(lsp_results, vector_results, max_results=5)
        assert len(merged) == 5

    def test_weighted_merge(self) -> None:
        """Weighted merge should favor specified source."""
        reranker = ResultReranker()

        lsp_results = [{"fp": "lsp_top.py", "np": "func1", "sc": 1.0}]
        vector_results = [{"fp": "vector_top.py", "np": "func2", "sc": 0.95}]

        # Favor LSP
        merged_lsp = reranker.rerank_with_weights(lsp_results, vector_results, lsp_weight=0.9, vector_weight=0.1, max_results=10)
        assert merged_lsp[0]["fp"] == "lsp_top.py"

        # Favor vector
        merged_vector = reranker.rerank_with_weights(lsp_results, vector_results, lsp_weight=0.1, vector_weight=0.9, max_results=10)
        assert merged_vector[0]["fp"] == "vector_top.py"

    def test_explain_merge(self) -> None:
        """Explain merge should provide statistics."""
        reranker = ResultReranker()

        lsp_results = [
            {"fp": "file1.py", "np": "func1", "sc": 1.0},
            {"fp": "file2.py", "np": "func2", "sc": 1.0},
        ]
        vector_results = [
            {"fp": "file1.py", "np": "func1", "sc": 0.9},
            {"fp": "file3.py", "np": "func3", "sc": 0.8},
        ]

        explanation = reranker.explain_merge(lsp_results, vector_results)

        assert explanation["lsp_input"] == 2
        assert explanation["vector_input"] == 2
        assert explanation["merged_output"] == 3
        assert explanation["both_sources"] == 1  # file1.py appears in both


class TestSemanticIntegration:
    """Integration tests for semantic search (requires dependencies)."""

    @pytest.fixture
    def sample_results_compact(self) -> list[dict[str, str]]:
        """Sample search results in compact format."""
        return [
            {"fp": "src/auth/user.py", "np": "UserService/authenticate", "sc": 0.92, "k": "Method", "ln": 45},
            {"fp": "src/auth/token.py", "np": "TokenValidator/verify", "sc": 0.88, "k": "Method", "ln": 23},
            {"fp": "src/auth/middleware.py", "np": "auth_middleware", "sc": 0.85, "k": "Function", "ln": 12},
        ]

    @pytest.fixture
    def sample_results_standard(self) -> list[dict[str, str]]:
        """Sample search results in standard format."""
        return [
            {
                "relative_path": "src/auth/user.py",
                "name_path": "UserService/authenticate",
                "score": 0.92,
                "kind": "Method",
                "line": 45,
            },
            {
                "relative_path": "src/auth/token.py",
                "name_path": "TokenValidator/verify",
                "score": 0.88,
                "kind": "Method",
                "line": 23,
            },
        ]

    def test_result_key_generation_compact(self, sample_results_compact: list[dict[str, str]]) -> None:
        """Result key generation should work with compact format."""
        reranker = ResultReranker()
        key = reranker._get_result_key(sample_results_compact[0])
        assert key == "src/auth/user.py::UserService/authenticate"

    def test_result_key_generation_standard(self, sample_results_standard: list[dict[str, str]]) -> None:
        """Result key generation should work with standard format."""
        reranker = ResultReranker()
        key = reranker._get_result_key(sample_results_standard[0])
        assert key == "src/auth/user.py::UserService/authenticate"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
