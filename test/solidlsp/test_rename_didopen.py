from unittest.mock import MagicMock

from solidlsp.ls import SolidLanguageServer


class DummyLanguageServer(SolidLanguageServer):
    def _start_server(self) -> None:
        raise AssertionError("Not used in this test")

    def _create_base_initialize_params(self) -> dict:
        return {}


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
    language_server._warm_file_buffers = {}
    language_server._warm_buffer_ttl = 30.0
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
    # with the warm file buffer cache, the buffer is not closed (didClose) when the
    # open_file context exits: it is kept warm for the TTL and closed lazily later
    assert events == ["didOpen", "rename"]
    assert language_server._warm_file_buffers  # buffer retained for fast reopen
