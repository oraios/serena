# SPDX-License-Identifier: MIT
"""Implementation-query guarantees at the Vue companion-service boundary."""

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

from solidlsp.language_servers.vue_language_server import VueLanguageServer, VueTypeScriptServer
from solidlsp.ls_exceptions import SolidLSPException


@pytest.mark.parametrize("relative_path", ["src/shapes.ts", "src/Shapes.vue"])
@pytest.mark.parametrize("outcome", ["locations", "empty", "error"])
def test_implementation_query_uses_open_companion_file(relative_path: str, outcome: str, monkeypatch: pytest.MonkeyPatch) -> None:
    server = object.__new__(VueLanguageServer)
    companion = Mock(spec=VueTypeScriptServer)
    server._ts_server = companion
    ready = False
    opened = False
    closed = False
    expected = (
        []
        if outcome == "empty"
        else [
            {
                "uri": "file:///project/src/shapes.ts",
                "relativePath": "src/shapes.ts",
                "range": {"start": {"line": 4, "character": 13}, "end": {"line": 4, "character": 19}},
            }
        ]
    )
    failure = SolidLSPException("companion implementation query failed")

    def ensure_ready() -> None:
        nonlocal ready
        ready = True

    @contextmanager
    def open_file(path: str) -> Iterator[None]:
        nonlocal opened, closed
        assert ready
        assert path == relative_path
        opened = True
        try:
            yield
        finally:
            opened = False
            closed = True

    def query(path: str, line: int, column: int):
        assert ready and opened
        assert (path, line, column) == (relative_path, 3, 17)
        if outcome == "error":
            raise failure
        return expected

    monkeypatch.setattr(server, "_ensure_ls_operational", ensure_ready)
    companion.open_file.side_effect = open_file
    companion.request_implementation.side_effect = query

    if outcome == "error":
        with pytest.raises(SolidLSPException) as exc_info:
            server.request_implementation(relative_path, 3, 17)
        assert exc_info.value is failure
    else:
        assert server.request_implementation(relative_path, 3, 17) is expected
    assert closed and not opened


def test_implementation_query_preserves_readiness_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    server = object.__new__(VueLanguageServer)
    failure = SolidLSPException("Language Server not started")
    monkeypatch.setattr(server, "_ensure_ls_operational", Mock(side_effect=failure))
    with pytest.raises(SolidLSPException) as exc_info:
        server.request_implementation("src/shapes.ts", 0, 17)
    assert exc_info.value is failure


def test_vue_advertises_implementation_support() -> None:
    assert VueLanguageServer.supports_implementation_request()
