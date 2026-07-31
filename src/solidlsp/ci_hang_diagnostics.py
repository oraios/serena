from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DIAGNOSTICS_DIR_ENV = "SERENA_CI_HANG_DIAGNOSTICS_DIR"
JDTLS_CANARY_PHASE_ENV = "SERENA_CI_JDTLS_CANARY_PHASE"
JDTLS_CANARY_STALL_SECONDS_ENV = "SERENA_CI_JDTLS_CANARY_STALL_SECONDS"

JDTLS_LAST_PHASE_FILENAME = "jdtls-last-phase.json"
JDTLS_PHASE_TAIL_FILENAME = "jdtls-phase-tail.json"
JDTLS_LSP_TAIL_FILENAME = "jdtls-lsp-tail.json"

_PHASE_TAIL_SIZE = 200
_LSP_TAIL_SIZE = 400
_STATE_LOCK = threading.RLock()
_CANARY_STALL_STARTED = threading.Event()
_CANARY_DIAGNOSTICS_CAPTURED = threading.Event()

LSPTraceLogger = Callable[[str, str, dict[str, Any] | str], None]


@dataclass
class _RuntimeDiagnosticsState:
    sequence: int = 0
    phases: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=_PHASE_TAIL_SIZE))
    lsp_messages: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=_LSP_TAIL_SIZE))


_STATE_BY_ROOT: dict[Path, _RuntimeDiagnosticsState] = {}


def _diagnostics_root() -> Path | None:
    value = os.environ.get(DIAGNOSTICS_DIR_ENV)
    if value is None or not value.strip():
        return None
    return Path(value)


def _is_java_language_server(ls_id: object) -> bool:
    value = getattr(ls_id, "value", ls_id)
    return str(value).casefold() == "java"


def _new_entry(state: _RuntimeDiagnosticsState, kind: str) -> dict[str, Any]:
    state.sequence += 1
    return {
        "sequence": state.sequence,
        "kind": kind,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "monotonic_seconds": time.monotonic(),
        "process_id": os.getpid(),
        "thread_id": threading.get_ident(),
        "thread_name": threading.current_thread().name,
    }


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary_path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(temporary_path, path)


def record_jdtls_phase(phase: str, **details: object) -> None:
    """Record a JDTLS lifecycle phase without relying on Python logging."""
    root = _diagnostics_root()
    if root is None:
        return

    try:
        with _STATE_LOCK:
            state = _STATE_BY_ROOT.setdefault(root, _RuntimeDiagnosticsState())
            entry = _new_entry(state, "phase")
            entry["phase"] = phase
            if details:
                entry["details"] = details
            state.phases.append(entry)
            _write_json_atomic(root / JDTLS_LAST_PHASE_FILENAME, entry)
            _write_json_atomic(
                root / JDTLS_PHASE_TAIL_FILENAME,
                {
                    "max_entries": _PHASE_TAIL_SIZE,
                    "entries": list(state.phases),
                },
            )
    except OSError:
        # Diagnostics must never change language-server behavior.
        return


def record_jdtls_lifecycle(ls_id: object, phase: str, **details: object) -> None:
    if _is_java_language_server(ls_id):
        record_jdtls_phase(phase, **details)


def _summarize_lsp_message(source: str, target: str, message: dict[str, Any] | str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "source": source,
        "target": target,
    }
    if isinstance(message, str):
        summary.update({"message_kind": "text", "length": len(message)})
        return summary

    method = message.get("method")
    request_id = message.get("id")
    if method is not None:
        summary["method"] = method
    if request_id is not None:
        summary["request_id"] = request_id

    if method is not None and request_id is not None:
        summary["message_kind"] = "request"
    elif method is not None:
        summary["message_kind"] = "notification"
    elif request_id is not None:
        summary["message_kind"] = "response"
    else:
        summary["message_kind"] = "other"

    if "result" in message:
        summary["has_result"] = True
    error = message.get("error")
    if isinstance(error, dict):
        summary["error_code"] = error.get("code")

    params = message.get("params")
    if method == "language/status" and isinstance(params, dict):
        summary["status_type"] = params.get("type")
        summary["status_message"] = params.get("message")

    return summary


def _record_jdtls_lsp_message(source: str, target: str, message: dict[str, Any] | str) -> None:
    root = _diagnostics_root()
    if root is None:
        return

    try:
        with _STATE_LOCK:
            state = _STATE_BY_ROOT.setdefault(root, _RuntimeDiagnosticsState())
            entry = _new_entry(state, "lsp")
            entry.update(_summarize_lsp_message(source, target, message))
            state.lsp_messages.append(entry)
    except OSError:
        return


def snapshot_runtime_diagnostics(output_dir: Path) -> list[Path]:
    """Persist a point-in-time copy of the in-memory JDTLS phase and LSP tails."""
    root = _diagnostics_root()
    if root is None:
        return []

    with _STATE_LOCK:
        state = _STATE_BY_ROOT.get(root)
        if state is None:
            return []

        written_paths: list[Path] = []
        if state.phases:
            last_phase_path = output_dir / JDTLS_LAST_PHASE_FILENAME
            _write_json_atomic(last_phase_path, state.phases[-1])
            written_paths.append(last_phase_path)

            phase_tail_path = output_dir / JDTLS_PHASE_TAIL_FILENAME
            _write_json_atomic(
                phase_tail_path,
                {
                    "max_entries": _PHASE_TAIL_SIZE,
                    "entries": list(state.phases),
                },
            )
            written_paths.append(phase_tail_path)

        if state.lsp_messages:
            lsp_tail_path = output_dir / JDTLS_LSP_TAIL_FILENAME
            _write_json_atomic(
                lsp_tail_path,
                {
                    "max_entries": _LSP_TAIL_SIZE,
                    "entries": list(state.lsp_messages),
                },
            )
            written_paths.append(lsp_tail_path)

        return written_paths


def wrap_jdtls_lsp_trace_logger(ls_id: object, delegate: LSPTraceLogger | None) -> LSPTraceLogger | None:
    """
    Add a bounded, payload-free JDTLS trace to an existing LSP trace logger.

    Only method names, request IDs, directions, response/error presence, and
    ``language/status`` values are persisted. Request parameters and response
    bodies are deliberately omitted.
    """
    if not _is_java_language_server(ls_id) or _diagnostics_root() is None:
        return delegate

    def trace(source: str, target: str, message: dict[str, Any] | str) -> None:
        if delegate is not None:
            delegate(source, target, message)
        _record_jdtls_lsp_message(source, target, message)

    return trace


def jdtls_canary_is_enabled() -> bool:
    value = os.environ.get(JDTLS_CANARY_PHASE_ENV)
    return value is not None and bool(value.strip())


def wait_for_jdtls_canary_stall(cancel_event: threading.Event) -> bool:
    """Wait until the test-only JDTLS canary enters its deliberate stall."""
    while not cancel_event.is_set():
        if _CANARY_STALL_STARTED.wait(timeout=0.1):
            return True
    return False


def notify_jdtls_canary_diagnostics_captured() -> None:
    """Release a deliberate JDTLS stall after its live diagnostics are complete."""
    _CANARY_DIAGNOSTICS_CAPTURED.set()


def maybe_stall_jdtls_canary(phase: str) -> None:
    """Deliberately stall at a named phase when the branch-only CI canary requests it."""
    configured_phase = os.environ.get(JDTLS_CANARY_PHASE_ENV)
    if configured_phase != phase:
        return

    duration_value = os.environ.get(JDTLS_CANARY_STALL_SECONDS_ENV, "150")
    duration_seconds = float(duration_value)
    if duration_seconds <= 0:
        raise ValueError(f"{JDTLS_CANARY_STALL_SECONDS_ENV} must be positive")

    record_jdtls_phase(
        "canary_stall_started",
        target_phase=phase,
        duration_seconds=duration_seconds,
    )
    _CANARY_STALL_STARTED.set()
    diagnostics_captured = _CANARY_DIAGNOSTICS_CAPTURED.wait(timeout=duration_seconds)
    record_jdtls_phase(
        "canary_stall_completed",
        target_phase=phase,
        diagnostics_captured=diagnostics_captured,
    )


def _reset_runtime_diagnostics_for_tests() -> None:
    with _STATE_LOCK:
        _STATE_BY_ROOT.clear()
        _CANARY_STALL_STARTED.clear()
        _CANARY_DIAGNOSTICS_CAPTURED.clear()
