import json
from pathlib import Path

from serena.agent import FindSymbolTool, SerenaAgent, SerenaConfigBase


class TestConfig(SerenaConfigBase):
    gui_log_window_enabled: bool = False
    web_dashboard: bool = False


def test_find_symbol_across_languages():
    repo = Path("test/resources/repos/multi/test_repo")
    agent = SerenaAgent(project=str(repo), serena_config=TestConfig())
    tool = agent.get_tool(FindSymbolTool)
    result = json.loads(tool.apply("func", substring_matching=True))
    paths = {s["relative_path"] for s in result}
    assert "py_mod.py" in paths
    assert "ts_mod.ts" in paths

    result_py = json.loads(tool.apply("py_func", language="python"))
    assert any(r["relative_path"] == "py_mod.py" for r in result_py)
    result_ts = json.loads(tool.apply("ts_func", language="typescript"))
    assert any(r["relative_path"] == "ts_mod.ts" for r in result_ts)
