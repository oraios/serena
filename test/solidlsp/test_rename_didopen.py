from unittest.mock import MagicMock

from solidlsp.ls import SolidLanguageServer


class DummyLanguageServer(SolidLanguageServer):
    events: list[str]

    def _start_server(self) -> None:
        raise AssertionError("Not used in this test")

    def _create_base_initialize_params(self) -> dict:
        return {}

    def _pre_open_for_cross_file_references(self) -> None:
        self.events.append("preOpenForCrossFileReferences")

    def _wait_for_cross_file_references_if_needed(self) -> None:
        self.events.append("waitForCrossFileReferences")


def _dummy_language_server(tmp_path, events: list[str], send: MagicMock) -> DummyLanguageServer:
    notify = MagicMock()
    notify.did_open_text_document.side_effect = lambda *_args, **_kwargs: events.append("didOpen")
    notify.did_close_text_document.side_effect = lambda *_args, **_kwargs: events.append("didClose")

    server = MagicMock()
    server.notify = notify
    server.send = send

    language_server = object.__new__(DummyLanguageServer)
    language_server.events = events
    language_server.repository_root_path = str(tmp_path)
    language_server.server_started = True
    language_server.open_file_buffers = {}
    language_server._encoding = "utf-8"
    language_server.language_id = "typescript"
    language_server.server = server
    return language_server


def test_request_rename_symbol_edit_waits_for_cross_file_references_before_rename(tmp_path) -> None:
    # A rename edits every reference, so it must not be sent before the server is ready for cross-file
    # requests; otherwise e.g. typescript-language-server answers from the open files only while it is
    # still loading the project.
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
    language_server.events = events
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
    assert events == ["preOpenForCrossFileReferences", "didOpen", "waitForCrossFileReferences", "rename", "didClose"]


def test_request_will_rename_files_waits_for_cross_file_references_before_request(tmp_path) -> None:
    # The edits a file rename needs are in the files that import it, so the request needs the same
    # cross-file readiness as a symbol rename.
    (tmp_path / "index.ts").write_text("export const x = 1;\n", encoding="utf-8")

    events: list[str] = []
    send = MagicMock()
    send.will_rename_files.side_effect = lambda *_args, **_kwargs: events.append("willRenameFiles")
    language_server = _dummy_language_server(tmp_path, events, send)

    result = language_server.request_will_rename_files("index.ts", "main.ts")
    assert result is None
    assert events == ["preOpenForCrossFileReferences", "didOpen", "waitForCrossFileReferences", "willRenameFiles", "didClose"]
