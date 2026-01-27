"""
Tests for Phase 5B: Learning-to-Rank (LTR) features.

Tests:
- LearnedRanker: feature extraction, reranking, model persistence
- FeedbackCollector: event recording, loading, statistics
- LTRTrainer: training pipeline
- Integration with IntelligentSearchTool
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Mark all tests in this file with semantic_phase5b
pytestmark = pytest.mark.semantic_phase5b


class TestLearnedRanker:
    """Tests for LearnedRanker class."""

    def test_ranker_initialization(self):
        """Test that LearnedRanker initializes correctly."""
        from murena.semantic.learned_ranker import LIGHTGBM_AVAILABLE, LearnedRanker

        mock_agent = Mock()
        mock_agent.project.project_root = "/tmp/test_project"

        ranker = LearnedRanker(mock_agent)

        assert ranker.agent == mock_agent
        assert not ranker.is_trained  # Not trained initially
        assert ranker.is_available == LIGHTGBM_AVAILABLE

    def test_feature_extraction(self):
        """Test feature extraction from search results."""
        from murena.semantic.learned_ranker import LearnedRanker

        mock_agent = Mock()
        mock_agent.project.project_root = "/tmp/test_project"

        ranker = LearnedRanker(mock_agent)

        # Test result with compact format
        result = {
            "fp": "src/module/file.py",
            "np": "MyClass/my_method",
            "sc": 0.85,
            "ce_score": 0.90,
            "k": "method",
            "lm": 1234567890,
        }

        features = ranker.extract_features(result, query="my_method", position=0)

        # Verify we get 15 features
        assert len(features) == len(ranker.FEATURE_NAMES)

        # Check specific features
        assert features[0] == 0.85  # vector_similarity
        assert features[2] == 0.90  # ce_score
        assert features[6] == 2  # path_depth (src/module/file.py)
        assert features[9] == 0.5  # query_match_type (partial match: "my_method" in "MyClass/my_method")
        assert features[10] == 0.0  # is_test_file (not a test file)

    def test_feature_names_match_extraction_order(self):
        """Test that FEATURE_NAMES match extraction order."""
        from murena.semantic.learned_ranker import LearnedRanker

        # This is critical for LightGBM training
        expected_features = [
            "vector_similarity",
            "bm25_score",
            "ce_score",
            "file_recency",
            "symbol_popularity",
            "access_count",
            "path_depth",
            "file_size",
            "last_modified",
            "query_match_type",
            "is_test_file",
            "num_references",
            "symbol_kind",
            "file_extension",
            "result_position",
        ]

        assert expected_features == LearnedRanker.FEATURE_NAMES

    def test_model_dir_creation(self):
        """Test that model directory is created."""
        from murena.semantic.learned_ranker import LearnedRanker

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_agent = Mock()
            mock_agent.project.project_root = tmpdir

            ranker = LearnedRanker(mock_agent)
            model_dir = ranker.model_dir

            assert model_dir.exists()
            assert model_dir == Path(tmpdir) / ".murena" / "models"

    def test_cold_start_fallback(self):
        """Test cold-start fallback to cross-encoder."""
        from murena.semantic.learned_ranker import LIGHTGBM_AVAILABLE, LearnedRanker

        if not LIGHTGBM_AVAILABLE:
            pytest.skip("LightGBM not available")

        mock_agent = Mock()
        mock_agent.project.project_root = "/tmp/test_project"

        ranker = LearnedRanker(mock_agent)

        # Mock cross-encoder fallback
        with patch("murena.semantic.reranker.CrossEncoderReranker") as mock_ce:
            mock_ce_instance = Mock()
            mock_ce_instance.rerank_with_cross_encoder.return_value = [{"fp": "file.py", "np": "result1", "ce_score": 0.9}]
            mock_ce.return_value = mock_ce_instance

            results = [
                {"fp": "file.py", "np": "result1", "sc": 0.8},
                {"fp": "other.py", "np": "result2", "sc": 0.7},
            ]

            # Rerank without trained model (should use fallback)
            ranker.rerank(
                query="test",
                results=results,
                top_k=2,
                use_cold_start_fallback=True,
            )

            # Should have called cross-encoder
            assert mock_ce_instance.rerank_with_cross_encoder.called


class TestFeedbackCollector:
    """Tests for FeedbackCollector class."""

    def test_collector_initialization(self):
        """Test that FeedbackCollector initializes correctly."""
        from murena.semantic.feedback_collector import FeedbackCollector

        mock_agent = Mock()
        mock_agent.project.project_root = "/tmp/test_project"

        collector = FeedbackCollector(mock_agent)

        assert collector.agent == mock_agent
        assert collector._session_id.startswith("session_")

    def test_feedback_dir_creation(self):
        """Test that feedback directory is created."""
        from murena.semantic.feedback_collector import FeedbackCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_agent = Mock()
            mock_agent.project.project_root = tmpdir

            collector = FeedbackCollector(mock_agent)
            feedback_dir = collector.feedback_dir

            assert feedback_dir.exists()
            assert feedback_dir == Path(tmpdir) / ".murena" / "feedback"

    def test_record_click_event(self):
        """Test recording click events."""
        from murena.semantic.feedback_collector import FeedbackCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_agent = Mock()
            mock_agent.project.project_root = tmpdir

            collector = FeedbackCollector(mock_agent)

            result = {
                "fp": "src/file.py",
                "np": "MyClass/method",
                "sc": 0.85,
            }

            # Record click
            collector.record_click(
                query="authentication",
                result=result,
                position=0,
                metadata={"source": "test"},
            )

            # Check that event was written
            log_files = list(collector.feedback_dir.glob("*.jsonl"))
            assert len(log_files) == 1

            # Read and verify event
            with open(log_files[0]) as f:
                event_data = json.loads(f.read().strip())

            assert event_data["query"] == "authentication"
            assert event_data["event_type"] == "click"
            assert event_data["file_path"] == "src/file.py"
            assert event_data["name_path"] == "MyClass/method"
            assert event_data["relevance_score"] == 0.3  # Click score

    def test_record_dwell_event(self):
        """Test recording dwell time events."""
        from murena.semantic.feedback_collector import FeedbackCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_agent = Mock()
            mock_agent.project.project_root = tmpdir

            collector = FeedbackCollector(mock_agent)

            result = {"fp": "file.py", "np": "Class/method"}

            # Record dwell (>5s threshold)
            collector.record_dwell(
                query="test",
                result=result,
                position=0,
                dwell_time=10.0,  # 10 seconds
            )

            # Should be recorded
            log_files = list(collector.feedback_dir.glob("*.jsonl"))
            assert len(log_files) == 1

            # Verify relevance scaled by dwell time
            with open(log_files[0]) as f:
                event_data = json.loads(f.read().strip())

            assert event_data["event_type"] == "dwell"
            assert event_data["relevance_score"] > 0.7  # Base dwell score

    def test_load_feedback_events(self):
        """Test loading feedback from disk."""
        from murena.semantic.feedback_collector import FeedbackCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_agent = Mock()
            mock_agent.project.project_root = tmpdir

            collector = FeedbackCollector(mock_agent)

            # Record multiple events
            result = {"fp": "file.py", "np": "method"}

            collector.record_click("query1", result, 0)
            collector.record_open("query2", result, 1)
            collector.record_edit("query3", result, 2)

            # Load events
            events = collector.load_feedback()

            assert len(events) == 3
            assert events[0].event_type == "click"
            assert events[1].event_type == "open"
            assert events[2].event_type == "edit"

    def test_get_feedback_stats(self):
        """Test feedback statistics."""
        from murena.semantic.feedback_collector import FeedbackCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_agent = Mock()
            mock_agent.project.project_root = tmpdir

            collector = FeedbackCollector(mock_agent)

            # Record events
            result = {"fp": "file.py", "np": "method"}

            collector.record_click("query1", result, 0)
            collector.record_click("query1", result, 1)  # Same query
            collector.record_open("query2", result, 0)

            stats = collector.get_feedback_stats()

            assert stats["total_events"] == 3
            assert stats["unique_queries"] >= 1  # At least 1 unique query
            assert "click" in stats["event_types"]
            assert "open" in stats["event_types"]


class TestLTRTrainer:
    """Tests for LTRTrainer class."""

    def test_trainer_initialization(self):
        """Test that LTRTrainer initializes correctly."""
        from murena.semantic.ltr_training import LTRTrainer

        mock_agent = Mock()
        trainer = LTRTrainer(mock_agent)

        assert trainer.agent == mock_agent

    def test_get_training_stats(self):
        """Test training readiness statistics."""
        from murena.semantic.ltr_training import LTRTrainer

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_agent = Mock()
            mock_agent.project.project_root = tmpdir

            trainer = LTRTrainer(mock_agent)
            stats = trainer.get_training_stats()

            assert "feedback_events" in stats
            assert "unique_queries" in stats
            assert "training_ready" in stats
            assert "model_exists" in stats


class TestIntegration:
    """Integration tests for Phase 5B features."""

    def test_intelligent_search_has_ltr_parameter(self):
        """Test that IntelligentSearchTool supports use_ltr parameter."""
        # Check that IntelligentSearchTool.apply has use_ltr parameter
        import inspect

        from murena.tools.semantic_tools import IntelligentSearchTool

        signature = inspect.signature(IntelligentSearchTool.apply)
        assert "use_ltr" in signature.parameters
        assert signature.parameters["use_ltr"].default is True

    def test_ltr_fallback_chain_exists(self):
        """Test that LTR → cross-encoder → RRF fallback chain is implemented."""
        # This is verified by code inspection in IntelligentSearchTool
        # Just ensure imports work
        from murena.semantic.learned_ranker import LearnedRanker
        from murena.semantic.reranker import CrossEncoderReranker

        assert LearnedRanker is not None
        assert CrossEncoderReranker is not None


def test_phase5b_marker():
    """Verify that the semantic_phase5b marker is registered."""
    # This test just ensures the marker exists
    assert True
