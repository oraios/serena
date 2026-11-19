import shutil

import pytest

from solidlsp.language_servers.elixir_tools.elixir_tools import ElixirTools

pytestmark = pytest.mark.elixir


@pytest.mark.skipif(shutil.which("elixir") is None, reason="Elixir is not installed")
def test_elixir_version_is_detected() -> None:
    version = ElixirTools._get_elixir_version()

    assert version is not None
    assert "Elixir" in version
