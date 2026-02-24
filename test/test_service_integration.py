"""Integration tests for the Serena HTTP service lifecycle.

These tests start actual Serena services, so they are slower and require
the full Serena runtime. Run with::

    uv run pytest test/test_service_integration.py -v -m service

They are excluded from the default test suite.
"""

import os
import signal
import subprocess
import time

import pytest
import requests


@pytest.mark.service
class TestServiceLifecycle:
    """Test the full start -> status -> stop lifecycle."""

    def test_foreground_start_and_heartbeat(self) -> None:
        """Start a service in foreground (as subprocess), check HTTP, then stop."""
        project_path = os.path.dirname(os.path.abspath(__file__))
        port = 24199  # Use top of range to avoid conflicts

        proc = subprocess.Popen(
            [
                "uv",
                "run",
                "serena",
                "service",
                "start",
                project_path,
                "--port",
                str(port),
                "--foreground",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            # Wait for server to start (up to 30s)
            started = False
            for _ in range(30):
                try:
                    resp = requests.post(
                        f"http://127.0.0.1:{port}/mcp",
                        json={},
                        timeout=1,
                    )
                    started = True
                    break
                except requests.ConnectionError:
                    time.sleep(1)

            assert started, "Service did not start within 30 seconds"
            # Any HTTP response means the server is alive
            assert resp.status_code in (200, 400, 405, 415, 422)

        finally:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
