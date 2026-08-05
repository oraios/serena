import pytest

from serena.dashboard import SerenaDashboardAPI


@pytest.fixture(autouse=True)
def disable_dashboard_background_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    SerenaDashboardAPI queries GitHub (news) and PyPI (newer version check) from background threads
    on construction. Tests must not depend on network access, so disable both; a test that needs
    either result should set the corresponding attribute on the instance directly.
    """
    monkeypatch.setattr(SerenaDashboardAPI, "_fetch_news", lambda self: None)
    monkeypatch.setattr(SerenaDashboardAPI, "_determine_newer_serena_version", lambda self: None)
