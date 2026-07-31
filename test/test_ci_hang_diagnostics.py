import json
import threading
from pathlib import Path
from typing import TextIO

import pytest

import test.ci_hang_diagnostics as diagnostics
from solidlsp import ci_hang_diagnostics as runtime_diagnostics
from test.ci_hang_diagnostics import (
    CommandResult,
    HangDiagnosticsCollector,
    HangDiagnosticsWatchdog,
    ProcessSnapshot,
    parse_jdtls_pids,
)


def test_parse_jdtls_pids() -> None:
    output = """
    111 C:\\tools\\plugins\\org.eclipse.equinox.launcher_1.6.900.jar -data C:\\workspace
    222 org.eclipse.jdt.ls.core.id1
    333 org.gradle.launcher.daemon.bootstrap.GradleDaemon
    malformed
    """

    assert parse_jdtls_pids(output) == {111, 222}


def test_watchdog_reads_configuration_from_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    serena_home = tmp_path / "serena-home"
    monkeypatch.setenv(diagnostics.DIAGNOSTICS_DIR_ENV, str(tmp_path / "diagnostics"))
    monkeypatch.setenv(diagnostics.DIAGNOSTICS_DELAY_ENV, "12.5")
    monkeypatch.setenv("SERENA_HOME", str(serena_home))

    watchdog = HangDiagnosticsWatchdog.from_environment("test/example.py::test_stall")

    assert watchdog is not None
    assert watchdog.delay_seconds == 12.5
    assert watchdog.collector.serena_home == serena_home


def test_collector_captures_python_jvm_and_workspace_logs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    diagnostics_root = tmp_path / "diagnostics"
    serena_home = tmp_path / "serena-home"
    workspace_log = (
        serena_home / "language_servers" / "static" / "EclipseJDTLS" / "workspaces" / "workspace-hash" / "data_dir" / ".metadata" / ".log"
    )
    workspace_log.parent.mkdir(parents=True)
    workspace_log.write_text("JDTLS workspace error log\n", encoding="utf-8")
    monkeypatch.setenv(runtime_diagnostics.DIAGNOSTICS_DIR_ENV, str(diagnostics_root))
    runtime_diagnostics._reset_runtime_diagnostics_for_tests()
    runtime_diagnostics.record_jdtls_phase("service_ready_wait_started")
    trace_logger = runtime_diagnostics.wrap_jdtls_lsp_trace_logger("java", None)
    assert trace_logger is not None
    trace_logger("solidlsp", "ls", {"jsonrpc": "2.0", "id": 7, "method": "initialize", "params": {"secret": "omitted"}})

    # replace live process inspection...
    monkeypatch.setattr(
        diagnostics,
        "_collect_process_snapshot",
        lambda: ProcessSnapshot(
            records=[{"pid": 4321, "name": "java.exe", "cmdline": ["org.eclipse.equinox.launcher"]}],
            jdtls_pids={4321},
            jdtls_data_dirs={workspace_log.parents[1]},
        ),
    )
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: f"/fake/{name}" if name == "jcmd" else None)

    # replace external diagnostics commands...
    def run_command(command: list[str], timeout_seconds: float) -> CommandResult:
        assert timeout_seconds == 30
        if command[-1] == "-l" and len(command) == 2:
            return CommandResult(command, 0, "4321 org.eclipse.jdt.ls.core.id1\n", "")
        return CommandResult(command, 0, '"JDT Main Thread" #1 WAITING\n', "")

    monkeypatch.setattr(diagnostics, "_run_command", run_command)

    # replace faulthandler's direct file-descriptor write...
    def dump_traceback(*, file: TextIO, all_threads: bool) -> None:
        assert all_threads
        file.write("Python worker thread waiting in Event.wait\n")

    monkeypatch.setattr(diagnostics.faulthandler, "dump_traceback", dump_traceback)

    collector = HangDiagnosticsCollector(output_root=diagnostics_root, serena_home=serena_home)
    capture_dir = collector.collect("test/solidlsp/java/test_java.py::test_stall")

    assert "test_stall" in (capture_dir / "metadata.json").read_text(encoding="utf-8")
    assert "service_ready_wait_started" in (
        capture_dir / "jdtls-runtime-diagnostics" / runtime_diagnostics.JDTLS_LAST_PHASE_FILENAME
    ).read_text(encoding="utf-8")
    copied_lsp_trace = (capture_dir / "jdtls-runtime-diagnostics" / runtime_diagnostics.JDTLS_LSP_TAIL_FILENAME).read_text(encoding="utf-8")
    assert '"method": "initialize"' in copied_lsp_trace
    assert "secret" not in copied_lsp_trace
    assert "Event.wait" in (capture_dir / "python-threads.txt").read_text(encoding="utf-8")
    assert "WAITING" in (capture_dir / "jvm-4321-jcmd-thread-print.txt").read_text(encoding="utf-8")
    copied_logs = list((capture_dir / "jdtls-workspace-logs").glob("*.log"))
    assert len(copied_logs) == 1
    assert copied_logs[0].read_text(encoding="utf-8") == "JDTLS workspace error log\n"
    assert (capture_dir / "capture-complete.txt").is_file()


def test_collector_falls_back_to_jstack(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        diagnostics,
        "_collect_process_snapshot",
        lambda: ProcessSnapshot(records=[], jdtls_pids={9876}),
    )
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: f"/fake/{name}")

    def run_command(command: list[str], timeout_seconds: float) -> CommandResult:
        if command[-1] == "-l" and len(command) == 2:
            return CommandResult(command, 0, "9876 org.eclipse.jdt.ls.core.id1\n", "")
        if "Thread.print" in command:
            return CommandResult(command, 1, "", "AttachNotSupportedException")
        return CommandResult(command, 0, '"Worker" WAITING on PlexusContainerManager\n', "")

    monkeypatch.setattr(diagnostics, "_run_command", run_command)
    monkeypatch.setattr(diagnostics.faulthandler, "dump_traceback", lambda **kwargs: None)

    collector = HangDiagnosticsCollector(
        output_root=tmp_path / "diagnostics",
        serena_home=tmp_path / "serena-home",
    )
    capture_dir = collector.collect("test/example.py::test_stall")

    assert "PlexusContainerManager" in (capture_dir / "jvm-9876-jstack.txt").read_text(encoding="utf-8")


def test_runtime_diagnostics_keep_bounded_payload_free_lsp_tail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    diagnostics_root = tmp_path / "runtime"
    monkeypatch.setenv(runtime_diagnostics.DIAGNOSTICS_DIR_ENV, str(diagnostics_root))
    runtime_diagnostics._reset_runtime_diagnostics_for_tests()

    runtime_diagnostics.record_jdtls_phase("initialize_request_sending", workspace=tmp_path / "workspace")
    delegate_messages: list[object] = []
    trace_logger = runtime_diagnostics.wrap_jdtls_lsp_trace_logger(
        "java",
        lambda source, target, message: delegate_messages.append(message),
    )
    assert trace_logger is not None
    for request_id in range(405):
        trace_logger(
            "solidlsp",
            "ls",
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "textDocument/references",
                "params": {"secret_file_contents": "must not be persisted"},
            },
        )

    runtime_diagnostics.snapshot_runtime_diagnostics(diagnostics_root)
    phase = json.loads((diagnostics_root / runtime_diagnostics.JDTLS_LAST_PHASE_FILENAME).read_text(encoding="utf-8"))
    trace = json.loads((diagnostics_root / runtime_diagnostics.JDTLS_LSP_TAIL_FILENAME).read_text(encoding="utf-8"))
    serialized_trace = json.dumps(trace)

    assert phase["phase"] == "initialize_request_sending"
    assert len(delegate_messages) == 405
    assert len(trace["entries"]) == trace["max_entries"] == 400
    assert trace["entries"][0]["request_id"] == 5
    assert trace["entries"][-1]["request_id"] == 404
    assert "secret_file_contents" not in serialized_trace
    assert "must not be persisted" not in serialized_trace


def test_canary_stall_arms_diagnostics_worker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(runtime_diagnostics.DIAGNOSTICS_DIR_ENV, str(tmp_path))
    monkeypatch.setenv(runtime_diagnostics.JDTLS_CANARY_PHASE_ENV, "before_service_ready_wait")
    monkeypatch.setenv(runtime_diagnostics.JDTLS_CANARY_STALL_SECONDS_ENV, "1")
    runtime_diagnostics._reset_runtime_diagnostics_for_tests()
    runtime_diagnostics.notify_jdtls_canary_diagnostics_captured()

    runtime_diagnostics.maybe_stall_jdtls_canary("before_service_ready_wait")

    assert runtime_diagnostics.wait_for_jdtls_canary_stall(threading.Event())
    phase_tail = json.loads((tmp_path / runtime_diagnostics.JDTLS_PHASE_TAIL_FILENAME).read_text(encoding="utf-8"))
    assert [entry["phase"] for entry in phase_tail["entries"][-2:]] == [
        "canary_stall_started",
        "canary_stall_completed",
    ]


def test_watchdog_collects_after_canary_stall_signal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(runtime_diagnostics.DIAGNOSTICS_DIR_ENV, str(tmp_path))
    monkeypatch.setenv(runtime_diagnostics.JDTLS_CANARY_PHASE_ENV, "before_service_ready_wait")
    monkeypatch.setenv(runtime_diagnostics.JDTLS_CANARY_STALL_SECONDS_ENV, "1")
    runtime_diagnostics._reset_runtime_diagnostics_for_tests()
    collected = threading.Event()

    def collect(collector: HangDiagnosticsCollector, nodeid: str) -> Path:
        collected.set()
        return tmp_path / "capture"

    monkeypatch.setattr(HangDiagnosticsCollector, "collect", collect)
    watchdog = HangDiagnosticsWatchdog(
        nodeid="test/example.py::test_canary",
        delay_seconds=0,
        collector=HangDiagnosticsCollector(output_root=tmp_path, serena_home=tmp_path / "serena-home"),
    )

    watchdog.start()
    runtime_diagnostics.maybe_stall_jdtls_canary("before_service_ready_wait")

    assert collected.wait(timeout=1)
    watchdog.cancel()
