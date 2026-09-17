"""A full-document ``textDocument/didChange`` sent when an already-open file is re-opened
after changing on disk must carry a new document version, as the range-based didChange
notifications for edits do; reusing the number breaks everything a server keys on it.
"""

import os
from unittest.mock import MagicMock

from solidlsp.ls import LSPFileBuffer


def _buffer(tmp_path, notify: MagicMock) -> LSPFileBuffer:
    path = tmp_path / "main.py"
    path.write_text("x = 1\n", encoding="utf-8")
    language_server = MagicMock()
    language_server.server.notify = notify
    return LSPFileBuffer(
        abs_path=path,
        uri=path.as_uri(),
        encoding="utf-8",
        version=0,
        language_id="python",
        ref_count=1,
        language_server=language_server,
    )


def _bump_mtime(path) -> None:
    stat = path.stat()
    os.utime(path, (stat.st_atime + 10, stat.st_mtime + 10))


def test_reopen_after_disk_change_bumps_version(tmp_path) -> None:
    notify = MagicMock()
    buffer = _buffer(tmp_path, notify)
    opened = notify.did_open_text_document.call_args.args[0]["textDocument"]
    assert opened["version"] == 0

    buffer.abs_path.write_text("x = 2\n", encoding="utf-8")
    _bump_mtime(buffer.abs_path)
    buffer.ensure_open_in_ls()

    notify.did_change_text_document.assert_called_once()
    changed = notify.did_change_text_document.call_args.args[0]
    assert changed["textDocument"]["version"] == 1
    assert changed["contentChanges"] == [{"text": "x = 2\n"}]
    assert buffer.version == 1

    buffer.abs_path.write_text("x = 3\n", encoding="utf-8")
    _bump_mtime(buffer.abs_path)
    buffer.ensure_open_in_ls()
    assert notify.did_change_text_document.call_args.args[0]["textDocument"]["version"] == 2


def test_reopen_without_disk_change_sends_nothing(tmp_path) -> None:
    notify = MagicMock()
    buffer = _buffer(tmp_path, notify)

    buffer.ensure_open_in_ls()

    notify.did_change_text_document.assert_not_called()
    assert buffer.version == 0
