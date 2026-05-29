from serena.analytics import ToolUsageStats


def test_entry_update_on_call_tracks_timing_and_errors():
    stats = ToolUsageStats()
    # Successful call
    stats._tool_stats["read_file"].update_on_call(input_tokens=10, output_tokens=20, duration_ms=15.0, success=True, now=1000.0)
    e = stats._tool_stats["read_file"]
    assert e.num_times_called == 1
    assert e.num_errors == 0
    assert e.input_tokens == 10
    assert e.output_tokens == 20
    assert e.total_duration_ms == 15.0
    assert e.min_duration_ms == 15.0
    assert e.max_duration_ms == 15.0
    assert e.last_called_at == 1000.0
    # Failed call with longer duration
    stats._tool_stats["read_file"].update_on_call(input_tokens=5, output_tokens=0, duration_ms=42.0, success=False, now=1001.0)
    e = stats._tool_stats["read_file"]
    assert e.num_times_called == 2
    assert e.num_errors == 1
    assert e.total_duration_ms == 57.0
    assert e.min_duration_ms == 15.0
    assert e.max_duration_ms == 42.0
    assert e.last_called_at == 1001.0


from serena.analytics import _INPUT_OUTPUT_PREVIEW_BYTES, ToolCallRecord, _truncate_preview


def test_truncate_preview_short_input_returns_as_is():
    text, truncated = _truncate_preview("hello")
    assert text == "hello"
    assert truncated is False


def test_truncate_preview_long_input_truncates_to_cap():
    long = "x" * (_INPUT_OUTPUT_PREVIEW_BYTES + 1000)
    text, truncated = _truncate_preview(long)
    assert len(text.encode("utf-8")) <= _INPUT_OUTPUT_PREVIEW_BYTES
    assert truncated is True


def test_tool_call_record_is_frozen():
    rec = ToolCallRecord(
        seq=1,
        tool="read_file",
        started_at=1000.0,
        duration_ms=12.0,
        success=True,
        error_message=None,
        input_preview="a",
        output_preview="b",
        input_truncated=False,
        output_truncated=False,
        input_tokens=3,
        output_tokens=4,
    )
    import dataclasses

    assert dataclasses.is_dataclass(rec)
    # Frozen — assignment raises
    import pytest as _pytest

    with _pytest.raises(dataclasses.FrozenInstanceError):
        rec.seq = 2  # type: ignore[misc]


def test_record_tool_call_safely_handles_analytics_exception(monkeypatch, caplog):
    """
    Instrumentation must never break the agent: if record_call raises,
    _record_tool_call_safely swallows and logs.
    """
    import logging

    from serena.agent import SerenaAgent

    # Build a minimal agent without going through SerenaAgent.__init__'s heavy setup.
    agent = SerenaAgent.__new__(SerenaAgent)
    agent._tool_usage_stats = ToolUsageStats()

    def explode(*_a, **_kw):
        raise RuntimeError("synthetic analytics failure")

    monkeypatch.setattr(agent._tool_usage_stats, "record_call", explode)

    with caplog.at_level(logging.WARNING):
        # Must not raise.
        agent._record_tool_call_safely(
            tool_name="x",
            input_str="i",
            output_str="o",
            duration_ms=1.0,
            success=True,
            error_message=None,
        )
    assert any("synthetic analytics failure" in r.message or "analytics" in r.message.lower() for r in caplog.records)


def test_record_tool_call_safely_records_success_path(monkeypatch):
    """
    A successful call recorded via _record_tool_call_safely shows up in the
    timeline buffer with success=True and the given duration.
    """
    from serena.agent import SerenaAgent

    agent = SerenaAgent.__new__(SerenaAgent)
    agent._tool_usage_stats = ToolUsageStats()

    agent._record_tool_call_safely(
        tool_name="fake_tool",
        input_str="{}",
        output_str="ok",
        duration_ms=12.5,
        success=True,
        error_message=None,
    )
    recs, _ = agent._tool_usage_stats.get_records_since(since_seq=None, tool=None, limit=10)
    assert len(recs) == 1
    assert recs[0].tool == "fake_tool"
    assert recs[0].duration_ms == 12.5
    assert recs[0].success is True


def test_apply_ex_records_exactly_once_on_exception(monkeypatch):
    """B1 regression: apply_ex with catch_exceptions=True records the failing
    call exactly once via the finally block, not twice.
    """
    from serena.agent import SerenaAgent
    from serena.tools.tools_base import Tool, ToolMarkerDoesNotRequireActiveProject

    # Build a minimal Tool subclass that doesn't need a project and always raises.
    class _RaisingTool(Tool, ToolMarkerDoesNotRequireActiveProject):
        """A minimal tool that always raises for testing."""

        def apply(self) -> str:
            """Apply the tool."""
            raise RuntimeError("deliberate failure")

    # Build a minimal agent stub.
    agent = SerenaAgent.__new__(SerenaAgent)
    agent._tool_usage_stats = ToolUsageStats()

    record_calls: list[dict] = []

    def _capture_record(**kwargs):  # type: ignore[override]
        record_calls.append(kwargs)

    agent._record_tool_call_safely = _capture_record  # type: ignore[method-assign]

    # Stub out is_active so the tool is always active.
    tool = _RaisingTool.__new__(_RaisingTool)
    tool.agent = agent
    monkeypatch.setattr(tool, "is_active", lambda: True)

    # Stub issue_task to run the callable inline (bypasses TaskExecutor).
    def _inline_issue_task(fn, name=""):
        result_holder = {}

        class _FakeFuture:
            def result(self, timeout=None):
                return result_holder["value"]

        result_holder["value"] = fn()
        return _FakeFuture()

    agent.issue_task = _inline_issue_task  # type: ignore[method-assign]

    tool.apply_ex(log_call=False, catch_exceptions=True)

    assert len(record_calls) == 1, f"Expected 1 recording, got {len(record_calls)}"
    assert record_calls[0]["success"] is False
    assert "deliberate failure" in (record_calls[0]["error_message"] or "")


def test_failed_tool_call_is_recorded_with_error_message():
    from serena.agent import SerenaAgent

    agent = SerenaAgent.__new__(SerenaAgent)
    agent._tool_usage_stats = ToolUsageStats()
    agent._record_tool_call_safely(
        tool_name="bad_tool",
        input_str="{}",
        output_str="",
        duration_ms=3.0,
        success=False,
        error_message="ValueError: bad arg",
    )
    recs, _ = agent._tool_usage_stats.get_records_since(since_seq=None, tool=None, limit=10)
    assert len(recs) == 1
    assert recs[0].success is False
    assert recs[0].error_message == "ValueError: bad arg"
    e = agent._tool_usage_stats.get_stats("bad_tool")
    assert e.num_errors == 1


import threading

from serena.analytics import _RECORD_BUFFER_SIZE


def test_record_call_populates_buffer_and_entry():
    stats = ToolUsageStats()
    stats.record_call(
        tool_name="read_file",
        input_str="a=1",
        output_str="ok",
        duration_ms=5.0,
        success=True,
        error_message=None,
        now=1000.0,
    )
    recs, max_seq = stats.get_records_since(since_seq=None, tool=None, limit=10)
    assert max_seq == 1
    assert len(recs) == 1
    r = recs[0]
    assert r.seq == 1
    assert r.tool == "read_file"
    assert r.success is True
    assert r.duration_ms == 5.0
    # Per-call token counts are persisted on the record (computed once, not just aggregated).
    assert r.input_tokens >= 1
    assert r.output_tokens >= 1
    e = stats.get_stats("read_file")
    assert e.num_times_called == 1
    assert e.total_duration_ms == 5.0


def test_get_records_since_cursor_filters():
    stats = ToolUsageStats()
    for i in range(5):
        stats.record_call(
            tool_name=f"t{i % 2}",
            input_str="",
            output_str="",
            duration_ms=1.0,
            success=True,
            error_message=None,
            now=1000.0 + i,
        )
    recs, max_seq = stats.get_records_since(since_seq=2, tool=None, limit=10)
    assert [r.seq for r in recs] == [3, 4, 5]
    assert max_seq == 5
    recs_t0, _ = stats.get_records_since(since_seq=None, tool="t0", limit=10)
    assert all(r.tool == "t0" for r in recs_t0)
    assert [r.seq for r in recs_t0] == [1, 3, 5]


def test_ring_buffer_drops_oldest_at_capacity():
    stats = ToolUsageStats()
    for i in range(_RECORD_BUFFER_SIZE + 50):
        stats.record_call(
            tool_name="t",
            input_str="",
            output_str="",
            duration_ms=1.0,
            success=True,
            error_message=None,
            now=float(i),
        )
    recs, max_seq = stats.get_records_since(since_seq=None, tool=None, limit=_RECORD_BUFFER_SIZE + 100)
    assert max_seq == _RECORD_BUFFER_SIZE + 50
    assert len(recs) == _RECORD_BUFFER_SIZE
    # Earliest retained is seq = max_seq - cap + 1
    assert recs[0].seq == max_seq - _RECORD_BUFFER_SIZE + 1


def test_clear_resets_records_and_seq_counter():
    stats = ToolUsageStats()
    stats.record_call(tool_name="t", input_str="", output_str="", duration_ms=1.0, success=True, error_message=None, now=1.0)
    assert len(stats.get_records_since(since_seq=None, tool=None, limit=10)[0]) == 1
    stats.clear()
    records, max_seq = stats.get_records_since(since_seq=None, tool=None, limit=10)
    assert records == []
    assert max_seq == 0
    # The next record_call resumes seq numbering from 1 (not 2).
    stats.record_call(tool_name="t", input_str="", output_str="", duration_ms=1.0, success=True, error_message=None, now=2.0)
    records, max_seq = stats.get_records_since(since_seq=None, tool=None, limit=10)
    assert records[0].seq == 1
    assert max_seq == 1


def test_seq_monotonic_under_concurrent_writers():
    stats = ToolUsageStats()
    N = 1000

    def writer():
        for _ in range(N):
            stats.record_call(
                tool_name="t",
                input_str="",
                output_str="",
                duration_ms=1.0,
                success=True,
                error_message=None,
                now=0.0,
            )

    threads = [threading.Thread(target=writer) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    recs, max_seq = stats.get_records_since(since_seq=None, tool=None, limit=10_000)
    assert max_seq == 2 * N
    assert len(recs) == 2 * N  # *** B7 correction: completeness check ***
    # No duplicate seqs in retained tail
    seqs = [r.seq for r in recs]
    assert len(seqs) == len(set(seqs))
    # Strictly increasing
    assert seqs == sorted(seqs)
