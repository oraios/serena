import logging
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from serena.util.non_blocking_stderr_handler import NonBlockingStderrHandler


def _run_with_undrained_stderr(script: str, timeout: float = 30.0) -> tuple[int, str]:
    """Runs the script with its stderr connected to a pipe that the parent never reads —
    exactly the scenario of an MCP client host that ignores the spawned server's stderr.
    stdout IS drained (non-blocking, polled) so that print() output survives.

    A raw os.pipe() is used because subprocess' own PIPE handling would drain stderr via
    communicate(), defeating the purpose; and communicate() is avoided for stdout as well
    (observed to hang when a custom stderr fd is combined with a never-drained pipe).

    :return: (returncode, stdout text); returncode is -9 (killed) when the child had to be
        terminated after `timeout` seconds because it hung
    """
    read_fd, write_fd = os.pipe()
    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", textwrap.dedent(script)],
            stdout=subprocess.PIPE,
            stderr=write_fd,  # child writes here; we never read read_fd, so it fills up
        )
        os.close(write_fd)  # parent does not write
        deadline = time.monotonic() + timeout
        stdout_chunks: list[bytes] = []
        os.set_blocking(proc.stdout.fileno(), False)
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            try:
                chunk = proc.stdout.read()
                if chunk:
                    stdout_chunks.append(chunk)
            except Exception:
                pass
            time.sleep(0.05)
        try:
            chunk = proc.stdout.read()
            if chunk:
                stdout_chunks.append(chunk)
        except Exception:
            pass
        if proc.poll() is None:
            proc.kill()
            proc.wait()
            return proc.returncode, b"".join(stdout_chunks).decode()
        return proc.returncode, b"".join(stdout_chunks).decode()
    finally:
        os.close(read_fd)  # never drained by design


class TestBlockingStreamHandlerDeadlocks:
    """Documents the deadlock that the plain StreamHandler produces when stderr is a
    socketpair/pipe that nobody drains (the MCP client host scenario). These tests use
    a subprocess whose stderr is a pipe that the parent never reads; the pipe has a
    small buffer (64 KiB on Linux socketpairs), so enough logging fills it and the
    process deadlocks with exit code None (killed by timeout) unless the handler is
    non-blocking.
    """

    def test_blocking_stream_handler_deadlocks_when_stderr_is_undrained(self):
        """The pre-fix behaviour: a blocked stderr write holds the logging lock and freezes
        the process even though the log-producing work is long finished. This test documents
        the deadlock (it fails until a non-blocking handler is used); it is expected to pass
        with `NonBlockingStderrHandler` and to hang otherwise.
        """
        script = """
        import logging, sys, threading, time

        logging.basicConfig(level=logging.INFO)  # default StreamHandler(stderr)

        result_holder = {}

        def work():
            # simulate the tool that finishes quickly but logs a lot afterwards
            time.sleep(0.1)
            result_holder["done"] = True
            for i in range(100000):  # enough records to fill a 64 KiB stderr buffer many times over
                logging.info(f"record {i} " + "x" * 100)

        t = threading.Thread(target=work)
        t.start()

        deadline = time.monotonic() + 10
        while "done" not in result_holder and time.monotonic() < deadline:
            time.sleep(0.05)

        # the work itself finished long ago; with a blocking StreamHandler on an undrained
        # stderr, THIS log call deadlocks the main thread (logging's global lock is held
        # by the worker thread blocked inside write()).
        logging.info("post-work log from main thread")
        print("SURVIVED", flush=True)
        sys.exit(0)
        """
        returncode, stdout = _run_with_undrained_stderr(script, timeout=15.0)
        # the deadlock signature: the main thread finishes its work and prints SURVIVED, but the
        # process cannot exit because the log-producing worker thread is blocked forever inside
        # the stderr write (holding the logging lock) — the parent must kill it (rc=-9)
        assert "SURVIVED" in stdout and returncode == -9, (
            f"expected the blocking handler to deadlock the child at exit (rc={returncode}, stdout={stdout!r})"
        )

    def test_non_blocking_handler_survives_undrained_stderr(self):
        """The fixed behaviour: with NonBlockingStderrHandler installed, the same workload
        completes and the process exits 0 promptly, even though its stderr pipe is full
        and never drained.
        """
        script = """
        import logging, sys, threading, time
        sys.path.insert(0, {repo_src!r})

        from serena.util.non_blocking_stderr_handler import NonBlockingStderrHandler

        handler = NonBlockingStderrHandler()
        logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(message)s", force=True)

        result_holder = {{}}

        def work():
            time.sleep(0.1)
            result_holder["done"] = True
            for i in range(100000):
                logging.info(f"record {{i}} " + "x" * 100)

        t = threading.Thread(target=work)
        t.start()

        deadline = time.monotonic() + 10
        while "done" not in result_holder and time.monotonic() < deadline:
            time.sleep(0.05)

        logging.info("post-work log from main thread")
        print("SURVIVED", flush=True)
        sys.exit(0)
        """.format(repo_src=str(Path(__file__).parents[2] / "src"))
        started = time.monotonic()
        returncode, stdout = _run_with_undrained_stderr(script, timeout=25.0)
        elapsed = time.monotonic() - started
        assert "SURVIVED" in stdout, f"process did not survive the undrained stderr (rc={returncode}, elapsed={elapsed:.1f}s)"
        assert elapsed < 20, f"process took too long ({elapsed:.1f}s) — suspected blocking"


class TestNonBlockingStderrHandlerUnit:
    def test_emits_to_full_pipe_without_blocking(self, tmp_path):
        """A full pipe must not block the emitting thread: records are dropped (OSError/BlockingIOError
        swallowed) and emit() returns promptly.
        """
        # create a real pipe and never drain it
        read_fd, write_fd = os.pipe()
        try:
            stream = os.fdopen(write_fd, "w", encoding="utf-8")
            handler = NonBlockingStderrHandler(stream=stream)
            assert handler._nonblocking_fd  # the fd must have been switched to non-blocking

            start = time.monotonic()
            for i in range(5000):  # enough to fill any pipe buffer many times over
                handler.emit(logging.LogRecord("n", logging.INFO, "p", 1, f"m{i} " + "x" * 100, (), None))
            elapsed = time.monotonic() - start
            assert elapsed < 5.0, f"emit() blocked on a full pipe ({elapsed:.2f}s for 5000 records)"
        finally:
            os.close(read_fd)
            stream.close()

    def test_writes_reach_pipe_when_drained(self, tmp_path):
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

    def test_tty_like_stream_writes_normally(self):
        """A stream without a bounded buffer (no fileno, e.g. StringIO) uses plain writes."""
        import io

        buf = io.StringIO()
        handler = NonBlockingStderrHandler(stream=buf)
        handler.emit(logging.LogRecord("n", logging.INFO, "p", 1, "hello", (), None))
        assert "hello" in buf.getvalue()

    def test_fd_is_nonblocking_only_for_pipes_and_sockets(self, tmp_path):
        """Regular files must NOT be made non-blocking (O_NONBLOCK on files has different
        semantics); pipes must be.
        """
        file_path = tmp_path / "out.log"
        read_fd, write_fd = os.pipe()
        try:
            pipe_stream = os.fdopen(write_fd, "w", encoding="utf-8")
            pipe_handler = NonBlockingStderrHandler(stream=pipe_stream)
            assert pipe_handler._nonblocking_fd

            with open(file_path, "w", encoding="utf-8") as file_stream:
                file_handler = NonBlockingStderrHandler(stream=file_stream)
                assert not file_handler._nonblocking_fd

            pipe_stream.close()
        finally:
            os.close(read_fd)
