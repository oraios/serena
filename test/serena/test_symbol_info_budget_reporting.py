import json
import logging
from unittest.mock import MagicMock

import pytest

from serena.project import Project
from serena.symbol import LanguageServerSymbol, LanguageServerSymbolRetriever
from serena.tools.symbol_tools import FindSymbolTool
from solidlsp.ls_types import SymbolKind


@pytest.mark.parametrize("budget", [0.0, 10.0, 0.5], ids=["unlimited", "within-budget", "exhausted-budget"])
def test_find_symbol_distinguishes_budget_skip_from_missing_info(
    budget: float, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """Budget-skipped information must be distinguishable in the user-visible tool result."""
    # provide two symbols through the discovery boundary
    symbols = []
    for line, name in enumerate(["documented", "undocumented"]):
        span = {"start": {"line": line, "character": 0}, "end": {"line": line, "character": 12}}
        symbols.append(
            LanguageServerSymbol(
                {
                    "name": name,
                    "kind": SymbolKind.Function,
                    "location": {
                        "relativePath": "example.py",
                        "absolutePath": "C:/example.py",
                        "uri": "file:///C:/example.py",
                        "range": span,
                    },
                    "selectionRange": span,
                    "children": [],
                    "parent": None,
                }
            )
        )
    monkeypatch.setattr(LanguageServerSymbolRetriever, "find", lambda *args, **kwargs: symbols)

    # emulate hover responses and elapsed time without starting a language server
    project = MagicMock(spec=Project)
    project.serena_config = MagicMock(symbol_info_budget=0.0)
    project.project_config = MagicMock(symbol_info_budget=None)
    server = project.get_language_server_manager_or_raise.return_value.get_language_server.return_value
    elapsed = 0.0

    def request_hover(*, relative_file_path, line, column, file_buffer):
        nonlocal elapsed
        elapsed += 1.0
        return {"contents": "Documented function"} if line == 0 else None

    server.request_hover.side_effect = request_hover
    monkeypatch.setattr("serena.symbol.perf_counter", lambda: elapsed)
    agent = MagicMock()
    agent.get_active_project_or_raise.return_value = project
    tool = FindSymbolTool(agent)

    # obtain a reference result where both symbols were actually queried
    missing_info_result = tool.apply("", include_info=True, max_answer_chars=10000)
    assert server.request_hover.call_count == 2
    assert "Documented function" in missing_info_result
    assert "undocumented" in missing_info_result

    # compare the same tool output with the configured budget
    server.request_hover.reset_mock()
    project.serena_config.symbol_info_budget = budget
    caplog.set_level(logging.INFO, logger="serena.symbol")
    result = tool.apply("", include_info=True, max_answer_chars=10000)
    if budget == 0.5:
        assert server.request_hover.call_count == 1
        assert result != missing_info_result, (
            "find_symbol returned identical output for budget-skipped info and genuinely missing info: " + result
        )
        note, _, json_part = result.partition("\n")
        assert note == "Note: symbol_info_budget exhausted; info omitted for 1 symbol(s)."
        output = json.loads(json_part)
        assert output[0]["info"] == "Documented function"
        assert "info" not in output[1]
        assert "Skipped information for 1 symbols because symbol_info_budget was exhausted" in caplog.text
    else:
        assert server.request_hover.call_count == 2
        assert result == missing_info_result
