"""didChange notifications for in-memory edits follow the text document synchronisation the server negotiated."""

from pathlib import Path
from typing import Any, cast

import pytest

from solidlsp import ls_types
from solidlsp.ls import LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_request import LanguageServerRequest
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams

_FULL_SYNC_RESULTS = [
    pytest.param({"capabilities": {"textDocumentSync": 1}}, id="kind"),
    pytest.param({"capabilities": {"textDocumentSync": {"openClose": True, "change": 1, "save": {"includeText": True}}}}, id="options"),
]

_RANGED_SYNC_RESULTS = [
    pytest.param({"capabilities": {"textDocumentSync": 2}}, id="incremental-kind"),
    pytest.param({"capabilities": {"textDocumentSync": {"openClose": True, "change": 2}}}, id="incremental-options"),
    pytest.param({"capabilities": {"textDocumentSync": {"openClose": True}}}, id="options-without-change"),
    pytest.param({"capabilities": {}}, id="capability-omitted"),
    pytest.param(None, id="no-result"),
]


class _RecordingNotify:
    def __init__(self) -> None:
        self.did_change_params: list[dict[str, Any]] = []

    def did_change_text_document(self, params: dict[str, Any]) -> None:
        self.did_change_params.append(params)


class _InitializedServer:
    """Stand-in for a language server process which has answered the initialize request with the given result."""

    def __init__(self, initialize_result: Any) -> None:
        self._initialize_result = initialize_result
        self.send = LanguageServerRequest(cast(Any, self))
        self.notify = _RecordingNotify()
        self.send.initialize(cast(InitializeParams, {}))

    def send_request(self, method: str, params: Any = None) -> Any:
        assert method == "initialize"
        return self._initialize_result


class _UnstartedLanguageServer(SolidLanguageServer):
    """Language server whose process is the given stand-in rather than a launched server."""

    def __init__(self, server: _InitializedServer, repository_root_path: Path) -> None:
        # not calling super().__init__, which sets up the interface to a real server process
        self.server = cast(Any, server)
        self.server_started = True
        self.repository_root_path = str(repository_root_path)
        self.open_file_buffers = {}

    def _create_base_initialize_params(self) -> InitializeParams:
        raise NotImplementedError

    def _start_server(self) -> None:
        raise NotImplementedError


def _language_server_with_open_file(tmp_path: Path, initialize_result: Any) -> tuple[SolidLanguageServer, _RecordingNotify]:
    """
    :return: a language server, which has not been started as a process, with ``doc.txt`` (containing ``hello``) open,
        and the recorder of the notifications it sends
    """
    server = _InitializedServer(initialize_result)
    ls = _UnstartedLanguageServer(server, tmp_path)

    path = tmp_path / "doc.txt"
    path.write_text("hello\n")
    ls.open_file_buffers[path.as_uri()] = LSPFileBuffer(
        abs_path=path,
        uri=path.as_uri(),
        encoding="utf-8",
        version=0,
        language_id="plaintext",
        ref_count=1,
        language_server=ls,
        open_in_ls=False,
    )
    return ls, server.notify


def _content_changes_with_versions(notify: _RecordingNotify) -> list[tuple[int, list[dict[str, Any]]]]:
    return [(params["textDocument"]["version"], params["contentChanges"]) for params in notify.did_change_params]


@pytest.mark.parametrize("initialize_result", _FULL_SYNC_RESULTS)
def test_edits_send_full_text_when_server_negotiated_full_sync(tmp_path: Path, initialize_result: Any) -> None:
    ls, notify = _language_server_with_open_file(tmp_path, initialize_result)

    end = ls.insert_text_at_position("doc.txt", 0, 5, " world")
    deleted = ls.delete_text_between_positions("doc.txt", ls_types.Position(line=0, character=5), end)

    assert deleted == " world"
    assert _content_changes_with_versions(notify) == [(1, [{"text": "hello world\n"}]), (2, [{"text": "hello\n"}])]


@pytest.mark.parametrize("initialize_result", _RANGED_SYNC_RESULTS)
def test_edits_send_ranged_changes_unless_server_negotiated_full_sync(tmp_path: Path, initialize_result: Any) -> None:
    ls, notify = _language_server_with_open_file(tmp_path, initialize_result)

    end = ls.insert_text_at_position("doc.txt", 0, 5, " world")
    ls.delete_text_between_positions("doc.txt", ls_types.Position(line=0, character=5), end)

    start = {"line": 0, "character": 5}
    assert _content_changes_with_versions(notify) == [
        (1, [{"range": {"start": start, "end": start}, "text": " world"}]),
        (2, [{"range": {"start": start, "end": {"line": 0, "character": 11}}, "text": ""}]),
    ]
