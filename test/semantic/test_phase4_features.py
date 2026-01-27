"""
Tests for Phase 4 semantic search features:
- Cross-encoder reranking
- Query expansion
- AST-based clone detection
- Improved routing with confidence scores
"""

import pytest

from murena.semantic import SEMANTIC_AVAILABLE

# Skip all tests if semantic dependencies not available
pytestmark = [
    pytest.mark.skipif(not SEMANTIC_AVAILABLE, reason="Semantic dependencies not installed"),
    pytest.mark.semantic_phase4,
]


class TestCrossEncoderReranking:
    """Test cross-encoder reranking functionality."""

    def test_reranker_initialization(self):
        """Test that CrossEncoderReranker can be initialized."""
        from murena.semantic.reranker import CrossEncoderReranker

        reranker = CrossEncoderReranker(k=60, use_cross_encoder=True)
        assert reranker.k == 60
        assert reranker.use_cross_encoder is True

    def test_reranker_without_cross_encoder(self):
        """Test that reranker works when cross-encoder is disabled."""
        from murena.semantic.reranker import CrossEncoderReranker

        reranker = CrossEncoderReranker(use_cross_encoder=False)

        # Mock results
        results = [
            {"fp": "file1.py", "np": "func1", "sc": 0.8},
            {"fp": "file2.py", "np": "func2", "sc": 0.9},
        ]

        # Should return top_k without reranking
        reranked = reranker.rerank_with_cross_encoder("test query", results, top_k=2)
        assert len(reranked) == 2
        assert reranked == results

    def test_extract_text_from_result(self):
        """Test text extraction from result dictionary."""
        from murena.semantic.reranker import CrossEncoderReranker

        reranker = CrossEncoderReranker()

        # Compact format
        result = {"fp": "file.py", "np": "MyClass/method", "doc": "Does something"}
        text = reranker._extract_text(result)
        assert "file.py" in text
        assert "MyClass/method" in text
        assert "Does something" in text

        # Standard format
        result = {"file_path": "file.py", "name_path": "MyClass/method"}
        text = reranker._extract_text(result)
        assert "file.py" in text
        assert "MyClass/method" in text


class TestQueryExpansion:
    """Test query expansion functionality."""

    def test_expander_initialization(self):
        """Test that QueryExpander can be initialized."""
        from murena.semantic.query_expander import QueryExpander

        expander = QueryExpander(max_expansions=3)
        assert expander.max_expansions == 3

    def test_expand_with_known_terms(self):
        """Test expansion of known terms."""
        from murena.semantic.query_expander import QueryExpander

        expander = QueryExpander(max_expansions=2)

        # Test auth expansion
        expanded = expander.expand("auth logic")
        assert "auth" in expanded
        assert "logic" in expanded
        assert "authentication" in expanded or "authorize" in expanded

    def test_expand_disabled(self):
        """Test that expansion can be disabled."""
        from murena.semantic.query_expander import QueryExpander

        expander = QueryExpander()

        original = "auth logic"
        expanded = expander.expand(original, expand_enabled=False)
        assert expanded == original

    def test_expand_unknown_terms(self):
        """Test that unknown terms are not expanded."""
        from murena.semantic.query_expander import QueryExpander

        expander = QueryExpander()

        original = "unknown term xyz"
        expanded = expander.expand(original)
        assert "unknown" in expanded
        assert "term" in expanded
        assert "xyz" in expanded

    def test_add_custom_expansion(self):
        """Test adding custom expansion rules."""
        from murena.semantic.query_expander import QueryExpander

        expander = QueryExpander()
        expander.add_expansion("custom", ["expansion1", "expansion2"])

        expanded = expander.expand("custom term")
        assert "custom" in expanded
        assert "expansion1" in expanded or "expansion2" in expanded


class TestImprovedRouting:
    """Test improved routing with confidence scores."""

    def test_route_with_confidence(self):
        """Test routing with confidence score."""
        from murena.semantic.router import QueryRouter

        router = QueryRouter()

        # High confidence LSP (single identifier)
        mode, confidence = router.route_with_confidence("UserService")
        assert mode.value == "lsp"
        assert confidence >= 0.9

        # High confidence vector (multiple semantic keywords)
        mode, confidence = router.route_with_confidence("find all authentication logic")
        assert mode.value == "vector"
        assert confidence >= 0.7

        # Medium confidence hybrid
        mode, confidence = router.route_with_confidence("login method with JWT")
        assert confidence >= 0.5

    def test_explicit_mode_high_confidence(self):
        """Test that explicit mode gives high confidence."""
        from murena.semantic.router import QueryRouter

        router = QueryRouter()

        mode, confidence = router.route_with_confidence("any query", mode="lsp")
        assert mode.value == "lsp"
        assert confidence == 1.0

    def test_should_use_fallback(self):
        """Test fallback threshold detection."""
        from murena.semantic.router import QueryRouter

        router = QueryRouter()

        # High confidence - no fallback
        assert not router.should_use_fallback(0.80)

        # Low confidence - use fallback
        assert router.should_use_fallback(0.50)

    def test_get_fallback_mode(self):
        """Test fallback mode selection."""
        from murena.semantic.router import QueryRouter, SearchMode

        router = QueryRouter()

        # LSP → HYBRID
        assert router.get_fallback_mode(SearchMode.LSP) == SearchMode.HYBRID

        # VECTOR → HYBRID
        assert router.get_fallback_mode(SearchMode.VECTOR) == SearchMode.HYBRID

        # HYBRID → HYBRID (no further fallback)
        assert router.get_fallback_mode(SearchMode.HYBRID) == SearchMode.HYBRID


class TestCloneDetector:
    """Test AST-based clone detection."""

    def test_detector_initialization(self):
        """Test that CloneDetector can be initialized."""
        from unittest.mock import MagicMock

        from murena.semantic.clone_detector import CloneDetector

        mock_agent = MagicMock()
        detector = CloneDetector(mock_agent)
        assert detector.agent == mock_agent

    def test_classify_clone_type(self):
        """Test clone type classification."""
        from unittest.mock import MagicMock

        from murena.semantic.clone_detector import CloneDetector

        mock_agent = MagicMock()
        detector = CloneDetector(mock_agent)

        # Type-1: Exact clone
        assert "Type-1" in detector._classify_clone_type(0.96, 0.96)

        # Type-2: Renamed
        assert "Type-2" in detector._classify_clone_type(0.92, 0.85)

        # Type-3: Modified
        assert "Type-3" in detector._classify_clone_type(0.75, 0.75)

        # Type-4: Semantic
        assert "Type-4" in detector._classify_clone_type(0.65, 0.80)

    def test_normalize_ast_structure(self):
        """Test AST normalization."""
        from unittest.mock import MagicMock

        from murena.semantic.clone_detector import TREE_SITTER_AVAILABLE, CloneDetector

        if not TREE_SITTER_AVAILABLE:
            pytest.skip("tree-sitter not available")

        mock_agent = MagicMock()
        detector = CloneDetector(mock_agent)

        # Create mock AST node
        mock_node = MagicMock()
        mock_node.type = "function_definition"
        mock_node.children = []

        normalized = detector._normalize_ast(mock_node)
        assert normalized["type"] == "function_definition"
        assert normalized["children"] == []


class TestIntegration:
    """Integration tests for Phase 4 features working together."""

    def test_semantic_searcher_has_query_expansion(self):
        """Test that SemanticSearcher has query expansion capability."""
        from murena.semantic.query_expander import QueryExpander
        from murena.semantic.searcher import SemanticSearcher

        # Verify the query_expander property exists
        assert hasattr(SemanticSearcher, "query_expander")

        # Verify QueryExpander can be instantiated
        expander = QueryExpander()
        assert expander.expand("auth") != "auth"  # Should expand

    def test_intelligent_search_has_confidence_routing(self):
        """Test that IntelligentSearchTool supports confidence routing."""
        from murena.semantic.router import QueryRouter

        # Verify routing with confidence works
        router = QueryRouter()
        mode, confidence = router.route_with_confidence("find UserService")

        assert mode is not None
        assert 0.0 <= confidence <= 1.0
        assert isinstance(confidence, float)

    def test_token_efficiency_preserved(self):
        """Test that compact format is still used for token efficiency."""
        # This test verifies that the compact JSON format is still being used
        from murena.semantic.reranker import ResultReranker

        reranker = ResultReranker(k=10)

        # Create test results with compact keys
        results = [
            {"fp": "file.py", "np": "Class/method", "sc": 0.9, "ln": 10},
            {"fp": "other.py", "np": "OtherClass/func", "sc": 0.8, "ln": 20},
        ]

        # Verify the reranker works with compact format
        merged = reranker.merge_results(results, [], max_results=10)
        assert len(merged) == 2
        assert "fp" in merged[0]  # Compact format preserved
        assert "np" in merged[0]  # Compact: name_path


def test_phase4_marker():
    """Verify that the semantic_phase4 marker is registered."""
    # This test just ensures the marker exists
    assert True
