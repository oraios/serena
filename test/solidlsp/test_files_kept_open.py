# SPDX-License-Identifier: MIT

import os
from collections.abc import Callable
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig, LanguageServerId
from solidlsp.ls_process import LanguageServerInterface
from solidlsp.lsp_protocol_handler.server import StringDict
from solidlsp.settings import SolidLSPSettings


class _ScriptedLanguageServer(SolidLanguageServer):
    def __init__(self, repository_root_path: Path, files_kept_open: int) -> None:
        self._number_of_files_kept_open = files_kept_open
        settings = SolidLSPSettings(solidlsp_dir=str(repository_root_path / ".solidlsp"), project_data_path=str(repository_root_path))
        super().__init__(LanguageServerConfig(LanguageServerId.PYTHON), str(repository_root_path), None, "python", settings)
        self.server_started = True

    def _create_language_server_interface(self, logging_fn: Callable[[str, str, StringDict | str], None] | None) -> LanguageServerInterface:
        server = MagicMock()
        server.send.references.return_value = []
        return server

    def _start_server(self) -> None:
        raise AssertionError("Not used in this test")

    def _create_base_initialize_params(self) -> dict:
        return {}

    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 0

    def _get_number_of_files_kept_open_in_ls(self) -> int:
        return self._number_of_files_kept_open


def _notified_uris(language_server: SolidLanguageServer, notification: str) -> list[str]:
    server = cast(MagicMock, language_server.server)
    return [call.args[0]["textDocument"]["uri"] for call in getattr(server.notify, notification).call_args_list]


def _write_files(tmp_path: Path, *names: str) -> dict[str, str]:
    for name in names:
        (tmp_path / name).write_text("x = 1\n", encoding="utf-8")
    return {name: (tmp_path / name).as_uri() for name in names}


def test_file_used_by_consecutive_requests_is_opened_once(tmp_path: Path) -> None:
    uri = _write_files(tmp_path, "a.py")
    language_server = _ScriptedLanguageServer(tmp_path, files_kept_open=1)

    language_server.request_references("a.py", 0, 0)
    language_server.request_references("a.py", 0, 0)

    assert _notified_uris(language_server, "did_open_text_document") == [uri["a.py"]]
    assert _notified_uris(language_server, "did_close_text_document") == []


def test_least_recently_used_file_is_closed_when_the_limit_is_exceeded(tmp_path: Path) -> None:
    uri = _write_files(tmp_path, "a.py", "b.py")
    language_server = _ScriptedLanguageServer(tmp_path, files_kept_open=1)

    language_server.request_references("a.py", 0, 0)
    language_server.request_references("b.py", 0, 0)

    assert _notified_uris(language_server, "did_open_text_document") == [uri["a.py"], uri["b.py"]]
    assert _notified_uris(language_server, "did_close_text_document") == [uri["a.py"]]


def test_kept_file_changed_on_disk_is_updated_in_the_language_server(tmp_path: Path) -> None:
    _write_files(tmp_path, "a.py")
    language_server = _ScriptedLanguageServer(tmp_path, files_kept_open=1)
    language_server.request_references("a.py", 0, 0)

    path = tmp_path / "a.py"
    path.write_text("x = 2\n", encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    language_server.request_references("a.py", 0, 0)

    server = cast(MagicMock, language_server.server)
    change = server.notify.did_change_text_document.call_args.args[0]
    assert change["contentChanges"][0]["text"] == "x = 2\n"


def test_stopping_closes_the_kept_files(tmp_path: Path) -> None:
    uri = _write_files(tmp_path, "a.py", "b.py")
    language_server = _ScriptedLanguageServer(tmp_path, files_kept_open=2)
    language_server.request_references("a.py", 0, 0)
    language_server.request_references("b.py", 0, 0)

    language_server.stop()

    assert sorted(_notified_uris(language_server, "did_close_text_document")) == sorted([uri["a.py"], uri["b.py"]])


def test_diagnostics_request_opens_a_kept_file_anew(tmp_path: Path) -> None:
    uri = _write_files(tmp_path, "a.py")
    language_server = _ScriptedLanguageServer(tmp_path, files_kept_open=1)
    language_server.request_references("a.py", 0, 0)

    language_server.request_published_text_document_diagnostics("a.py", timeout=0)

    assert _notified_uris(language_server, "did_open_text_document") == [uri["a.py"], uri["a.py"]]
    assert _notified_uris(language_server, "did_close_text_document") == [uri["a.py"]]


def test_no_file_is_kept_open_when_the_limit_is_zero(tmp_path: Path) -> None:
    uri = _write_files(tmp_path, "a.py")
    language_server = _ScriptedLanguageServer(tmp_path, files_kept_open=0)

    language_server.request_references("a.py", 0, 0)
    language_server.request_references("a.py", 0, 0)

    assert _notified_uris(language_server, "did_open_text_document") == [uri["a.py"], uri["a.py"]]
    assert _notified_uris(language_server, "did_close_text_document") == [uri["a.py"], uri["a.py"]]
