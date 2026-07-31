from __future__ import annotations

import faulthandler
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from solidlsp import ci_hang_diagnostics as runtime_diagnostics

DIAGNOSTICS_DIR_ENV = runtime_diagnostics.DIAGNOSTICS_DIR_ENV
DIAGNOSTICS_DELAY_ENV = "SERENA_CI_HANG_DIAGNOSTICS_SECONDS"

_COMMAND_TIMEOUT_SECONDS = 30.0
_JDTLS_PROCESS_MARKERS = ("org.eclipse.equinox.launcher", "org.eclipse.jdt.ls.core")
_METADATA_ENVIRONMENT_VARIABLES = (
    "CI",
    "GITHUB_ACTIONS",
    "GITHUB_JOB",
    "GITHUB_RUN_ATTEMPT",
    "GITHUB_RUN_ID",
    "RUNNER_ARCH",
    "RUNNER_NAME",
    "RUNNER_OS",
    runtime_diagnostics.JDTLS_CANARY_PHASE_ENV,
    runtime_diagnostics.JDTLS_CANARY_STALL_SECONDS_ENV,
    "SERENA_CI_JDTLS_REPRO_MODE",
)


@dataclass(frozen=True)
class CommandResult:
    """Result of a best-effort diagnostics command."""

    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and self.error is None

    def render(self) -> str:
        sections = [
            f"command: {subprocess.list2cmdline(self.command)}",
            f"returncode: {self.returncode}",
        ]
        if self.error is not None:
            sections.append(f"error: {self.error}")
        sections.extend(
            (
                "\nstdout:",
                self.stdout,
                "\nstderr:",
                self.stderr,
            )
        )
        return "\n".join(sections).rstrip() + "\n"


@dataclass(frozen=True)
class ProcessSnapshot:
    """Process-tree state captured from the running pytest process."""

    records: list[dict[str, Any]]
    jdtls_pids: set[int]
    jdtls_data_dirs: set[Path] = field(default_factory=set)


def parse_jdtls_pids(jcmd_output: str) -> set[int]:
    """
    Extract JDTLS process IDs from ``jcmd -l`` output.

    :param jcmd_output: output emitted by ``jcmd -l``
    :return: process IDs whose main command identifies Eclipse JDTLS
    """
    result: set[int] = set()

    # inspect JVM descriptions...
    for line in jcmd_output.splitlines():
        pid_text, separator, description = line.strip().partition(" ")
        if not separator or not pid_text.isdigit():
            continue
        if _is_jdtls_process(description):
            result.add(int(pid_text))

    return result


def _is_jdtls_process(description: str) -> bool:
    normalized_description = description.casefold()
    return any(marker.casefold() in normalized_description for marker in _JDTLS_PROCESS_MARKERS)


def _coerce_subprocess_output(output: str | bytes | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


def _run_command(command: list[str], timeout_seconds: float) -> CommandResult:
    # execute command...
    try:
        completed_process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        return CommandResult(
            command=command,
            returncode=completed_process.returncode,
            stdout=completed_process.stdout,
            stderr=completed_process.stderr,
        )
    except subprocess.TimeoutExpired as exception:
        return CommandResult(
            command=command,
            returncode=None,
            stdout=_coerce_subprocess_output(exception.stdout),
            stderr=_coerce_subprocess_output(exception.stderr),
            error=f"timed out after {timeout_seconds:g} seconds",
        )
    except OSError as exception:
        return CommandResult(
            command=command,
            returncode=None,
            stdout="",
            stderr="",
            error=f"{type(exception).__name__}: {exception}",
        )


def _collect_process_snapshot() -> ProcessSnapshot:
    records: list[dict[str, Any]] = []
    jdtls_pids: set[int] = set()
    jdtls_data_dirs: set[Path] = set()

    # limit collection to pytest and its descendants...
    pytest_process = psutil.Process(os.getpid())
    try:
        processes = [pytest_process, *pytest_process.children(recursive=True)]
    except (psutil.Error, OSError):
        processes = [pytest_process]

    # inspect process metadata...
    for process in processes:
        try:
            record = process.as_dict(attrs=["pid", "ppid", "name", "cmdline", "status", "create_time"])
            records.append(record)

            command_line = [str(argument) for argument in record.get("cmdline") or []]
            if _is_jdtls_process(" ".join(command_line)):
                jdtls_pids.add(int(record["pid"]))
                if (data_dir := _extract_jdtls_data_dir(command_line)) is not None:
                    jdtls_data_dirs.add(data_dir)
        except (psutil.Error, OSError) as exception:
            records.append({"pid": process.pid, "error": f"{type(exception).__name__}: {exception}"})

    return ProcessSnapshot(records=records, jdtls_pids=jdtls_pids, jdtls_data_dirs=jdtls_data_dirs)


def _extract_jdtls_data_dir(command_line: list[str]) -> Path | None:
    for index, argument in enumerate(command_line[:-1]):
        if argument == "-data":
            return Path(command_line[index + 1])
    return None


@dataclass(frozen=True)
class HangDiagnosticsCollector:
    """Best-effort collector for a pytest stall involving Eclipse JDTLS."""

    output_root: Path
    serena_home: Path
    command_timeout_seconds: float = _COMMAND_TIMEOUT_SECONDS

    def collect(self, nodeid: str) -> Path:
        """
        Capture Python and JVM state without terminating either process.

        :param nodeid: pytest node ID active when the watchdog fired
        :return: directory containing the captured evidence
        """
        captured_at = datetime.now(UTC)
        capture_dir = self.output_root / f"hang-{captured_at.strftime('%Y%m%dT%H%M%SZ')}-pid-{os.getpid()}"
        capture_dir.mkdir(parents=True, exist_ok=False)
        errors: list[str] = []

        # record test metadata...
        try:
            self._write_metadata(capture_dir, nodeid, captured_at)
        except Exception as exception:
            errors.append(self._format_error("metadata", exception))

        # snapshot phase markers and the bounded LSP trace...
        try:
            self._capture_runtime_diagnostics(capture_dir)
        except Exception as exception:
            errors.append(self._format_error("runtime diagnostics", exception))

        # dump all Python threads...
        try:
            self._capture_python_threads(capture_dir)
        except Exception as exception:
            errors.append(self._format_error("Python thread dump", exception))

        # inspect pytest descendants...
        process_snapshot = ProcessSnapshot(records=[], jdtls_pids=set())
        try:
            process_snapshot = _collect_process_snapshot()
            self._write_json(capture_dir / "pytest-process-tree.json", process_snapshot.records)
        except Exception as exception:
            errors.append(self._format_error("process tree", exception))

        # dump live JDTLS JVMs...
        try:
            self._capture_jdtls_threads(capture_dir, process_snapshot.jdtls_pids)
        except Exception as exception:
            errors.append(self._format_error("JDTLS thread dump", exception))

        # preserve Eclipse workspace logs...
        try:
            self._capture_jdtls_logs(capture_dir, process_snapshot.jdtls_data_dirs)
        except Exception as exception:
            errors.append(self._format_error("JDTLS logs", exception))

        # mark capture outcome...
        if errors:
            (capture_dir / "capture-errors.txt").write_text("\n".join(errors) + "\n", encoding="utf-8")
        (capture_dir / "capture-complete.txt").write_text(
            f"Diagnostics collection completed at {datetime.now(UTC).isoformat()}.\n",
            encoding="utf-8",
        )

        return capture_dir

    def _write_metadata(self, capture_dir: Path, nodeid: str, captured_at: datetime) -> None:
        environment = {name: value for name in _METADATA_ENVIRONMENT_VARIABLES if (value := os.environ.get(name)) is not None}
        metadata = {
            "captured_at": captured_at.isoformat(),
            "pytest_nodeid": nodeid,
            "python_executable": sys.executable,
            "python_pid": os.getpid(),
            "python_version": sys.version,
            "platform": platform.platform(),
            "environment": environment,
        }
        self._write_json(capture_dir / "metadata.json", metadata)

    def _capture_runtime_diagnostics(self, capture_dir: Path) -> None:
        output_dir = capture_dir / "jdtls-runtime-diagnostics"
        output_dir.mkdir()
        manifest: list[dict[str, str | int]] = []

        for destination_path in runtime_diagnostics.snapshot_runtime_diagnostics(output_dir):
            manifest.append(
                {
                    "source": "in-memory-runtime-snapshot",
                    "destination": destination_path.name,
                    "size_bytes": destination_path.stat().st_size,
                }
            )

        self._write_json(output_dir / "manifest.json", manifest)

    @staticmethod
    def _capture_python_threads(capture_dir: Path) -> None:
        with (capture_dir / "python-threads.txt").open("w", encoding="utf-8") as stream:
            stream.write("All Python threads captured by faulthandler:\n\n")
            stream.flush()
            faulthandler.dump_traceback(file=stream, all_threads=True)

    def _capture_jdtls_threads(self, capture_dir: Path, process_tree_pids: set[int]) -> None:
        jcmd_executable = shutil.which("jcmd")
        jstack_executable = shutil.which("jstack")

        # enumerate visible JVMs...
        if jcmd_executable is None:
            jcmd_list_result = CommandResult(
                command=["jcmd", "-l"],
                returncode=None,
                stdout="",
                stderr="",
                error="jcmd was not found on PATH",
            )
        else:
            jcmd_list_result = _run_command([jcmd_executable, "-l"], self.command_timeout_seconds)
        (capture_dir / "jcmd-list.txt").write_text(jcmd_list_result.render(), encoding="utf-8")

        # combine both discovery methods...
        jdtls_pids = set(process_tree_pids)
        jdtls_pids.update(parse_jdtls_pids(jcmd_list_result.stdout))
        if not jdtls_pids:
            (capture_dir / "jdtls-process-not-found.txt").write_text(
                "No live JVM matched the Eclipse Equinox launcher or JDTLS main class.\n",
                encoding="utf-8",
            )
            return

        # attach to each JDTLS process...
        for pid in sorted(jdtls_pids):
            jcmd_thread_result: CommandResult | None = None
            if jcmd_executable is not None:
                jcmd_thread_result = _run_command(
                    [jcmd_executable, str(pid), "Thread.print", "-l"],
                    self.command_timeout_seconds,
                )
                (capture_dir / f"jvm-{pid}-jcmd-thread-print.txt").write_text(jcmd_thread_result.render(), encoding="utf-8")

            if jcmd_thread_result is not None and jcmd_thread_result.succeeded and jcmd_thread_result.stdout.strip():
                continue

            if jstack_executable is None:
                (capture_dir / f"jvm-{pid}-jstack-unavailable.txt").write_text(
                    "jstack was not found on PATH, so no fallback dump could be attempted.\n",
                    encoding="utf-8",
                )
                continue

            jstack_result = _run_command(
                [jstack_executable, "-l", str(pid)],
                self.command_timeout_seconds,
            )
            (capture_dir / f"jvm-{pid}-jstack.txt").write_text(jstack_result.render(), encoding="utf-8")

    def _capture_jdtls_logs(self, capture_dir: Path, active_data_dirs: set[Path]) -> None:
        workspace_root = self.serena_home / "language_servers" / "static" / "EclipseJDTLS" / "workspaces"
        output_dir = capture_dir / "jdtls-workspace-logs"
        output_dir.mkdir()
        manifest: list[dict[str, str | int]] = []

        # prefer logs named by active JDTLS command lines...
        active_logs = sorted((data_dir / ".metadata" / ".log" for data_dir in active_data_dirs), key=str)
        selected_logs = [(path, "active-process") for path in active_logs if path.is_file()]

        # fall back to logs updated near the current test...
        if not selected_logs:
            workspace_logs = sorted(
                workspace_root.glob("*/data_dir/.metadata/.log"),
                key=self._safe_mtime,
                reverse=True,
            )
            recent_cutoff = time.time() - 2 * 60 * 60
            recent_logs = [path for path in workspace_logs if self._safe_mtime(path) >= recent_cutoff]
            fallback_logs = recent_logs[:3] if recent_logs else workspace_logs[:1]
            selected_logs = [(path, "recent-fallback") for path in fallback_logs]

        # copy selected workspace error logs...
        for index, (source_path, selection) in enumerate(selected_logs):
            try:
                workspace_id = source_path.relative_to(workspace_root).parts[0]
            except ValueError:
                workspace_id = source_path.parents[2].name
            destination_path = output_dir / f"{index:02d}-{workspace_id}.log"
            try:
                shutil.copy2(source_path, destination_path)
                manifest.append(
                    {
                        "source": str(source_path),
                        "destination": destination_path.name,
                        "selection": selection,
                        "size_bytes": destination_path.stat().st_size,
                    }
                )
            except OSError as exception:
                manifest.append(
                    {
                        "source": str(source_path),
                        "selection": selection,
                        "error": f"{type(exception).__name__}: {exception}",
                    }
                )

        self._write_json(output_dir / "manifest.json", manifest)

    @staticmethod
    def _safe_mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0

    @staticmethod
    def _write_json(path: Path, value: object) -> None:
        path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

    @staticmethod
    def _format_error(phase: str, exception: Exception) -> str:
        return f"{phase}: {type(exception).__name__}: {exception}"


@dataclass
class HangDiagnosticsWatchdog:
    """Per-test timer that captures diagnostics before pytest-timeout aborts."""

    nodeid: str
    delay_seconds: float
    collector: HangDiagnosticsCollector
    _timer: threading.Timer | None = field(default=None, init=False, repr=False)
    _worker: threading.Thread | None = field(default=None, init=False, repr=False)
    _cancel_event: threading.Event = field(default_factory=threading.Event, init=False, repr=False)

    @classmethod
    def from_environment(cls, nodeid: str) -> HangDiagnosticsWatchdog | None:
        """
        Create an enabled watchdog from CI environment variables.

        :param nodeid: pytest node ID about to run
        :return: configured watchdog, or None when diagnostics are disabled
        :raises ValueError: if the configured delay is not positive
        """
        output_root_value = os.environ.get(DIAGNOSTICS_DIR_ENV)
        delay_value = os.environ.get(DIAGNOSTICS_DELAY_ENV)
        if not output_root_value or not delay_value:
            return None

        # validate timing...
        delay_seconds = float(delay_value)
        if delay_seconds <= 0:
            raise ValueError(f"{DIAGNOSTICS_DELAY_ENV} must be positive")

        # resolve Serena storage...
        serena_home_value = os.environ.get("SERENA_HOME")
        serena_home = Path(serena_home_value) if serena_home_value and serena_home_value.strip() else Path.home() / ".serena"
        collector = HangDiagnosticsCollector(
            output_root=Path(output_root_value),
            serena_home=serena_home,
        )
        return cls(nodeid=nodeid, delay_seconds=delay_seconds, collector=collector)

    def start(self) -> None:
        if self._timer is not None or self._worker is not None:
            raise RuntimeError("hang diagnostics watchdog has already been started")

        # The deliberate Windows canary arms collection only after JDTLS reaches the
        # requested stall. Normal CI continues to use a fixed per-test deadline.
        if runtime_diagnostics.jdtls_canary_is_enabled():
            worker = threading.Thread(
                target=self._collect_after_canary_stall,
                name="serena-ci-jdtls-canary-diagnostics",
                daemon=True,
            )
            self._worker = worker
            worker.start()
            return

        # schedule capture...
        timer = threading.Timer(self.delay_seconds, self._collect)
        timer.name = "serena-ci-hang-diagnostics"
        timer.daemon = True
        self._timer = timer
        timer.start()

    def cancel(self) -> None:
        self._cancel_event.set()
        if self._timer is not None:
            self._timer.cancel()

    def _collect_after_canary_stall(self) -> None:
        if not runtime_diagnostics.wait_for_jdtls_canary_stall(self._cancel_event):
            return
        if self._cancel_event.wait(timeout=self.delay_seconds):
            return
        try:
            self._collect()
        finally:
            runtime_diagnostics.notify_jdtls_canary_diagnostics_captured()

    def _collect(self) -> None:
        self.collector.collect(self.nodeid)
