# SPDX-License-Identifier: MIT
"""Real stdio transport shutdown releases every owned subprocess pipe."""

import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_process import StdioLanguageServer
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.util.subprocess_util import ManagedSubprocess, ManagedSubprocessLauncher


@pytest.mark.parametrize("exit_mode", ["shutdown", "already-exited", "uncooperative", "termination-error"])
def test_stop_releases_subprocess_pipes(exit_mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    ready = threading.Event()
    helper = Path(__file__).parents[1] / "resources" / "stdio_test_server.py"
    server = StdioLanguageServer(
        ProcessLaunchInfo(cmd=[sys.executable, "-u", str(helper), exit_mode]),
        ls_id=LanguageServerId.PYTHON,
        determine_log_level=lambda _line: logging.INFO,
        request_timeout=2,
    )
    server.on_notification("ready", lambda _params: ready.set())
    process = None
    terminate = None
    pipes = []
    try:
        server.start()
        process = server._process
        assert process is not None
        terminate = process.terminate
        pipes = [process.stdin, process.stdout, process.stderr]
        assert ready.wait(5), "helper server did not start"
        if exit_mode == "already-exited":
            server.send_notification("crash", {})
            deadline = time.monotonic() + 5
            while process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert process.poll() is not None
        if exit_mode == "termination-error":

            def terminate_with_error(timeout: float) -> None:
                terminate(timeout=timeout)
                raise RuntimeError("termination report failed")

            monkeypatch.setattr(process, "terminate", terminate_with_error)
            with pytest.raises(RuntimeError, match="termination report failed"):
                server.stop(timeout=2)
        else:
            server.stop(timeout=2)
        assert process.poll() is not None
        deadline = time.monotonic() + 2
        while not all(pipe is not None and pipe.closed for pipe in pipes) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert all(pipe is not None and pipe.closed for pipe in pipes), "stop left a subprocess pipe open"
        server.stop(timeout=2)
    finally:
        if terminate is not None:
            terminate(timeout=2)
        for pipe in pipes:
            if pipe is not None:
                pipe.close()


def test_restart_keeps_replacement_server_responsive() -> None:
    ready = threading.Event()
    helper = Path(__file__).parents[1] / "resources" / "stdio_test_server.py"
    server = StdioLanguageServer(
        ProcessLaunchInfo(cmd=[sys.executable, "-u", str(helper), "shutdown"]),
        ls_id=LanguageServerId.PYTHON,
        determine_log_level=lambda _line: logging.INFO,
        request_timeout=2,
    )
    server.on_notification("ready", lambda _params: ready.set())
    pipes = []
    try:
        for _ in range(5):
            ready.clear()
            server.start()
            process = server._process
            assert process is not None
            pipes.extend([process.stdin, process.stdout, process.stderr])
            assert ready.wait(5)
            assert server.send_request("ping", {}) is None
            server.stop(timeout=2)
        deadline = time.monotonic() + 2
        while not all(pipe is not None and pipe.closed for pipe in pipes) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert all(pipe is not None and pipe.closed for pipe in pipes)
    finally:
        server.stop(timeout=2)
        for pipe in pipes:
            if pipe is not None:
                pipe.close()


def test_immediately_exited_process_releases_pipes(monkeypatch: pytest.MonkeyPatch) -> None:
    popen = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stderr.write('startup failed'); sys.exit(7)"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    process = ManagedSubprocess(popen, name="Startup failure", start_new_session=False)
    server = StdioLanguageServer(
        ProcessLaunchInfo(cmd=[sys.executable]),
        ls_id=LanguageServerId.PYTHON,
        determine_log_level=lambda _line: logging.INFO,
    )
    try:
        popen.wait(timeout=5)
        monkeypatch.setattr(ManagedSubprocessLauncher.get_instance(), "launch", lambda *_args, **_kwargs: process)
        with pytest.raises(RuntimeError, match="Process terminated immediately with code 7. Error: startup failed"):
            server.start()
        assert all(pipe is not None and pipe.closed for pipe in (popen.stdin, popen.stdout, popen.stderr))
        server.stop(timeout=2)
    finally:
        process.terminate(timeout=2)
        for pipe in (popen.stdin, popen.stdout, popen.stderr):
            if pipe is not None:
                pipe.close()
