"""
Integration tests for call graph semantic search integration.

Tests:
- Query routing for call graph keywords
- LTR ranking with call graph features
- Natural language call graph queries
- IntelligentSearchTool with call graph mode
"""

from murena.semantic.router import QueryRouter, SearchMode


class TestCallGraphQueryRouting:
    """Test query routing for call graph keywords."""

    def test_who_calls_query_routes_to_call_graph(self):
        """Test 'who calls X' query routes to CALL_GRAPH mode."""
        router = QueryRouter()
        mode = router.route("who calls authenticate?")
        assert mode == SearchMode.CALL_GRAPH

    def test_what_calls_query_routes_to_call_graph(self):
        """Test 'what calls X' query routes to CALL_GRAPH mode."""
        router = QueryRouter()
        mode = router.route("what calls the login function?")
        assert mode == SearchMode.CALL_GRAPH

    def test_called_by_query_routes_to_call_graph(self):
        """Test 'called by X' query routes to CALL_GRAPH mode."""
        router = QueryRouter()
        mode = router.route("called by UserService")
        assert mode == SearchMode.CALL_GRAPH

    def test_callers_query_routes_to_call_graph(self):
        """Test 'callers of X' query routes to CALL_GRAPH mode."""
        router = QueryRouter()
        mode = router.route("callers of authenticate")
        assert mode == SearchMode.CALL_GRAPH

    def test_find_callers_query_routes_to_call_graph(self):
        """Test 'find callers X' query routes to CALL_GRAPH mode."""
        router = QueryRouter()
        mode = router.route("find callers of login")
        assert mode == SearchMode.CALL_GRAPH

    def test_call_graph_keyword_routes_to_call_graph(self):
        """Test 'call graph' keyword routes to CALL_GRAPH mode."""
        router = QueryRouter()
        mode = router.route("show call graph for authenticate")
        assert mode == SearchMode.CALL_GRAPH

    def test_incoming_calls_keyword_routes_to_call_graph(self):
        """Test 'incoming calls' keyword routes to CALL_GRAPH mode."""
        router = QueryRouter()
        mode = router.route("incoming calls to authenticate")
        assert mode == SearchMode.CALL_GRAPH

    def test_outgoing_calls_keyword_routes_to_call_graph(self):
        """Test 'outgoing calls' keyword routes to CALL_GRAPH mode."""
        router = QueryRouter()
        mode = router.route("outgoing calls from UserService")
        assert mode == SearchMode.CALL_GRAPH

    def test_uses_keyword_routes_to_call_graph(self):
        """Test 'uses' keyword routes to CALL_GRAPH mode."""
        router = QueryRouter()
        mode = router.route("what uses the authenticate function")
        assert mode == SearchMode.CALL_GRAPH

    def test_used_by_keyword_routes_to_call_graph(self):
        """Test 'used by' keyword routes to CALL_GRAPH mode."""
        router = QueryRouter()
        mode = router.route("used by which functions")
        assert mode == SearchMode.CALL_GRAPH

    def test_dependencies_keyword_routes_to_call_graph(self):
        """Test 'dependencies' keyword routes to CALL_GRAPH mode."""
        router = QueryRouter()
        mode = router.route("find dependencies for UserService")
        assert mode == SearchMode.CALL_GRAPH

    def test_depends_on_keyword_routes_to_call_graph(self):
        """Test 'depends on' keyword routes to CALL_GRAPH mode."""
        router = QueryRouter()
        mode = router.route("what depends on authenticate")
        assert mode == SearchMode.CALL_GRAPH

    def test_impact_keyword_routes_to_call_graph(self):
        """Test 'impact' keyword routes to CALL_GRAPH mode."""
        router = QueryRouter()
        mode = router.route("analyze impact of changing authenticate")
        assert mode == SearchMode.CALL_GRAPH

    def test_non_call_graph_query_routes_to_vector(self):
        """Test non-call graph queries don't route to CALL_GRAPH mode."""
        router = QueryRouter()
        mode = router.route("find authentication logic")
        assert mode != SearchMode.CALL_GRAPH

    def test_simple_identifier_routes_to_lsp(self):
        """Test simple identifier routes to LSP, not CALL_GRAPH."""
        router = QueryRouter()
        mode = router.route("authenticate")
        assert mode == SearchMode.LSP


class TestCallGraphFeatureExtraction:
    """Test LTR feature extraction with call graph features."""

    def test_extract_features_with_call_graph_data(self):
        """Test feature extraction includes call graph features."""
        from murena.agent import MurenaAgent
        from murena.semantic.learned_ranker import LearnedRanker

        # Create a mock agent
        agent = MurenaAgent()

        ranker = LearnedRanker(agent)

        # Result with call graph features
        result = {
            "fp": "services.py",
            "np": "UserService/authenticate",
            "k": "method",
            "ln": 42,
            "sc": 0.95,
            "is_direct_caller": 1,
            "call_depth": 0,
            "caller_importance": 5.0,
            "is_test_caller": False,
            "call_frequency": 3,
        }

        features = ranker.extract_features(result, "who calls authenticate", 0)

        # Should have 20 features (15 base + 5 call graph)
        assert len(features) == 20

        # Check call graph features (indices 15-19)
        assert features[15] == 1.0  # is_direct_caller
        assert features[16] == 0.0  # call_depth
        assert features[17] == 5.0  # caller_importance
        assert features[18] == 0.0  # is_test_caller
        assert features[19] == 3.0  # call_frequency

    def test_extract_features_without_call_graph_data(self):
        """Test feature extraction works without call graph features."""
        from murena.agent import MurenaAgent
        from murena.semantic.learned_ranker import LearnedRanker

        agent = MurenaAgent()
        ranker = LearnedRanker(agent)

        # Result without call graph features
        result = {
            "fp": "services.py",
            "np": "UserService/authenticate",
            "k": "method",
            "ln": 42,
            "sc": 0.95,
        }

        features = ranker.extract_features(result, "authenticate", 0)

        # Should still have 20 features (defaults to 0 for missing call graph features)
        assert len(features) == 20

        # Check call graph features default to 0
        assert features[15] == 0.0  # is_direct_caller (default)
        assert features[16] == 0.0  # call_depth (default)
        assert features[17] == 0.0  # caller_importance (default)
        assert features[18] == 0.0  # is_test_caller (default)
        assert features[19] == 0.0  # call_frequency (default)

    def test_is_test_caller_feature(self):
        """Test is_test_caller feature extraction."""
        from murena.agent import MurenaAgent
        from murena.semantic.learned_ranker import LearnedRanker

        agent = MurenaAgent()
        ranker = LearnedRanker(agent)

        # Result with test caller
        result = {
            "fp": "test/test_auth.py",
            "np": "test_authenticate",
            "k": "function",
            "ln": 10,
            "sc": 0.9,
            "is_test_caller": True,
        }

        features = ranker.extract_features(result, "who calls authenticate", 0)

        # is_test_caller feature (index 18) should be 1.0
        assert features[18] == 1.0


# Note: End-to-end integration tests with actual call graph tools would require
# a running MurenaAgent with LSP servers, which is beyond the scope of unit tests.
# These tests focus on the routing and feature extraction components.
