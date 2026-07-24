"""Tests for the ``SearchForPatternTool`` overflow shortening chain.

The snippet stage and, in particular, its position in the shortening chain were
previously untested. Test contributed by @AmirF194 in review of PR #1667.
"""

from unittest.mock import MagicMock

from serena.config.serena_config import SerenaConfig
from serena.project import Project
from serena.tools.file_tools import SearchForPatternTool


def make_search_tool(tmp_path) -> SearchForPatternTool:
    serena_config = SerenaConfig(gui_log_window=False, web_dashboard=False)
    project = Project.load(str(tmp_path), serena_config=serena_config)
    agent = MagicMock()
    agent.serena_config = serena_config
    agent.get_active_project_or_raise.return_value = project
    return SearchForPatternTool(agent)


def test_search_for_pattern_multiple_exclusion_globs_are_additive(tmp_path):
    paths = [
        "plugins/feature-pipeline/SKILL.md",
        "docs/superpowers/plans/archive.md",
        "docs/superpowers/specs/archive.md",
        "src/generated/cache.py",
    ]
    for path in paths:
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("feature-pipeline\n", encoding="utf-8")

    tool = make_search_tool(tmp_path)

    singular_result = tool.apply(
        substring_pattern="feature-pipeline",
        paths_exclude_glob="**/generated/**",
    )
    assert "plugins/feature-pipeline/SKILL.md" in singular_result
    assert "docs/superpowers/plans/archive.md" in singular_result
    assert "src/generated/cache.py" not in singular_result

    additive_result = tool.apply(
        substring_pattern="feature-pipeline",
        paths_exclude_glob="**/generated/**",
        paths_exclude_globs=[
            "docs/superpowers/plans/**",
            "docs/superpowers/specs/**",
        ],
    )
    assert "plugins/feature-pipeline/SKILL.md" in additive_result
    assert "docs/superpowers" not in additive_result
    assert "src/generated/cache.py" not in additive_result


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

    tool = make_search_tool(tmp_path)

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
