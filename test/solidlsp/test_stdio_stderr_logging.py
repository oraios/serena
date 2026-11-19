# SPDX-License-Identifier: MIT

import io
import logging
from unittest.mock import MagicMock

import pytest

from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_process import StdioLanguageServer


def _server_reading_stderr(data: bytes) -> StdioLanguageServer:
    server = StdioLanguageServer(
        process_launch_info=MagicMock(),
        ls_id=LanguageServerId.CPP,
        determine_log_level=lambda _line: logging.WARNING,
    )
    stderr = io.BytesIO(data)
    process = MagicMock()
    process.stderr = stderr
    process.poll.side_effect = lambda: 0 if stderr.tell() == len(data) else None
    server._process = process
    server._is_stopping = True
    return server


@pytest.mark.parametrize("line_ending", ["\n", "\r\n"])
def test_stderr_lines_are_logged_without_line_endings(caplog: pytest.LogCaptureFixture, line_ending: str) -> None:
    lines = ["I[12:00:00.000] <-- textDocument/didOpen", "  continuation line"]
    data = "".join(line + line_ending for line in [*lines, ""]).encode()
    server = _server_reading_stderr(data)

    with caplog.at_level(logging.WARNING, logger="solidlsp.ls_process"):
        server._read_ls_process_stderr()

    assert [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING] == lines
