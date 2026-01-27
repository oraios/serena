"""
Learning-to-Rank for semantic search results.

Uses LightGBM with LambdaRank objective for result reranking based on implicit feedback.
Provides cold-start fallback to cross-encoder when insufficient training data.
"""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from murena.agent import MurenaAgent

# Optional LightGBM for learning-to-rank
try:
    import lightgbm as lgb
    import numpy as np
    from sklearn.preprocessing import StandardScaler

    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False
    log.warning("LightGBM not available, learned ranker disabled")


class LearnedRanker:
    """
    Learning-to-Rank model for semantic search results.

    Uses LightGBM with LambdaRank objective to learn from implicit user feedback.
    Falls back to cross-encoder reranking when insufficient training data.

    Features (15 total):
    - vector_similarity: Embedding cosine similarity
    - bm25_score: BM25 text matching score
    - ce_score: Cross-encoder relevance score
    - file_recency: Days since file last modified
    - symbol_popularity: Times symbol accessed in project
    - access_count: User access frequency
    - path_depth: Directory nesting level
    - file_size: Lines of code
    - last_modified: Unix timestamp
    - query_match_type: Exact/partial/fuzzy
    - is_test_file: Boolean indicator
    - num_references: Symbol reference count
    - symbol_kind: Class/Function/Method/etc.
    - file_extension: .py/.js/.go/etc.
    - result_position: Original rank position
    """

    MODEL_FILENAME = "ltr_model.txt"
    SCALER_FILENAME = "ltr_scaler.json"
    MIN_TRAINING_SAMPLES = 100  # Minimum feedback samples for training
    COLD_START_THRESHOLD = MIN_TRAINING_SAMPLES  # Use cross-encoder until this many samples

    # Feature names (must match extraction order)
    FEATURE_NAMES = [
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

    def __init__(self, agent: "MurenaAgent"):
        """
        Initialize learned ranker.

        :param agent: MurenaAgent instance for accessing project data
        """
        self.agent = agent
        self._model: Optional[Any] = None  # LightGBM model
        self._scaler: Optional[Any] = None  # StandardScaler for feature normalization
        self._model_path: Optional[Path] = None
        self._is_trained = False

        if not LIGHTGBM_AVAILABLE:
            log.warning("LightGBM not installed, learned ranker unavailable")

    @property
    def model_dir(self) -> Path:
        """Get directory for storing trained models."""
        project_root = Path(self.agent.project.project_root)  # type: ignore[attr-defined]
        model_dir = project_root / ".murena" / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        return model_dir

    @property
    def is_available(self) -> bool:
        """Check if learned ranker is available (LightGBM installed)."""
        return LIGHTGBM_AVAILABLE

    @property
    def is_trained(self) -> bool:
        """Check if model is trained and ready for inference."""
        return self._is_trained and self._model is not None

    def load_model(self) -> bool:
        """
        Load trained model from disk.

        :return: True if model loaded successfully, False otherwise
        """
        if not LIGHTGBM_AVAILABLE:
            return False

        model_path = self.model_dir / self.MODEL_FILENAME
        scaler_path = self.model_dir / self.SCALER_FILENAME

        if not model_path.exists():
            log.debug(f"No trained model found at {model_path}")
            return False

        try:
            # Load LightGBM model
            self._model = lgb.Booster(model_file=str(model_path))
            self._model_path = model_path

            # Load scaler if exists
            if scaler_path.exists():
                with open(scaler_path) as f:
                    scaler_data = json.load(f)
                    self._scaler = StandardScaler()
                    self._scaler.mean_ = np.array(scaler_data["mean"])
                    self._scaler.scale_ = np.array(scaler_data["scale"])

            self._is_trained = True
            log.info(f"Loaded trained LTR model from {model_path}")
            return True

        except Exception as e:
            log.warning(f"Failed to load LTR model: {e}")
            return False

    def save_model(self) -> bool:
        """
        Save trained model to disk.

        :return: True if saved successfully, False otherwise
        """
        if not self.is_trained or self._model is None:
            log.warning("No trained model to save")
            return False

        try:
            model_path = self.model_dir / self.MODEL_FILENAME
            scaler_path = self.model_dir / self.SCALER_FILENAME

            # Save LightGBM model
            self._model.save_model(str(model_path))

            # Save scaler
            if self._scaler is not None:
                scaler_data = {
                    "mean": self._scaler.mean_.tolist(),
                    "scale": self._scaler.scale_.tolist(),
                }
                with open(scaler_path, "w") as f:
                    json.dump(scaler_data, f)

            log.info(f"Saved LTR model to {model_path}")
            return True

        except Exception as e:
            log.error(f"Failed to save LTR model: {e}")
            return False

    def extract_features(self, result: dict[str, Any], query: str, position: int) -> list[float]:
        """
        Extract ranking features from a search result.

        :param result: Search result dictionary
        :param query: Original query string
        :param position: Result position in original ranking
        :return: Feature vector (20 features)
        """
        features = []

        # 1. vector_similarity: Embedding cosine similarity
        features.append(result.get("sc", result.get("score", 0.0)))

        # 2. bm25_score: BM25 text matching (if available)
        features.append(result.get("bm25", 0.0))

        # 3. ce_score: Cross-encoder score (if available)
        features.append(result.get("ce_score", 0.0))

        # 4. file_recency: Days since last modified
        last_modified = result.get("lm", result.get("last_modified", 0))
        if last_modified > 0:
            import time

            days_old = (time.time() - last_modified) / 86400
            features.append(days_old)
        else:
            features.append(999)  # Very old/unknown

        # 5. symbol_popularity: Access frequency in project
        features.append(result.get("pop", result.get("popularity", 0)))

        # 6. access_count: User-specific access count
        features.append(result.get("ac", result.get("access_count", 0)))

        # 7. path_depth: Directory nesting level
        file_path = result.get("fp", result.get("file_path", ""))
        features.append(file_path.count("/"))

        # 8. file_size: Lines of code (if available)
        features.append(result.get("fs", result.get("file_size", 0)))

        # 9. last_modified: Unix timestamp
        features.append(last_modified)

        # 10. query_match_type: Exact (1.0), partial (0.5), fuzzy (0.0)
        name_path = result.get("np", result.get("name_path", ""))
        if query.lower() in name_path.lower():
            match_type = 1.0 if query.lower() == name_path.lower() else 0.5
        else:
            match_type = 0.0
        features.append(match_type)

        # 11. is_test_file: Boolean indicator
        is_test = any(marker in file_path.lower() for marker in ["test", "spec", "__test__", "_test."])
        features.append(1.0 if is_test else 0.0)

        # 12. num_references: Symbol reference count
        features.append(result.get("refs", result.get("num_references", 0)))

        # 13. symbol_kind: Encoded as numeric
        kind = result.get("k", result.get("kind", ""))
        kind_encoding = {
            "class": 5.0,
            "function": 4.0,
            "method": 4.0,
            "variable": 2.0,
            "constant": 2.0,
            "module": 3.0,
        }
        features.append(kind_encoding.get(kind.lower(), 1.0))

        # 14. file_extension: Encoded as numeric
        ext = Path(file_path).suffix.lower()
        ext_encoding = {
            ".py": 5.0,
            ".js": 4.0,
            ".ts": 4.0,
            ".go": 4.0,
            ".java": 3.0,
            ".rs": 3.0,
        }
        features.append(ext_encoding.get(ext, 1.0))

        # 15. result_position: Original rank position
        features.append(float(position))

        # Call graph features (16-20) - added in Phase 3
        # These features are populated when call graph analysis is available

        # 16. is_direct_caller: Whether this is a direct caller (1.0) or not (0.0)
        is_direct_caller = result.get("is_direct_caller", 0)
        features.append(1.0 if is_direct_caller else 0.0)

        # 17. call_depth: Depth in call graph (0 = direct, 1+ = indirect)
        call_depth = result.get("call_depth", 0)
        features.append(float(min(call_depth, 5)))  # Cap at 5

        # 18. caller_importance: Importance based on num_references of caller
        caller_importance = result.get("caller_importance", 0.0)
        features.append(float(caller_importance))

        # 19. is_test_caller: Whether caller is from test code
        is_test_caller = result.get("is_test_caller", False)
        features.append(1.0 if is_test_caller else 0.0)

        # 20. call_frequency: Number of call sites (how many times this is called)
        call_frequency = result.get("call_frequency", 0)
        features.append(float(call_frequency))

        return features

    def rerank(
        self,
        query: str,
        results: list[dict[str, Any]],
        top_k: int = 10,
        use_cold_start_fallback: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Rerank search results using learned model.

        :param query: Search query
        :param results: List of search results
        :param top_k: Number of top results to return
        :param use_cold_start_fallback: Use cross-encoder if model not trained
        :return: Reranked results
        """
        if not self.is_available:
            log.debug("LightGBM not available, returning original results")
            return results[:top_k]

        # Load model if not already loaded
        if not self.is_trained:
            self.load_model()

        # Cold-start fallback: use cross-encoder if insufficient training
        if not self.is_trained and use_cold_start_fallback:
            log.debug("LTR model not trained, falling back to cross-encoder")
            from murena.semantic.reranker import CrossEncoderReranker

            reranker = CrossEncoderReranker(use_cross_encoder=True)
            return reranker.rerank_with_cross_encoder(query, results, top_k)

        if not self.is_trained:
            log.debug("LTR model not trained and fallback disabled, returning original")
            return results[:top_k]

        try:
            # Extract features for all results
            feature_matrix = []
            for i, result in enumerate(results):
                features = self.extract_features(result, query, i)
                feature_matrix.append(features)

            feature_matrix_np = np.array(feature_matrix)

            # Normalize features
            if self._scaler is not None:
                feature_matrix_np = self._scaler.transform(feature_matrix_np)

            # Predict scores
            assert self._model is not None  # For mypy
            scores = self._model.predict(feature_matrix_np)

            # Add LTR scores to results
            for result, score in zip(results, scores, strict=False):
                result["ltr_score"] = float(score)

            # Sort by LTR score
            reranked = sorted(results, key=lambda x: x["ltr_score"], reverse=True)

            log.debug(f"Reranked {len(results)} results with LTR model")
            return reranked[:top_k]

        except Exception as e:
            log.error(f"Error during LTR reranking: {e}")
            return results[:top_k]

    def train(
        self,
        training_data: list[dict[str, Any]],
        validation_split: float = 0.2,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Train LightGBM model on feedback data.

        :param training_data: List of training samples with features and labels
        :param validation_split: Fraction of data for validation
        :param params: Optional LightGBM parameters
        :return: Training metrics
        """
        if not LIGHTGBM_AVAILABLE:
            raise RuntimeError("LightGBM not installed")

        if len(training_data) < self.MIN_TRAINING_SAMPLES:
            raise ValueError(f"Insufficient training data: {len(training_data)} < {self.MIN_TRAINING_SAMPLES}")

        try:
            # Extract features and labels
            X = np.array([sample["features"] for sample in training_data])
            y = np.array([sample["label"] for sample in training_data])
            groups = np.array([sample["query_id"] for sample in training_data])

            # Normalize features
            self._scaler = StandardScaler()
            X = self._scaler.fit_transform(X)

            # Split train/validation
            n_train = int(len(X) * (1 - validation_split))
            X_train, X_val = X[:n_train], X[n_train:]
            y_train, y_val = y[:n_train], y[n_train:]

            # Count queries in each split
            unique_train_queries = len(np.unique(groups[:n_train]))
            unique_val_queries = len(np.unique(groups[n_train:]))

            # LightGBM datasets
            train_data = lgb.Dataset(
                X_train,
                label=y_train,
                group=[unique_train_queries],
                feature_name=self.FEATURE_NAMES,
            )
            val_data = lgb.Dataset(
                X_val,
                label=y_val,
                group=[unique_val_queries],
                reference=train_data,
            )

            # Training parameters
            default_params = {
                "objective": "lambdarank",
                "metric": "ndcg",
                "ndcg_eval_at": [1, 3, 5, 10],
                "num_leaves": 31,
                "learning_rate": 0.05,
                "feature_fraction": 0.9,
                "bagging_fraction": 0.8,
                "bagging_freq": 5,
                "verbose": -1,
            }

            if params:
                default_params.update(params)

            # Train model
            log.info(f"Training LTR model on {len(training_data)} samples")
            self._model = lgb.train(
                default_params,
                train_data,
                num_boost_round=100,
                valid_sets=[train_data, val_data],
                valid_names=["train", "valid"],
            )

            self._is_trained = True

            # Save model
            self.save_model()

            # Return metrics
            metrics = {
                "num_samples": len(training_data),
                "num_features": len(self.FEATURE_NAMES),
                "num_train": n_train,
                "num_val": len(X_val),
                "train_queries": unique_train_queries,
                "val_queries": unique_val_queries,
            }

            log.info(f"LTR training complete: {metrics}")
            return metrics

        except Exception as e:
            log.error(f"Error training LTR model: {e}")
            raise
