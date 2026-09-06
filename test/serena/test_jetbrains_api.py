"""
Tests for the JetBrains facade API, using a mocked plugin client (no IDE required).
"""

from unittest.mock import MagicMock, patch

import pytest

from serena.facades.api.jb import JetBrainsApi
from serena.facades.facade import Facade


@pytest.fixture
def agent() -> MagicMock:
    agent = MagicMock()
    agent.serena_config.default_max_tool_answer_chars = 10000
    return agent


@pytest.fixture
def client() -> MagicMock:
    client = MagicMock()
    with patch("serena.facades.api.jb.JetBrainsPluginClient.from_project") as from_project:
        from_project.return_value.__enter__.return_value = client
        yield client


def test_facade_exposes_all_jetbrains_operations(agent: MagicMock) -> None:
    facade = Facade.from_api(JetBrainsApi(agent))
    assert facade.name == "jb"
    assert set(facade.enabled_method_names) == {
        "find_symbol",
        "find_referencing_symbols",
        "get_symbols_overview",
        "get_type_hierarchy",
        "find_declaration",
        "find_implementations",
        "rename",
        "move",
        "safe_delete",
        "inline_symbol",
        "run_inspections",
        "list_inspections",
        "debug_eval",
        "debug_eval_info",
    }


def test_find_symbol_renders_grouped_and_exposes_symbols(agent: MagicMock, client: MagicMock) -> None:
    symbols = [
        {"name_path": "Foo", "type": "class", "relative_path": "a.py", "quick_info": "class Foo"},
        {"name_path": "Bar/foo", "type": "method", "relative_path": "b.py", "quick_info": "def foo()"},
    ]
    client.find_symbol.return_value = {"symbols": symbols}

    result = JetBrainsApi(agent).find_symbol("foo")

    # the underlying symbols are accessible from code
    assert [s["name_path"] for s in result.symbols] == ["Foo", "Bar/foo"]
    # and the rendering contains them, grouped by file
    rendered = result.represent()
    assert '"a.py"' in rendered and '"b.py"' in rendered
    assert "class Foo" in rendered


def test_find_symbol_rejects_too_many_matches_with_identifiers(agent: MagicMock, client: MagicMock) -> None:
    client.find_symbol.return_value = {
        "symbols": [{"name_path": f"foo{i}", "type": "function", "relative_path": "a.py", "body": "..."} for i in range(3)]
    }
    with pytest.raises(ValueError, match="Matched 3>max_matches=1") as exc_info:
        JetBrainsApi(agent).find_symbol("foo*", max_matches=1)
    assert "foo2" in str(exc_info.value)
    assert '"body"' not in str(exc_info.value)  # only identifiers, no content


def test_find_symbol_rejects_wildcard_only_pattern(agent: MagicMock, client: MagicMock) -> None:
    with pytest.raises(ValueError, match="get_symbols_overview"):
        JetBrainsApi(agent).find_symbol("*")
    client.find_symbol.assert_not_called()
