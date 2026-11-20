"""Tests for the ``SearchForPatternTool`` overflow shortening chain.

The snippet stage and, in particular, its position in the shortening chain were
previously untested. Test contributed by @AmirF194 in review of PR #1667.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from serena.config.serena_config import SerenaConfig
from serena.project import Project
from serena.tools.file_tools import SearchForPatternTool


def test_search_for_pattern_snippet_stage(tmp_path):
    lines: list[str] = []
    for i in range(60):
        lines += [
            "filler above",
            "filler above",
            f"MATCHME item number {i:04d} " + "payload " * 6,
            "filler below",
            "filler below",
        ]
    (tmp_path / "data.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    project = Project.load(str(tmp_path), serena_config=SerenaConfig(gui_log_window=False, web_dashboard=False))
    agent = MagicMock()
    agent.get_active_project_or_raise.return_value = project
    tool = SearchForPatternTool(agent)

    def run(cap: int) -> str:
        return tool.apply(
            substring_pattern="MATCHME",
            context_lines_before=2,
            context_lines_after=2,
            restrict_search_to_code_files=False,
            max_answer_chars=cap,
        )

    # wide but overflowing cap: the snippet stage (line + matched text) is returned
    snippet = run(7000)
    assert "The answer is too long" in snippet
    assert '"text":' in snippet and "MATCHME item number 0000" in snippet
    assert "Match lines per file" not in snippet  # not the bare-line-numbers stage

    # tighter cap: the chain degrades past the snippet stage to bare line numbers
    bare = run(1000)
    assert "Match lines per file" in bare and '"text":' not in bare


@pytest.mark.parametrize("ignore_source", ["gitignore", "config"])
def test_search_for_pattern_can_opt_into_single_ignored_file(tmp_path: Path, ignore_source: str) -> None:
    # create an ignored source file and a visible control
    for filename in ["ignored.py", "visible.py"]:
        (tmp_path / filename).write_text('message = "MATCHME"\n', encoding="utf-8")
    if ignore_source == "gitignore":
        (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    config = SerenaConfig(
        gui_log_window=False,
        web_dashboard=False,
        ignored_paths=["ignored.py"] if ignore_source == "config" else [],
    )
    project = Project.load(str(tmp_path), serena_config=config)
    agent = MagicMock()
    agent.get_active_project_or_raise.return_value = project
    agent.serena_config.default_max_tool_answer_chars = 10000
    tool = SearchForPatternTool(agent)

    # verify the opt-in through the public tool, preserving default and source-only filtering
    result = tool.apply("MATCHME", relative_path="ignored.py", skip_ignored_files=False)
    assert json.loads(result) == {"ignored.py": ['  >   0:message = "MATCHME"']}
    assert tool.apply("MATCHME", relative_path="ignored.py") == "{}"
    assert tool.apply("MATCHME", relative_path="ignored.py", skip_ignored_files=False, restrict_search_to_code_files=True) == "{}"
    assert set(json.loads(tool.apply("MATCHME", skip_ignored_files=False))) == {"ignored.py", "visible.py"}
    assert set(json.loads(tool.apply("MATCHME"))) == {"visible.py"}
