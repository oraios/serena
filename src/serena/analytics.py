from __future__ import annotations

import threading
from collections import defaultdict


class ToolStatsEntry:
    def __init__(self) -> None:
        self.count = 0
        self.input_chars = 0
        self.output_chars = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "count": self.count,
            "input_chars": self.input_chars,
            "output_chars": self.output_chars,
        }

_lock = threading.Lock()
_tool_stats: dict[str, ToolStatsEntry] = defaultdict(ToolStatsEntry)


def record_tool_usage(tool_name: str, input_chars: int, output_chars: int) -> None:
    with _lock:
        entry = _tool_stats[tool_name]
        entry.count += 1
        entry.input_chars += input_chars
        entry.output_chars += output_chars


def get_tool_stats() -> dict[str, dict[str, int]]:
    with _lock:
        return {name: entry.to_dict() for name, entry in _tool_stats.items()}


def clear_tool_stats() -> None:
    with _lock:
        _tool_stats.clear()
