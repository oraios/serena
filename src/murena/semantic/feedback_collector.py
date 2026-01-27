"""
Implicit feedback collection for learning-to-rank.

Tracks user interactions with search results to generate training data:
- Clicks on results
- Dwell time (time spent viewing)
- File opens
- Symbol navigations
- Scroll depth

Stores feedback as JSONL for efficient streaming and training.
"""

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from murena.agent import MurenaAgent


@dataclass
class FeedbackEvent:
    """
    Single user interaction event.

    Used to generate relevance labels for training LTR model.
    """

    query: str  # Search query
    query_id: str  # Unique query identifier (hash)
    result_position: int  # Position in search results (0-indexed)
    file_path: str  # File path of result
    name_path: str  # Symbol name path
    event_type: str  # click, open, dwell, scroll
    relevance_score: float  # Computed relevance (0.0-1.0)
    timestamp: float  # Unix timestamp
    session_id: str  # User session identifier
    metadata: dict[str, Any]  # Additional context


class FeedbackCollector:
    """
    Collects implicit feedback from user interactions.

    Feedback signals:
    - Click: User clicked on result (relevance: 0.3)
    - Open: User opened file (relevance: 0.5)
    - Dwell: User spent >5s viewing (relevance: 0.7)
    - Scroll: User scrolled to result (relevance: 0.8)
    - Edit: User edited the file (relevance: 1.0)

    Stores feedback in .murena/feedback/{date}.jsonl for incremental loading.
    """

    FEEDBACK_DIR = "feedback"
    MIN_DWELL_TIME = 5.0  # Minimum seconds for positive dwell signal

    # Relevance scores for different event types
    RELEVANCE_SCORES = {
        "click": 0.3,
        "open": 0.5,
        "dwell": 0.7,
        "scroll": 0.8,
        "edit": 1.0,
    }

    def __init__(self, agent: "MurenaAgent"):
        """
        Initialize feedback collector.

        :param agent: MurenaAgent instance for project context
        """
        self.agent = agent
        self._session_id = self._generate_session_id()

    @property
    def feedback_dir(self) -> Path:
        """Get directory for storing feedback logs."""
        project_root = Path(self.agent.project.project_root)  # type: ignore[attr-defined]
        feedback_dir = project_root / ".murena" / self.FEEDBACK_DIR
        feedback_dir.mkdir(parents=True, exist_ok=True)
        return feedback_dir

    @staticmethod
    def _generate_session_id() -> str:
        """Generate unique session identifier."""
        return f"session_{int(time.time())}"

    @staticmethod
    def _generate_query_id(query: str, timestamp: float) -> str:
        """
        Generate unique query identifier.

        :param query: Search query string
        :param timestamp: Query timestamp
        :return: Query ID (hash of query + timestamp bucket)
        """
        import hashlib

        # Bucket queries by 5-minute intervals
        bucket = int(timestamp / 300) * 300
        query_key = f"{query}_{bucket}"
        return hashlib.md5(query_key.encode()).hexdigest()[:16]

    def record_click(
        self,
        query: str,
        result: dict[str, Any],
        position: int,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Record click event on search result.

        :param query: Original search query
        :param result: Clicked result dictionary
        :param position: Position in results (0-indexed)
        :param metadata: Optional additional context
        """
        self._record_event(
            query=query,
            result=result,
            position=position,
            event_type="click",
            relevance_score=self.RELEVANCE_SCORES["click"],
            metadata=metadata or {},
        )

    def record_open(
        self,
        query: str,
        result: dict[str, Any],
        position: int,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Record file open event.

        :param query: Original search query
        :param result: Opened result dictionary
        :param position: Position in results (0-indexed)
        :param metadata: Optional additional context
        """
        self._record_event(
            query=query,
            result=result,
            position=position,
            event_type="open",
            relevance_score=self.RELEVANCE_SCORES["open"],
            metadata=metadata or {},
        )

    def record_dwell(
        self,
        query: str,
        result: dict[str, Any],
        position: int,
        dwell_time: float,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Record dwell time event.

        :param query: Original search query
        :param result: Result user dwelled on
        :param position: Position in results (0-indexed)
        :param dwell_time: Time spent viewing (seconds)
        :param metadata: Optional additional context
        """
        # Only record if dwell time exceeds threshold
        if dwell_time < self.MIN_DWELL_TIME:
            return

        metadata = metadata or {}
        metadata["dwell_time"] = dwell_time

        # Scale relevance by dwell time (cap at 30s)
        base_score = self.RELEVANCE_SCORES["dwell"]
        time_factor = min(dwell_time / 30.0, 1.0)
        relevance = base_score + (1.0 - base_score) * time_factor

        self._record_event(
            query=query,
            result=result,
            position=position,
            event_type="dwell",
            relevance_score=relevance,
            metadata=metadata,
        )

    def record_edit(
        self,
        query: str,
        result: dict[str, Any],
        position: int,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Record edit event (highest relevance).

        :param query: Original search query
        :param result: Edited result dictionary
        :param position: Position in results (0-indexed)
        :param metadata: Optional additional context
        """
        self._record_event(
            query=query,
            result=result,
            position=position,
            event_type="edit",
            relevance_score=self.RELEVANCE_SCORES["edit"],
            metadata=metadata or {},
        )

    def _record_event(
        self,
        query: str,
        result: dict[str, Any],
        position: int,
        event_type: str,
        relevance_score: float,
        metadata: dict[str, Any],
    ) -> None:
        """
        Record feedback event to disk.

        :param query: Search query
        :param result: Result dictionary
        :param position: Position in results
        :param event_type: Type of event
        :param relevance_score: Computed relevance (0.0-1.0)
        :param metadata: Additional context
        """
        timestamp = time.time()

        event = FeedbackEvent(
            query=query,
            query_id=self._generate_query_id(query, timestamp),
            result_position=position,
            file_path=result.get("fp", result.get("file_path", "")),
            name_path=result.get("np", result.get("name_path", "")),
            event_type=event_type,
            relevance_score=relevance_score,
            timestamp=timestamp,
            session_id=self._session_id,
            metadata=metadata,
        )

        # Write to daily log file
        log_file = self._get_log_file()
        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(asdict(event)) + "\n")

            log.debug(f"Recorded {event_type} event: {query} -> {result.get('np', '')}")

        except Exception as e:
            log.error(f"Failed to write feedback event: {e}")

    def _get_log_file(self) -> Path:
        """Get current day's feedback log file."""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.feedback_dir / f"{today}.jsonl"

    def load_feedback(
        self,
        min_date: Optional[str] = None,
        max_date: Optional[str] = None,
    ) -> list[FeedbackEvent]:
        """
        Load feedback events from disk.

        :param min_date: Minimum date (YYYY-MM-DD, inclusive)
        :param max_date: Maximum date (YYYY-MM-DD, inclusive)
        :return: List of feedback events
        """
        events = []

        for log_file in sorted(self.feedback_dir.glob("*.jsonl")):
            # Filter by date range
            date_str = log_file.stem
            if min_date and date_str < min_date:
                continue
            if max_date and date_str > max_date:
                continue

            try:
                with open(log_file) as f:
                    for line in f:
                        event_dict = json.loads(line.strip())
                        event = FeedbackEvent(**event_dict)
                        events.append(event)

            except Exception as e:
                log.warning(f"Failed to load feedback from {log_file}: {e}")

        log.info(f"Loaded {len(events)} feedback events")
        return events

    def get_training_data(
        self,
        min_date: Optional[str] = None,
        max_date: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Convert feedback events to training data format for LTR.

        :param min_date: Minimum date (YYYY-MM-DD)
        :param max_date: Maximum date (YYYY-MM-DD)
        :return: List of training samples with features and labels
        """
        events = self.load_feedback(min_date, max_date)

        if not events:
            log.warning("No feedback events available for training")
            return []

        # Group events by query
        from collections import defaultdict

        query_groups: dict[str, list[FeedbackEvent]] = defaultdict(list)
        for event in events:
            query_groups[event.query_id].append(event)

        # Convert to training samples
        training_samples = []

        for query_id, query_events in query_groups.items():
            # Get representative query string
            query = query_events[0].query

            # Aggregate relevance scores by result
            result_relevance: dict[tuple[str, str], list[float]] = defaultdict(list)

            for event in query_events:
                key = (event.file_path, event.name_path)
                result_relevance[key].append(event.relevance_score)

            # Create training samples
            for (file_path, name_path), scores in result_relevance.items():
                # Average relevance across multiple interactions
                avg_relevance = sum(scores) / len(scores)

                # Reconstruct result dict for feature extraction
                result = {
                    "fp": file_path,
                    "np": name_path,
                    # Additional features would be looked up from index
                }

                training_samples.append(
                    {
                        "query": query,
                        "query_id": query_id,
                        "result": result,
                        "label": avg_relevance,
                        "num_interactions": len(scores),
                    }
                )

        log.info(f"Generated {len(training_samples)} training samples from {len(events)} events")
        return training_samples

    def get_feedback_stats(self) -> dict[str, Any]:
        """
        Get statistics about collected feedback.

        :return: Dictionary with feedback statistics
        """
        events = self.load_feedback()

        if not events:
            return {
                "total_events": 0,
                "unique_queries": 0,
                "event_types": {},
                "date_range": None,
            }

        # Compute statistics
        event_types: dict[str, int] = {}
        for event in events:
            event_types[event.event_type] = event_types.get(event.event_type, 0) + 1

        unique_queries = len(set(event.query_id for event in events))

        timestamps = [event.timestamp for event in events]

        min_time = datetime.fromtimestamp(min(timestamps), tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        max_time = datetime.fromtimestamp(max(timestamps), tz=UTC).strftime("%Y-%m-%d %H:%M:%S")

        return {
            "total_events": len(events),
            "unique_queries": unique_queries,
            "event_types": event_types,
            "date_range": f"{min_time} to {max_time}",
        }
