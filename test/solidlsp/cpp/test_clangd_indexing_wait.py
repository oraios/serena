import threading
import time
from typing import Any

import pytest

from solidlsp.language_servers.clangd_language_server import ClangdLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.conftest import _create_ls

_TOKEN = "backgroundIndexProgress"


def _clangd(settings: dict[str, Any]) -> ClangdLanguageServer:
    language_server = _create_ls(LanguageServerId.CPP, ls_specific_settings={LanguageServerId.CPP: {"ls_path": "/opt/clangd", **settings}})
    assert isinstance(language_server, ClangdLanguageServer)
    return language_server


def _report_indexing_started(language_server: ClangdLanguageServer) -> None:
    language_server._on_work_done_progress_create({"token": _TOKEN})
    language_server._indexing_progress.on_progress({"token": _TOKEN, "value": {"kind": "begin", "title": "indexing"}})


def _report_indexing_ended(language_server: ClangdLanguageServer) -> None:
    language_server._indexing_progress.on_progress({"token": _TOKEN, "value": {"kind": "end"}})


def _seconds_waited(language_server: ClangdLanguageServer) -> float:
    start = time.monotonic()
    language_server._wait_for_cross_file_references_if_needed()
    return time.monotonic() - start


@pytest.mark.cpp
class TestClangdIndexingWait:
    def test_first_cross_file_query_waits_until_indexing_ends(self) -> None:
        language_server = _clangd({})
        _report_indexing_started(language_server)
        threading.Timer(0.5, _report_indexing_ended, args=[language_server]).start()

        assert 0.5 <= _seconds_waited(language_server) < 3.0

    def test_no_reported_indexing_ends_the_wait_after_the_start_grace(self) -> None:
        language_server = _clangd({"indexing_start_grace": 0.2})

        assert _seconds_waited(language_server) < 1.0

    def test_indexing_that_does_not_end_is_waited_for_at_most_the_timeout(self) -> None:
        language_server = _clangd({"indexing_timeout": 0.3})
        _report_indexing_started(language_server)

        assert _seconds_waited(language_server) < 1.5

    def test_only_the_first_cross_file_query_waits(self) -> None:
        language_server = _clangd({"indexing_timeout": 0.3})
        _report_indexing_started(language_server)
        _seconds_waited(language_server)

        assert _seconds_waited(language_server) < 0.1

    @pytest.mark.parametrize("value", ["soon", None, 0])
    def test_invalid_start_grace_falls_back_to_the_default(self, value: object) -> None:
        language_server = _clangd({"indexing_start_grace": value})

        assert 1.9 <= _seconds_waited(language_server) < 3.0
