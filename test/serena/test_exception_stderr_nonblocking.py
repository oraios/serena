# SPDX-License-Identifier: GPL-3.0-or-later
"""show_fatal_exception_safe must not raise when stderr is non-blocking."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from serena.util.exception import show_fatal_exception_safe


def test_fatal_print_survives_blocking_io_error_on_stderr() -> None:
    """A full non-blocking stderr pipe raises BlockingIOError on print; that must not escape."""
    e = RuntimeError("boom")
    log = MagicMock()

    class _ExplodingStderr:
        def write(self, _msg: str) -> int:
            raise BlockingIOError(11, "Resource temporarily unavailable")

        def flush(self) -> None:
            return None

    with (
        patch("serena.util.exception.log", log),
        patch("serena.util.exception.is_headless_environment", return_value=True),
        patch.object(sys, "stderr", _ExplodingStderr()),
    ):
        # Must not raise
        show_fatal_exception_safe(e)

    # The primary path still logs
    assert log.error.called
    assert any("Fatal exception" in str(call.args[0]) for call in log.error.call_args_list)


def test_fatal_print_survives_os_error_on_stderr() -> None:
    e = RuntimeError("boom")
    log = MagicMock()

    class _BrokenStderr:
        def write(self, _msg: str) -> int:
            raise OSError("stderr gone")

        def flush(self) -> None:
            return None

    with (
        patch("serena.util.exception.log", log),
        patch("serena.util.exception.is_headless_environment", return_value=True),
        patch.object(sys, "stderr", _BrokenStderr()),
    ):
        show_fatal_exception_safe(e)

    assert log.error.called
