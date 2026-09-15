from unittest.mock import MagicMock

from solidlsp.ls import SolidLanguageServer


class DummyWarmCacheLanguageServer(SolidLanguageServer):
    def _start_server(self) -> None:
        raise AssertionError("Not used in this test")

    def _create_base_initialize_params(self) -> dict:
        return {}


def _make_server(tmp_path) -> tuple[SolidLanguageServer, list[str], MagicMock]:
    """Creates a minimal SolidLanguageServer with mocked LSP notifications, wired for open_file().

    :return: tuple of (server, events list, the notify mock)
    """
    events: list[str] = []

    notify = MagicMock()
    notify.did_open_text_document.side_effect = lambda *_a, **_kw: events.append("didOpen")
    notify.did_change_text_document.side_effect = lambda *_a, **_kw: events.append("didChange")
    notify.did_close_text_document.side_effect = lambda *_a, **_kw: events.append("didClose")

    server = MagicMock()
    server.notify = notify
    server.is_running.return_value = True

    language_server = object.__new__(DummyWarmCacheLanguageServer)
    # bypass abstract __init__: set only what open_file() and stop() need
    language_server.ls_id = "python"
    language_server.repository_root_path = str(tmp_path)
    language_server.server_started = True
    language_server.open_file_buffers = {}
    language_server._warm_file_buffers = {}
    language_server._warm_buffer_ttl = 0.05
    language_server._encoding = "utf-8"
    language_server.language_id = "python"
    language_server.server = server
    language_server._path_contains_dots = lambda _p: False
    return language_server, events, server


def test_open_close_reopen_within_ttl_avoids_didopen(tmp_path) -> None:
    """Reopening a recently closed file within the TTL must not send another didOpen:
    the warm buffer keeps the LSP document open and the reopen sends nothing (mtime unchanged).
    """
    (tmp_path / "sample.py").write_text("x = 1\n", encoding="utf-8")
    server, events, _ = _make_server(tmp_path)

    with server.open_file("sample.py"):
        pass  # open -> close moves the buffer to the warm cache
    assert events == ["didOpen"]  # no didClose yet: buffer is warm

    with server.open_file("sample.py"):
        pass  # reopen within TTL: warm buffer reused, no notification
    assert events == ["didOpen"]  # still no didClose and no second didOpen

    # TTL expiry triggers the deferred didClose
    import time as _time

    _time.sleep(0.08)
    with server.open_file("other.py" if False else "sample.py"):
        pass
    assert events.count("didClose") == 1  # evicted by TTL on next open
    assert events.count("didOpen") == 2  # fresh didOpen after eviction


def test_reopen_after_disk_change_sends_didchange_not_didopen(tmp_path) -> None:
    """A warm buffer whose file changed on disk is reused and updated via didChange."""
    file_path = tmp_path / "sample.py"
    file_path.write_text("x = 1\n", encoding="utf-8")
    server, events, _ = _make_server(tmp_path)

    with server.open_file("sample.py"):
        pass
    file_path.write_text("x = 2\n", encoding="utf-8")  # external change while warm
    import os as _os

    _os.utime(file_path, (0, 0))  # force a distinct mtime (guaranteed > previous monotonic-ish value? no: 0 < prev)
    # ensure mtime actually differs (bump by rewriting, stat resolution dependent)
    with open(file_path, "a", encoding="utf-8") as f:
        f.write("y = 3\n")
    import os as _os2

    future = _os2.stat(file_path).st_mtime + 2.0
    _os2.utime(file_path, (future, future))

    with server.open_file("sample.py"):
        pass
    assert "didChange" in events
    assert events.count("didOpen") == 1  # still only one didOpen
    assert "didClose" not in events


def test_invalidate_warm_buffer_forces_fresh_didopen(tmp_path) -> None:
    """invalidate_warm_buffer() (external change path) evicts the buffer, so the next open sends didClose+didOpen."""
    file_path = tmp_path / "sample.py"
    file_path.write_text("x = 1\n", encoding="utf-8")
    server, events, _ = _make_server(tmp_path)

    with server.open_file("sample.py"):
        pass
    assert server._warm_file_buffers  # buffer is warm

    server.invalidate_warm_buffer("sample.py")
    assert not server._warm_file_buffers
    assert events == ["didOpen", "didClose"]  # invalidation closes the LSP document

    with server.open_file("sample.py"):
        pass
    assert events == ["didOpen", "didClose", "didOpen"]  # fresh full cycle


def test_close_all_warm_buffers_on_stop(tmp_path) -> None:
    """stop() must close every warm buffer so no stale documents remain open in the LS."""
    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b = 2\n", encoding="utf-8")
    server, events, _ = _make_server(tmp_path)

    with server.open_file("a.py"):
        pass
    with server.open_file("b.py"):
        pass
    assert events == ["didOpen", "didOpen"]
    assert len(server._warm_file_buffers) == 2

    stop_calls: list[dict] = []
    server.server.stop.side_effect = lambda *a, **kw: stop_calls.append({})
    server.stop(shutdown_timeout=2.0)

    assert not server._warm_file_buffers
    assert events.count("didClose") == 2


def test_warm_buffer_ttl_is_lazy_evicted(tmp_path) -> None:
    """Expired warm buffers are closed lazily: on the next open_file call after TTL."""
    file_path = tmp_path / "sample.py"
    file_path.write_text("x = 1\n", encoding="utf-8")
    server, events, _ = _make_server(tmp_path)

    with server.open_file("sample.py"):
        pass
    assert events == ["didOpen"]

    import time as _time

    _time.sleep(0.08)
    assert events.count("didClose") == 0  # not yet evicted

    with server.open_file("sample.py"):
        pass
    # eviction happened during the next open_file: old buffer closed, new one opened
    assert events.count("didClose") == 1
    assert events.count("didOpen") == 2
