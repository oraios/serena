from types import SimpleNamespace
from unittest.mock import Mock

from solidlsp.language_servers.nextflow_language_server import NextflowLanguageServer


def _make_server(completion_side_effect=None) -> tuple[NextflowLanguageServer, Mock]:
    server = object.__new__(NextflowLanguageServer)
    server._workspace_scan_flushed = False
    server._resolve_file_uri = lambda relative_path: f"file:///{relative_path}"
    completion = Mock(side_effect=completion_side_effect)
    server.server = SimpleNamespace(send=SimpleNamespace(completion=completion))
    return server, completion


def test_flush_failure_does_not_mark_scan_as_flushed() -> None:
    server, completion = _make_server(RuntimeError("server is still starting"))

    server._flush_deferred_workspace_scan("main.nf")

    assert completion.call_count == 2
    assert server._workspace_scan_flushed is False


def test_flush_retries_after_previous_failure() -> None:
    server, completion = _make_server(RuntimeError("server is still starting"))

    server._flush_deferred_workspace_scan("main.nf")
    server._flush_deferred_workspace_scan("main.nf")

    assert completion.call_count == 4
    assert server._workspace_scan_flushed is False


def test_one_successful_flush_marks_scan_as_flushed() -> None:
    server, completion = _make_server([RuntimeError("temporary failure"), {}])

    server._flush_deferred_workspace_scan("main.nf")
    server._flush_deferred_workspace_scan("main.nf")

    assert completion.call_count == 2
    assert server._workspace_scan_flushed is True
