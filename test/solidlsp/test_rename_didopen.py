from unittest.mock import MagicMock

from solidlsp.ls import SolidLanguageServer


class DummyLanguageServer(SolidLanguageServer):
    def _start_server(self) -> None:
        raise AssertionError("Not used in this test")


def test_request_rename_symbol_edit_opens_file_before_rename(tmp_path) -> None:
    (tmp_path / "index.ts").write_text("export const x = 1;\n", encoding="utf-8")

    events: list[str] = []

    notify = MagicMock()
    notify.did_open_text_document.side_effect = lambda *_args, **_kwargs: events.append("didOpen")
    notify.did_close_text_document.side_effect = lambda *_args, **_kwargs: events.append("didClose")

    send = MagicMock()
    send.rename.side_effect = lambda *_args, **_kwargs: events.append("rename")

    server = MagicMock()
    server.notify = notify
    server.send = send

    language_server = object.__new__(DummyLanguageServer)
    language_server.repository_root_path = str(tmp_path)
    language_server.server_started = True
    language_server.open_file_buffers = {}
    language_server._encoding = "utf-8"
    language_server.language_id = "typescript"
    language_server.server = server

    result = language_server.request_rename_symbol_edit(
        relative_file_path="index.ts",
        line=0,
        column=0,
        new_name="y",
    )
    assert result is None
    assert events == ["didOpen", "rename", "didClose"]
