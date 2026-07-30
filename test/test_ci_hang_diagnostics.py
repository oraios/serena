from pathlib import Path
from typing import TextIO

import pytest

import test.ci_hang_diagnostics as diagnostics
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
    serena_home = tmp_path / "serena-home"
    workspace_log = (
        serena_home / "language_servers" / "static" / "EclipseJDTLS" / "workspaces" / "workspace-hash" / "data_dir" / ".metadata" / ".log"
    )
    workspace_log.parent.mkdir(parents=True)
    workspace_log.write_text("JDTLS workspace error log\n", encoding="utf-8")

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

    collector = HangDiagnosticsCollector(output_root=tmp_path / "diagnostics", serena_home=serena_home)
    capture_dir = collector.collect("test/solidlsp/java/test_java.py::test_stall")

    assert "test_stall" in (capture_dir / "metadata.json").read_text(encoding="utf-8")
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
