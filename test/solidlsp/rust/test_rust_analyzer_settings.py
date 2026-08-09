from contextlib import nullcontext
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.language_servers.rust_analyzer import RustAnalyzer

pytestmark = pytest.mark.rust


def _make_server() -> RustAnalyzer:
    return object.__new__(RustAnalyzer)


def test_initialization_uses_lightweight_indexing_settings() -> None:
    initialization_options = _make_server()._create_base_initialize_params()["initializationOptions"]

    assert initialization_options["cachePriming"]["enable"] is False
    assert initialization_options["checkOnSave"] is True


@pytest.mark.parametrize("pull_diagnostics_failed", [False, True])
def test_published_diagnostics_wait_has_eight_second_minimum(pull_diagnostics_failed: bool) -> None:
    assert _make_server()._get_published_diagnostics_wait_timeout(pull_diagnostics_failed) == 8.0


def test_published_diagnostics_wait_preserves_larger_base_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def wider_base_timeout(_server: SolidLanguageServer, _pull_diagnostics_failed: bool) -> float:
        return 12.0

    monkeypatch.setattr(SolidLanguageServer, "_get_published_diagnostics_wait_timeout", wider_base_timeout)

    assert _make_server()._get_published_diagnostics_wait_timeout(False) == 12.0


def test_diagnostics_request_triggers_check_on_save(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _make_server()
    server_interface = MagicMock()
    server.server = cast(Any, server_interface)
    uri = "file:///workspace/src/lib.rs"

    monkeypatch.setattr(server, "_validate_text_document_diagnostics_request", lambda *_args: uri)
    monkeypatch.setattr(server, "open_file", lambda _relative_file_path: nullcontext())
    monkeypatch.setattr(SolidLanguageServer, "request_text_document_diagnostics", lambda *_args, **_kwargs: [])

    assert server.request_text_document_diagnostics("src/lib.rs") == []
    server_interface.notify.did_save_text_document.assert_called_once_with({"textDocument": {"uri": uri}})
