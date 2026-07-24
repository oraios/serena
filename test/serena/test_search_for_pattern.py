"""Tests for the ``SearchForPatternTool`` overflow shortening chain."""

import json
from unittest.mock import MagicMock

import pytest

from serena.config.serena_config import SerenaConfig
from serena.project import Project
from serena.tools.file_tools import SearchForPatternTool
from serena.util.text_utils import LineType, MatchedConsecutiveLines, TextLine


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


def test_search_for_pattern_ranked_excerpt_precedes_smaller_fallbacks(tmp_path):
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

    # wide but overflowing cap: whole ranked match entries retain their context
    ranked = run(7000)
    assert "The answer is too long" in ranked
    assert "Ranked match excerpt:" in ranked
    assert "MATCHME item number 0000" in ranked
    assert "filler above" in ranked
    assert "Showing " in ranked and "omitted " in ranked

    # exceptionally tight cap: the chain degrades past whole entries to a compact existing fallback
    compact = run(400)
    assert "Ranked match excerpt:" not in compact
    assert any(marker in compact for marker in ("Match lines per file:", "Match counts per file:", "Found 60 matches"))


def test_search_for_pattern_prioritizes_live_results_in_ranked_overflow_excerpt(tmp_path):
    for i in range(240):
        file = tmp_path / f"docs/superpowers/plans/archive-{i:03d}.md"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(f"feature-pipeline archived plan {i:03d} " + "payload " * 4 + "\n", encoding="utf-8")

    live_paths = [
        ".claude/skills/warden/SKILL.md",
        "config/warden/gaia.yaml",
        "scripts/warden-check.sh",
        "plugins/feature-pipeline/z-last.md",
        "plugins/feature-pipeline/a-first.md",
    ]
    for path in live_paths:
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        term = "feature-pipeline" if path.startswith("plugins/") else "Warden"
        content = (
            f"{term} first live candidate\n{term} second live candidate\n" if path.endswith("a-first.md") else f"{term} live candidate\n"
        )
        file.write_text(content, encoding="utf-8")

    tool = make_search_tool(tmp_path)
    discovered_matches = tool.project.search_project_files_for_pattern(
        pattern="feature-pipeline|Warden",
        paths_exclude_glob=".serena/**",
        code_files_only=False,
    )
    z_matches = [match for match in discovered_matches if match.source_file_path == "plugins/feature-pipeline/z-last.md"]
    a_matches = [match for match in discovered_matches if match.source_file_path == "plugins/feature-pipeline/a-first.md"]
    controlled_paths = {"plugins/feature-pipeline/z-last.md", "plugins/feature-pipeline/a-first.md"}
    other_matches = [match for match in discovered_matches if match.source_file_path not in controlled_paths]
    controlled_source_order = z_matches + list(reversed(a_matches)) + other_matches
    for match in controlled_source_order:
        assert match.source_file_path is not None
        match.source_file_path = match.source_file_path.replace("/", "\\")
    tool.project.search_project_files_for_pattern = MagicMock(return_value=controlled_source_order)
    expected_path_order = list(
        dict.fromkeys(match.source_file_path.replace("\\", "/") for match in controlled_source_order if match.source_file_path is not None)
    )

    prioritized = tool.apply(
        substring_pattern="feature-pipeline|Warden",
        paths_exclude_glob=".serena/**",
        paths_priority_globs=[
            "plugins/**",
            ".claude/skills/**",
            "config/**",
            "scripts/**",
        ],
        restrict_search_to_code_files=False,
        max_answer_chars=4_000,
    )

    assert "Ranked match excerpt:" in prioritized
    assert all(path in prioritized for path in live_paths)
    first_archive_index = prioritized.index("docs/superpowers/plans/archive-")
    assert prioritized.index("plugins/feature-pipeline/a-first.md") < prioritized.index("plugins/feature-pipeline/z-last.md")
    assert prioritized.index("0:feature-pipeline first live candidate") < prioritized.index("1:feature-pipeline second live candidate")
    assert prioritized.index("plugins/feature-pipeline/z-last.md") < prioritized.index(".claude/skills/warden/SKILL.md")
    assert prioritized.index(".claude/skills/warden/SKILL.md") < prioritized.index("config/warden/gaia.yaml")
    assert prioritized.index("config/warden/gaia.yaml") < prioritized.index("scripts/warden-check.sh")
    assert prioritized.index("scripts/warden-check.sh") < first_archive_index
    assert "Showing " in prioritized
    assert " of 246 matches across " in prioritized
    assert "omitted " in prioritized
    assert "refine the query for omitted results." in prioritized

    unprioritized = tool.apply(
        substring_pattern="feature-pipeline|Warden",
        paths_exclude_glob=".serena/**",
        restrict_search_to_code_files=False,
        max_answer_chars=100_000,
    )
    unprioritized_mapping = json.loads(unprioritized)
    assert list(unprioritized_mapping) == expected_path_order
    assert "1:feature-pipeline second live candidate" in unprioritized_mapping["plugins/feature-pipeline/a-first.md"][0]


def test_ranked_excerpt_serialization_count_does_not_grow_with_match_count(monkeypatch):
    matches = [
        MatchedConsecutiveLines(
            lines=[TextLine(line_number=0, line_content="x", match_type=LineType.MATCH)],
            source_file_path=f"archive/{i:05d}.md",
        )
        for i in range(20_000)
    ]
    serena_config = SerenaConfig(
        gui_log_window=False,
        web_dashboard=False,
        default_max_tool_answer_chars=150_000,
    )
    project = MagicMock()
    project.search_project_files_for_pattern.return_value = matches
    agent = MagicMock()
    agent.serena_config = serena_config
    agent.get_active_project_or_raise.return_value = project
    tool = SearchForPatternTool(agent)

    serialization_calls = 0
    serialize = tool._to_json

    def count_serialization_calls(value) -> str:
        nonlocal serialization_calls
        serialization_calls += 1
        if serialization_calls > 3:
            pytest.fail("ranked excerpt sizing must not repeatedly serialize growing prefixes")
        return serialize(value)

    monkeypatch.setattr(tool, "_to_json", count_serialization_calls)

    result = tool.apply(
        substring_pattern="x",
        paths_priority_globs=["plugins/**"],
    )

    assert "Ranked match excerpt:" in result
    assert serialization_calls == 2
