import shutil
import threading
from pathlib import Path
from typing import Any

import pytest

from solidlsp import ls_types
from solidlsp.ls_config import LanguageServerId
from test.conftest import get_repo_path, start_ls_context


def _outline(symbols: list[ls_types.UnifiedSymbolInformation]) -> list[tuple[str, int, list]]:
    return [(symbol["name"], symbol["kind"], _outline(symbol["children"])) for symbol in symbols]


def _scan_uncached_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ls_specific_settings: dict[LanguageServerId, dict[str, Any]]
) -> tuple[list[tuple[str, int, list]], int]:
    repo_path = tmp_path / "test_repo"
    shutil.copytree(get_repo_path(LanguageServerId.CPP), repo_path, ignore=shutil.ignore_patterns(".serena"))
    with start_ls_context(
        LanguageServerId.CPP, repo_path=str(repo_path), ls_specific_settings=ls_specific_settings, solidlsp_dir=tmp_path
    ) as language_server:
        lock = threading.Lock()
        running = 0
        max_running = 0
        send_document_symbol = language_server.server.send.document_symbol

        def tracked_document_symbol(params: dict) -> Any:
            nonlocal running, max_running
            with lock:
                running += 1
                max_running = max(max_running, running)
            try:
                return send_document_symbol(params)
            finally:
                with lock:
                    running -= 1

        monkeypatch.setattr(language_server.server.send, "document_symbol", tracked_document_symbol)
        return _outline(language_server.request_full_symbol_tree()), max_running


@pytest.mark.cpp
class TestClangdParallelSymbolScan:
    def test_parallel_scan_returns_the_same_tree_as_a_sequential_one(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        sequential_outline, sequential_max_running = _scan_uncached_fixture(
            tmp_path / "sequential", monkeypatch, {LanguageServerId.CPP: {"parallel_document_symbol_requests": 1}}
        )
        parallel_outline, parallel_max_running = _scan_uncached_fixture(tmp_path / "parallel", monkeypatch, {})

        assert sequential_max_running == 1
        assert parallel_max_running >= 2
        assert parallel_outline == sequential_outline
