"""
Tests for the configuration facade API.
"""

from unittest.mock import MagicMock

from serena.repl.api.cfg_api import ConfigApi
from serena.repl.facade import ApiScope, Facade


def test_facade_exposes_config_operations() -> None:
    facade = Facade.from_api(ConfigApi(MagicMock()), ApiScope())
    assert facade.name == "cfg"
    assert set(facade.enabled_method_names) == {"get_current_config", "open_dashboard"}
    assert not any(facade.get_method(name).info.can_edit for name in facade.enabled_method_names)


def test_operations_delegate_to_agent() -> None:
    agent = MagicMock()
    agent.get_current_config_overview.return_value = "overview"
    agent.open_dashboard.return_value = False
    agent.get_dashboard_url.return_value = "http://localhost:1"
    api = ConfigApi(agent)
    assert api.get_current_config() == "overview"
    assert "http://localhost:1" in api.open_dashboard()
