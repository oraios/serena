"""
Training pipeline for Learning-to-Rank model.

Loads implicit feedback, extracts features, trains LightGBM model.
Supports CLI invocation and scheduled training.
"""

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Optional

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from murena.agent import MurenaAgent


class LTRTrainer:
    """
    Manages training pipeline for Learning-to-Rank model.

    Workflow:
    1. Load feedback events from .murena/feedback/*.jsonl
    2. Extract ranking features for each result
    3. Prepare training data in LightGBM format
    4. Train LambdaRank model
    5. Save model to .murena/models/
    """

    def __init__(self, agent: "MurenaAgent"):
        """
        Initialize LTR trainer.

        :param agent: MurenaAgent instance
        """
        self.agent = agent

    def train(
        self,
        min_date: Optional[str] = None,
        max_date: Optional[str] = None,
        validation_split: float = 0.2,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Train LTR model on collected feedback.

        :param min_date: Minimum feedback date (YYYY-MM-DD)
        :param max_date: Maximum feedback date (YYYY-MM-DD)
        :param validation_split: Fraction of data for validation
        :param params: Optional LightGBM training parameters
        :return: Training metrics and results
        """
        from murena.semantic.feedback_collector import FeedbackCollector
        from murena.semantic.learned_ranker import LearnedRanker

        log.info("Starting LTR training pipeline")

        # Step 1: Load feedback
        collector = FeedbackCollector(self.agent)
        training_samples = collector.get_training_data(min_date, max_date)

        if not training_samples:
            return {
                "success": False,
                "error": "No feedback data available for training",
                "num_samples": 0,
            }

        # Check minimum samples
        ranker = LearnedRanker(self.agent)
        if len(training_samples) < ranker.MIN_TRAINING_SAMPLES:
            return {
                "success": False,
                "error": f"Insufficient training data: {len(training_samples)} < {ranker.MIN_TRAINING_SAMPLES}",
                "num_samples": len(training_samples),
            }

        log.info(f"Loaded {len(training_samples)} training samples")

        # Step 2: Extract features
        log.info("Extracting features from training samples")
        training_data = []

        for sample in training_samples:
            try:
                query = sample["query"]
                query_id = sample["query_id"]
                result = sample["result"]
                label = sample["label"]
                position = sample.get("position", 0)

                # Extract features
                features = ranker.extract_features(result, query, position)

                training_data.append(
                    {
                        "features": features,
                        "label": label,
                        "query_id": query_id,
                    }
                )

            except Exception as e:
                log.warning(f"Failed to extract features for sample: {e}")
                continue

        if not training_data:
            return {
                "success": False,
                "error": "Feature extraction failed for all samples",
                "num_samples": len(training_samples),
            }

        log.info(f"Extracted features for {len(training_data)} samples")

        # Step 3: Train model
        try:
            metrics = ranker.train(
                training_data=training_data,
                validation_split=validation_split,
                params=params,
            )

            log.info(f"LTR training complete: {metrics}")

            return {
                "success": True,
                "metrics": metrics,
                "num_samples": len(training_samples),
                "num_features": len(ranker.FEATURE_NAMES),
                "model_path": str(ranker.model_dir / ranker.MODEL_FILENAME),
            }

        except Exception as e:
            log.error(f"LTR training failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "num_samples": len(training_samples),
            }

    def train_incremental(
        self,
        days_back: int = 7,
        validation_split: float = 0.2,
    ) -> dict[str, Any]:
        """
        Train model on recent feedback (incremental update).

        :param days_back: Number of days to include in training
        :param validation_split: Fraction of data for validation
        :return: Training results
        """
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        min_date = start_date.strftime("%Y-%m-%d")
        max_date = end_date.strftime("%Y-%m-%d")

        log.info(f"Incremental training on feedback from {min_date} to {max_date}")

        return self.train(
            min_date=min_date,
            max_date=max_date,
            validation_split=validation_split,
        )

    def schedule_training(self, interval_hours: int = 24) -> None:
        """
        Schedule periodic model retraining.

        :param interval_hours: Training interval in hours (default: 24 = daily)
        """
        log.info(f"Scheduling LTR training every {interval_hours} hours")

        # Note: This is a placeholder for actual scheduling
        # In production, use cron, systemd timer, or task scheduler
        # For now, just log the intention

        log.warning("Automatic scheduling not yet implemented")
        log.info("To train manually, run: murena train-ltr")

    def get_training_stats(self) -> dict[str, Any]:
        """
        Get statistics about training data availability.

        :return: Training readiness metrics
        """
        from murena.semantic.feedback_collector import FeedbackCollector
        from murena.semantic.learned_ranker import LearnedRanker

        collector = FeedbackCollector(self.agent)
        ranker = LearnedRanker(self.agent)

        # Get feedback stats
        feedback_stats = collector.get_feedback_stats()
        num_events = feedback_stats.get("total_events", 0)
        unique_queries = feedback_stats.get("unique_queries", 0)

        # Check if model exists
        model_exists = (ranker.model_dir / ranker.MODEL_FILENAME).exists()
        model_loaded = ranker.load_model()

        # Estimate training readiness
        min_samples = ranker.MIN_TRAINING_SAMPLES
        is_ready = num_events >= min_samples

        return {
            "feedback_events": num_events,
            "unique_queries": unique_queries,
            "min_required_samples": min_samples,
            "training_ready": is_ready,
            "model_exists": model_exists,
            "model_loaded": model_loaded,
            "feedback_stats": feedback_stats,
        }


def train_ltr_cli(
    project_path: str,
    min_date: Optional[str] = None,
    max_date: Optional[str] = None,
    validation_split: float = 0.2,
) -> None:
    """
    CLI entry point for LTR training.

    :param project_path: Path to Murena project
    :param min_date: Minimum feedback date (YYYY-MM-DD)
    :param max_date: Maximum feedback date (YYYY-MM-DD)
    :param validation_split: Validation split fraction
    """
    from murena.agent import MurenaAgent

    # Load project
    log.info(f"Loading project: {project_path}")
    agent = MurenaAgent(project=project_path)

    # Train model
    trainer = LTRTrainer(agent)
    result = trainer.train(
        min_date=min_date,
        max_date=max_date,
        validation_split=validation_split,
    )

    # Print results
    if result["success"]:
        print("\n✓ LTR training successful!")
        print(f"  Samples: {result['num_samples']}")
        print(f"  Features: {result['num_features']}")
        print(f"  Model: {result['model_path']}")
        print(f"  Metrics: {result['metrics']}")
    else:
        print("\n✗ LTR training failed!")
        print(f"  Error: {result['error']}")
        print(f"  Samples: {result.get('num_samples', 0)}")

    # Shutdown agent
    agent.shutdown()
