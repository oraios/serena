from typing import Any
from unittest.mock import MagicMock

import pytest

from solidlsp.ls_config import LanguageServerId
from test.conftest import start_ls_context


def _open_count_for_three_requests(monkeypatch: pytest.MonkeyPatch, ls_specific_settings: dict[LanguageServerId, dict[str, Any]]) -> int:
    with start_ls_context(LanguageServerId.CPP, ls_specific_settings=ls_specific_settings) as language_server:
        did_open = MagicMock(wraps=language_server.server.notify.did_open_text_document)
        monkeypatch.setattr(language_server.server.notify, "did_open_text_document", did_open)
        for _ in range(3):
            language_server.request_references("b.cpp", 2, 4)
        return sum(1 for call in did_open.call_args_list if call.args[0]["textDocument"]["uri"].endswith("/b.cpp"))


@pytest.mark.cpp
class TestClangdFilesKeptOpen:
    def test_file_used_repeatedly_is_opened_once_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert _open_count_for_three_requests(monkeypatch, {}) == 1

    def test_zero_files_kept_open_reopens_the_file_for_every_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert _open_count_for_three_requests(monkeypatch, {LanguageServerId.CPP: {"files_kept_open": 0}}) == 3

    def test_diagnostics_of_a_kept_file_are_returned(self) -> None:
        with start_ls_context(LanguageServerId.CPP) as language_server:
            language_server.request_references("diagnostics_sample.cpp", 0, 0)
            diagnostics = language_server.request_text_document_diagnostics("diagnostics_sample.cpp")
        assert len(diagnostics) >= 1
