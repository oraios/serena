# SPDX-License-Identifier: MIT

import contextvars
import threading
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

from solidlsp import ls_types
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig, LanguageServerId
from solidlsp.ls_process import LanguageServerInterface
from solidlsp.lsp_protocol_handler.server import StringDict
from solidlsp.settings import SolidLSPSettings

_FILE_COUNT = 8

_CALLER_CONTEXT: contextvars.ContextVar[str | None] = contextvars.ContextVar("caller_context", default=None)


class _SlowSymbolServer:
    def __init__(self, files_without_symbols: frozenset[str] = frozenset(), files_failing_once: frozenset[str] = frozenset()) -> None:
        self._files_without_symbols = files_without_symbols
        self._files_failing_once = files_failing_once
        self._lock = threading.Lock()
        self._running = 0
        self.max_running = 0
        self.requests_per_file: Counter[str] = Counter()
        self.caller_contexts: list[str | None] = []

    def document_symbol(self, params: dict) -> list[dict]:
        name = Path(params["textDocument"]["uri"]).stem
        with self._lock:
            self._running += 1
            self.requests_per_file[name] += 1
            self.caller_contexts.append(_CALLER_CONTEXT.get())
            self.max_running = max(self.max_running, self._running)
            is_first_request = self.requests_per_file[name] == 1
        time.sleep(0.1)
        with self._lock:
            self._running -= 1
        if name in self._files_failing_once and is_first_request:
            raise RuntimeError(f"First request for {name} fails")
        if name in self._files_without_symbols:
            return []
        symbol_range = {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 5}}
        return [{"name": name, "kind": ls_types.SymbolKind.Variable, "range": symbol_range, "selectionRange": symbol_range, "children": []}]


class _ScriptedLanguageServer(SolidLanguageServer):
    def __init__(self, repository_root_path: Path, parallel_requests: int, symbol_server: _SlowSymbolServer) -> None:
        self._parallel_requests = parallel_requests
        self._symbol_server = symbol_server
        settings = SolidLSPSettings(solidlsp_dir=str(repository_root_path / ".solidlsp"), project_data_path=str(repository_root_path))
        super().__init__(LanguageServerConfig(LanguageServerId.PYTHON), str(repository_root_path), None, "python", settings)
        self.server_started = True

    def _create_language_server_interface(self, logging_fn: Callable[[str, str, StringDict | str], None] | None) -> LanguageServerInterface:
        server = MagicMock()
        server.send.document_symbol.side_effect = self._symbol_server.document_symbol
        return server

    def _start_server(self) -> None:
        raise AssertionError("Not used in this test")

    def _create_base_initialize_params(self) -> dict:
        return {}

    def _get_number_of_parallel_document_symbol_requests(self) -> int:
        return self._parallel_requests


def _scan(tmp_path: Path, parallel_requests: int, symbol_server: _SlowSymbolServer | None = None) -> tuple[list[str], _SlowSymbolServer]:
    package = tmp_path / "pkg"
    package.mkdir(parents=True, exist_ok=True)
    for index in range(_FILE_COUNT):
        (package / f"module_{index}.py").write_text(f"module_{index} = {index}\n", encoding="utf-8")
    symbol_server = symbol_server or _SlowSymbolServer()
    language_server = _ScriptedLanguageServer(tmp_path, parallel_requests, symbol_server)

    tree = language_server.request_full_symbol_tree("pkg")

    symbol_names = [
        symbol["name"] for package_symbol in tree for file_symbol in package_symbol["children"] for symbol in file_symbol["children"]
    ]
    return symbol_names, symbol_server


def test_directory_scan_requests_document_symbols_in_parallel(tmp_path: Path) -> None:
    _, symbol_server = _scan(tmp_path, parallel_requests=4)

    assert 2 <= symbol_server.max_running <= 4
    assert symbol_server.requests_per_file == Counter({f"module_{index}": 1 for index in range(_FILE_COUNT)})


def test_parallel_directory_scan_returns_the_same_tree_as_a_sequential_one(tmp_path: Path) -> None:
    sequential_names, _ = _scan(tmp_path / "sequential", parallel_requests=1)
    parallel_names, _ = _scan(tmp_path / "parallel", parallel_requests=4)

    assert parallel_names == sequential_names
    assert len(parallel_names) == _FILE_COUNT


def test_directory_scan_is_sequential_by_default(tmp_path: Path) -> None:
    _, symbol_server = _scan(tmp_path, parallel_requests=1)

    assert symbol_server.max_running == 1


def test_file_without_symbols_is_requested_once_in_a_parallel_scan(tmp_path: Path) -> None:
    symbol_server = _SlowSymbolServer(files_without_symbols=frozenset({"module_2"}))

    symbol_names, _ = _scan(tmp_path, parallel_requests=4, symbol_server=symbol_server)

    assert symbol_server.requests_per_file["module_2"] == 1
    assert "module_2" not in symbol_names
    assert len(symbol_names) == _FILE_COUNT - 1


def test_file_whose_parallel_request_failed_is_requested_again(tmp_path: Path) -> None:
    symbol_server = _SlowSymbolServer(files_failing_once=frozenset({"module_3"}))

    symbol_names, _ = _scan(tmp_path, parallel_requests=4, symbol_server=symbol_server)

    assert symbol_server.requests_per_file["module_3"] == 2
    assert "module_3" in symbol_names


def test_parallel_requests_run_in_the_callers_context(tmp_path: Path) -> None:
    symbol_server = _SlowSymbolServer()
    token = _CALLER_CONTEXT.set("scanning tool call")
    try:
        _scan(tmp_path, parallel_requests=4, symbol_server=symbol_server)
    finally:
        _CALLER_CONTEXT.reset(token)

    assert symbol_server.caller_contexts == ["scanning tool call"] * _FILE_COUNT
