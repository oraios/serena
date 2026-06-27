from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from solidlsp.language_servers.omnisharp import OmniSharp


class _NoWaitEvent:
    def is_set(self) -> bool:
        return False

    def wait(self, timeout: float | None = None) -> bool:
        raise AssertionError("OmniSharp startup must not wait for dynamic capability registration")


@pytest.mark.csharp
def test_omnisharp_startup_does_not_wait_for_capability_registration(tmp_path: Path) -> None:
    omnisharp = OmniSharp.__new__(OmniSharp)
    omnisharp.repository_root_path = str(tmp_path)
    omnisharp.server = SimpleNamespace(
        send=SimpleNamespace(initialize=lambda _params: {"capabilities": {}}),
        notify=SimpleNamespace(initialized=lambda _params: None, workspace_did_change_configuration=lambda _params: None),
        on_request=lambda *_args: None,
        on_notification=lambda *_args: None,
        start=lambda: None,
    )
    omnisharp.server_ready = _NoWaitEvent()
    omnisharp.definition_available = _NoWaitEvent()
    omnisharp.references_available = _NoWaitEvent()
    omnisharp.completions_available = _NoWaitEvent()

    omnisharp._start_server()
