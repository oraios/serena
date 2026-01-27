"""
Integration tests for Phase 4 advanced semantic search features.

Tests:
- Cross-encoder reranking
- Query expansion
- AST-based clone detection
- Confidence-based routing with fallback
"""

import pytest

# Check if semantic dependencies are available
try:
    from murena.semantic import SEMANTIC_AVAILABLE

    if not SEMANTIC_AVAILABLE:
        pytest.skip("Semantic search dependencies not installed", allow_module_level=True)
except ImportError:
    pytest.skip("Semantic search dependencies not installed", allow_module_level=True)

from murena.semantic.clone_detector import TREE_SITTER_AVAILABLE
from murena.semantic.query_expander import QueryExpander
from murena.semantic.reranker import CrossEncoderReranker
from murena.semantic.router import QueryRouter, SearchMode


class TestQueryExpansion:
    """Test query expansion with domain-specific synonyms."""

    def test_auth_expansion(self) -> None:
        """Auth term should expand to authentication, authorize, login, credentials."""
        expander = QueryExpander(max_expansions=3)
        expanded = expander.expand("auth")

        assert "auth" in expanded
        assert "authentication" in expanded
        assert "authorize" in expanded
        assert "login" in expanded

    def test_database_expansion(self) -> None:
        """DB term should expand to database, datastore, repository."""
        expander = QueryExpander(max_expansions=3)
        expanded = expander.expand("db connection")

        assert "db" in expanded
        assert "database" in expanded
        assert "datastore" in expanded
        assert "connection" in expanded

    def test_no_expansion_when_disabled(self) -> None:
        """Query should remain unchanged when expansion disabled."""
        expander = QueryExpander(max_expansions=3)
        expanded = expander.expand("auth logic", expand_enabled=False)

        assert expanded == "auth logic"

    def test_multiple_term_expansion(self) -> None:
        """Multiple terms should be expanded independently."""
        expander = QueryExpander(max_expansions=3)
        expanded = expander.expand("auth db")

        assert "auth" in expanded
        assert "authentication" in expanded
        assert "db" in expanded
        assert "database" in expanded

    def test_deduplication(self) -> None:
        """Expanded terms should be deduplicated."""
        expander = QueryExpander(max_expansions=3)
        expanded = expander.expand("auth login")  # Both expand to "authentication"

        # Count occurrences of "authentication"
        count = expanded.split().count("authentication")
        assert count == 1, "authentication should appear only once after deduplication"

    def test_max_expansions_limit(self) -> None:
        """Expansion should respect max_expansions limit."""
        expander = QueryExpander(max_expansions=2)
        expanded = expander.expand("auth")

        tokens = expanded.split()
        # Original "auth" + max 2 expansions = max 3 tokens for this term
        assert len(tokens) <= 4, f"Expected max 4 tokens, got {len(tokens)}: {tokens}"

    def test_custom_expansion(self) -> None:
        """Custom expansions should work."""
        expander = QueryExpander(max_expansions=3)
        expander.add_expansion("custom", ["custom1", "custom2", "custom3"])

        expanded = expander.expand("custom")

        assert "custom" in expanded
        assert "custom1" in expanded
        assert "custom2" in expanded


class TestCrossEncoderReranking:
    """Test cross-encoder reranking functionality."""

    @pytest.fixture
    def sample_results(self) -> list[dict[str, float]]:
        """Sample search results for reranking."""
        return [
            {"fp": "auth/user.py", "np": "UserService/authenticate", "sc": 0.75, "doc": "Authenticate user credentials"},
            {"fp": "auth/token.py", "np": "TokenValidator/verify", "sc": 0.80, "doc": "Verify JWT token"},
            {"fp": "models/user.py", "np": "User", "sc": 0.70, "doc": "User model class"},
            {"fp": "auth/session.py", "np": "SessionManager/create", "sc": 0.65, "doc": "Create user session"},
        ]

    def test_cross_encoder_loading(self) -> None:
        """Cross-encoder model should load successfully."""
        reranker = CrossEncoderReranker(use_cross_encoder=True)

        # Access the model to trigger lazy loading
        model = reranker.cross_encoder

        if model is not None:
            # Model loaded successfully
            assert reranker.use_cross_encoder is True
        else:
            # Model loading failed, should be disabled
            assert reranker.use_cross_encoder is False

    def test_rerank_with_cross_encoder(self, sample_results: list[dict[str, float]]) -> None:
        """Cross-encoder should rerank results."""
        reranker = CrossEncoderReranker(use_cross_encoder=True)

        query = "authenticate user login"
        reranked = reranker.rerank_with_cross_encoder(query, sample_results, top_k=3)

        # Should return top 3 results
        assert len(reranked) == 3

        # Results should have ce_score and combined_score
        if reranker.use_cross_encoder:
            for result in reranked:
                assert "ce_score" in result
                assert "combined_score" in result

    def test_rerank_empty_results(self) -> None:
        """Reranking empty results should return empty list."""
        reranker = CrossEncoderReranker(use_cross_encoder=True)

        query = "test query"
        reranked = reranker.rerank_with_cross_encoder(query, [], top_k=10)

        assert reranked == []

    def test_rerank_fallback_without_cross_encoder(self, sample_results: list[dict[str, float]]) -> None:
        """Reranking should work without cross-encoder (disabled)."""
        reranker = CrossEncoderReranker(use_cross_encoder=False)

        query = "authenticate"
        reranked = reranker.rerank_with_cross_encoder(query, sample_results, top_k=3)

        # Should return top 3 results without cross-encoder scoring
        assert len(reranked) == 3
        assert "ce_score" not in reranked[0]

    def test_combined_scoring(self, sample_results: list[dict[str, float]]) -> None:
        """Combined score should be calculated correctly."""
        reranker = CrossEncoderReranker(use_cross_encoder=True)

        query = "authenticate"
        reranked = reranker.rerank_with_cross_encoder(query, sample_results, top_k=4)

        if reranker.use_cross_encoder and len(reranked) > 0:
            result = reranked[0]
            if "ce_score" in result and "combined_score" in result:
                # Combined score should be weighted average
                base_score = result.get("sc", 0.0)
                ce_score = result["ce_score"]
                expected_combined = 0.7 * ce_score + 0.3 * base_score

                # Allow small floating point tolerance
                assert abs(result["combined_score"] - expected_combined) < 0.01


@pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not available")
class TestASTCloneDetection:
    """Test AST-based clone detection."""

    def test_clone_detector_initialization(self) -> None:
        """CloneDetector should initialize with agent."""
        from murena.agent import MurenaAgent
        from murena.semantic.clone_detector import CloneDetector

        # Create minimal agent (without full initialization)
        agent = MurenaAgent(project=".")
        detector = CloneDetector(agent)

        assert detector.agent == agent
        assert detector._parsers == {}

    def test_supported_languages(self) -> None:
        """CloneDetector should support Python, JavaScript, Go."""
        from murena.semantic.clone_detector import CloneDetector

        supported = CloneDetector.LANGUAGE_PARSERS.keys()

        assert "python" in supported
        assert "javascript" in supported
        assert "typescript" in supported
        assert "go" in supported

    def test_normalize_ast(self) -> None:
        """AST normalization should remove identifiers and keep structure."""
        from murena.agent import MurenaAgent
        from murena.semantic.clone_detector import CloneDetector

        agent = MurenaAgent(project=".")
        detector = CloneDetector(agent)

        # Create mock AST node
        class MockNode:
            def __init__(self, node_type: str, children: list) -> None:
                self.type = node_type
                self.children = children

        root = MockNode("function_definition", [MockNode("identifier", []), MockNode("block", [])])

        normalized = detector._normalize_ast(root)

        assert normalized["type"] == "function_definition"
        assert len(normalized["children"]) == 2
        assert normalized["children"][0]["type"] == "identifier"

    def test_jaccard_similarity(self) -> None:
        """Jaccard similarity should compute correctly."""
        from murena.agent import MurenaAgent
        from murena.semantic.clone_detector import CloneDetector

        agent = MurenaAgent(project=".")
        detector = CloneDetector(agent)

        ast1 = {"type": "root", "children": [{"type": "function", "children": []}, {"type": "class", "children": []}]}

        ast2 = {"type": "root", "children": [{"type": "function", "children": []}, {"type": "method", "children": []}]}

        similarity = detector._compute_ast_similarity(ast1, ast2)

        # Types in ast1: {root, function, class} = 3
        # Types in ast2: {root, function, method} = 3
        # Intersection: {root, function} = 2
        # Union: {root, function, class, method} = 4
        # Jaccard: 2/4 = 0.5
        assert similarity == 0.5

    def test_clone_type_classification(self) -> None:
        """Clone types should be classified correctly."""
        from murena.agent import MurenaAgent
        from murena.semantic.clone_detector import CloneDetector

        agent = MurenaAgent(project=".")
        detector = CloneDetector(agent)

        # Type-1: Exact
        assert detector._classify_clone_type(0.96, 0.96) == "Type-1 (Exact)"

        # Type-2: Renamed
        assert detector._classify_clone_type(0.92, 0.85) == "Type-2 (Renamed)"

        # Type-3: Modified
        assert detector._classify_clone_type(0.75, 0.75) == "Type-3 (Modified)"

        # Type-4: Semantic
        assert detector._classify_clone_type(0.60, 0.80) == "Type-4 (Semantic)"

        # Weak match
        assert detector._classify_clone_type(0.50, 0.60) == "Weak match"


class TestConfidenceBasedRouting:
    """Test confidence-based routing with automatic fallback."""

    def test_high_confidence_single_identifier(self) -> None:
        """Single identifier should have very high confidence (0.95)."""
        router = QueryRouter()

        mode, confidence = router.route_with_confidence("UserService")

        assert mode == SearchMode.LSP
        assert confidence == 0.95

    def test_high_confidence_symbol_path(self) -> None:
        """Symbol path should have high confidence (0.90)."""
        router = QueryRouter()

        mode, confidence = router.route_with_confidence("UserService/authenticate")

        assert mode == SearchMode.LSP
        assert confidence == 0.90

    def test_medium_confidence_natural_language(self) -> None:
        """Natural language with vector keywords should have medium confidence."""
        router = QueryRouter()

        mode, confidence = router.route_with_confidence("find all authentication logic")

        assert mode == SearchMode.VECTOR
        assert confidence >= 0.70

    def test_low_confidence_triggers_fallback(self) -> None:
        """Low confidence (<0.60) should trigger fallback."""
        router = QueryRouter()

        mode, confidence = router.route_with_confidence("user stuff")

        assert confidence < 0.60
        assert router.should_use_fallback(confidence) is True

    def test_fallback_mode_lsp_to_hybrid(self) -> None:
        """LSP mode should fallback to HYBRID."""
        router = QueryRouter()

        fallback = router.get_fallback_mode(SearchMode.LSP)

        assert fallback == SearchMode.HYBRID

    def test_fallback_mode_vector_to_hybrid(self) -> None:
        """VECTOR mode should fallback to HYBRID."""
        router = QueryRouter()

        fallback = router.get_fallback_mode(SearchMode.VECTOR)

        assert fallback == SearchMode.HYBRID

    def test_no_fallback_for_hybrid(self) -> None:
        """HYBRID mode should not have fallback (already uses both)."""
        router = QueryRouter()

        fallback = router.get_fallback_mode(SearchMode.HYBRID)

        assert fallback == SearchMode.HYBRID

    def test_explicit_mode_high_confidence(self) -> None:
        """Explicit mode override should have 1.0 confidence."""
        router = QueryRouter()

        mode, confidence = router.route_with_confidence("natural language query", mode="lsp")

        assert mode == SearchMode.LSP
        assert confidence == 1.0

    def test_mixed_query_hybrid_confidence(self) -> None:
        """Mixed query should route to VECTOR with medium-high confidence."""
        router = QueryRouter()

        mode, confidence = router.route_with_confidence("find UserService method")

        # "find" is a strong vector keyword, routes to VECTOR mode
        assert mode == SearchMode.VECTOR
        assert 0.70 <= confidence <= 0.90


class TestPhase4Integration:
    """End-to-end integration tests for Phase 4 features."""

    def test_query_expansion_in_semantic_search(self) -> None:
        """Query expansion should work in semantic search pipeline."""
        from murena.semantic.query_expander import QueryExpander

        expander = QueryExpander(max_expansions=3)

        # Test that expansion works
        original = "auth error"
        expanded = expander.expand(original)

        assert len(expanded) > len(original)
        assert "authentication" in expanded or "authorize" in expanded
        assert "exception" in expanded or "failure" in expanded

    def test_routing_with_confidence_explanation(self) -> None:
        """Routing explanation should include confidence reasoning."""
        router = QueryRouter()

        explanation = router.get_routing_explanation("UserService")

        assert explanation["query"] == "UserService"
        assert explanation["selected_mode"] == "lsp"
        assert "identifier" in explanation["reason"].lower() or "pattern" in explanation["reason"].lower()

    def test_cross_encoder_combines_with_rrf(self) -> None:
        """Cross-encoder should work with RRF scores."""
        reranker = CrossEncoderReranker(use_cross_encoder=True)

        # Results with RRF scores
        results = [
            {"fp": "file1.py", "np": "func1", "rrf_score": 0.015, "doc": "authentication function"},
            {"fp": "file2.py", "np": "func2", "rrf_score": 0.012, "doc": "user login handler"},
        ]

        query = "authenticate user"
        reranked = reranker.rerank_with_cross_encoder(query, results, top_k=2)

        # Should have combined scores
        if reranker.use_cross_encoder:
            for result in reranked:
                assert "combined_score" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
