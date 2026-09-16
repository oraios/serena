import io
import logging
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from serena.util.non_blocking_stderr_handler import NonBlockingStderrHandler


def _run_with_undrained_stderr(script: str, marker_path: str, timeout: float = 30.0) -> tuple[int, str]:
    """Runs the script with its stderr connected to a pipe that the parent never reads —
    exactly the scenario of an MCP client host that ignores the spawned server's stderr.

    The child receives `marker_path` as its first argument; it reports success by writing
    the text ``SURVIVED`` to the marker file and exiting. The parent never drains stderr,
    so a child that blocks inside a stderr write hangs and is killed after `timeout` seconds.

    :return: (returncode, marker file content); returncode is -9 (killed) when the child hung
    """
    read_fd, write_fd = os.pipe()
    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", script, marker_path],
            stdout=subprocess.DEVNULL,
            stderr=write_fd,  # child writes here; we never read read_fd, so it fills up
        )
        os.close(write_fd)  # parent does not write
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    finally:
        os.close(read_fd)  # never drained by design

    marker = Path(marker_path)
    return proc.returncode, marker.read_text(encoding="utf-8") if marker.exists() else ""


@pytest.mark.skipif(sys.platform == "win32", reason="anonymous pipes cannot be made non-blocking on Windows (see the handler's docstring)")
class TestNonBlockingStderrHandlerSurvival:
    """Exercises the handler in a subprocess whose stderr is a pipe that the parent never
    reads (the MCP client host scenario): the process must complete its work and exit 0.
    """

    def test_handler_survives_undrained_stderr(self, tmp_path):
        """A workload that floods stderr after its work is done must complete and exit 0
        even though its stderr pipe is full and never drained.
        """
        script = f"""
        import logging, sys, threading
        sys.path.insert(0, {str(Path(__file__).parents[2] / "src")!r})
        from serena.util.non_blocking_stderr_handler import NonBlockingStderrHandler

        handler = NonBlockingStderrHandler()
        logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(message)s", force=True)

        def work():
            for i in range(100000):  # enough records to fill the stderr buffer many times over
                logging.info(f"record {{i}} " + "x" * 100)

        t = threading.Thread(target=work)
        t.start()
        t.join()

        with open(sys.argv[1], 'w') as marker:
            marker.write('SURVIVED')
        logging.info("post-work log from main thread")
        sys.exit(0)
        """
        marker_path = str(tmp_path / "marker.txt")

        returncode, marker_content = _run_with_undrained_stderr(textwrap.dedent(script), marker_path, timeout=30.0)

        assert "SURVIVED" in marker_content, f"process did not survive the undrained stderr (rc={returncode})"
        assert returncode == 0, f"process did not exit cleanly (rc={returncode})"

    def test_emits_to_full_pipe_without_blocking(self, tmp_path):
        """A full pipe must not block the emitting thread: records are dropped and emit()
        returns for all of them.
        """
        read_fd, write_fd = os.pipe()
        try:
            stream = os.fdopen(write_fd, "w", encoding="utf-8")
            handler = NonBlockingStderrHandler(stream=stream)

            start = time.monotonic()
            for i in range(5000):  # enough to fill any pipe buffer many times over
                handler.emit(logging.LogRecord("n", logging.INFO, "p", 1, f"m{i} " + "x" * 100, (), None))
            elapsed = time.monotonic() - start
            assert elapsed < 30.0, f"emit() blocked on a full pipe ({elapsed:.2f}s for 5000 records)"
        finally:
            os.close(read_fd)
            stream.close()


class TestNonBlockingStderrHandlerDelivery:
    def test_writes_reach_pipe_when_drained(self):
        """When the pipe is drained, records arrive complete and in order."""
        read_fd, write_fd = os.pipe()
        try:
            stream = os.fdopen(write_fd, "w", encoding="utf-8")
            handler = NonBlockingStderrHandler(stream=stream)
            for i in range(10):
                handler.emit(logging.LogRecord("n", logging.INFO, "p", 1, f"record {i}", (), None))
            stream.flush()
            data = os.read(read_fd, 65536).decode()
            assert [f"record {i}" for i in range(10)] == [ln.split("- ")[-1] for ln in data.splitlines() if ln]
        finally:
            os.close(read_fd)
            stream.close()

    def test_stream_without_fileno_writes_normally(self):
        """A stream without a bounded buffer (no fileno, e.g. StringIO) uses plain writes."""
        buf = io.StringIO()
        handler = NonBlockingStderrHandler(stream=buf)
        handler.emit(logging.LogRecord("n", logging.INFO, "p", 1, "hello", (), None))
        assert "hello" in buf.getvalue()
