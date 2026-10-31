# SPDX-License-Identifier: GPL-3.0-or-later
"""Vue implementation navigation through the public Serena tool."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from serena.agent import SerenaAgent
from serena.config.serena_config import ProjectConfig, RegisteredProject
from serena.project import Project
from serena.tools.symbol_tools import FindImplementationsTool
from solidlsp.ls_config import LanguageServerId
from test.conftest import create_default_serena_config, get_repo_path

pytestmark = pytest.mark.vue


@pytest.fixture(scope="module")
def vue_agent() -> Iterator[SerenaAgent]:
    config = create_default_serena_config()
    project = Project(
        project_root=str(get_repo_path(LanguageServerId.VUE)),
        project_config=ProjectConfig(project_name="vue_implementations", language_servers=[LanguageServerId.VUE]),
        serena_config=config,
    )
    config.projects = [RegisteredProject.from_project_instance(project)]
    agent = SerenaAgent(project="vue_implementations", serena_config=config)
    try:
        agent.execute_task(lambda: None)
        yield agent
    finally:
        agent.on_shutdown()


def test_find_implementations_returns_classes_and_source_ranges(vue_agent: SerenaAgent) -> None:
    implementations = json.loads(
        vue_agent.get_tool(FindImplementationsTool).apply(
            name_path="Shape",
            relative_path="src/types/implementation_sample.ts",
        )
    )
    assert {(item["name_path"], Path(item["relative_path"]).as_posix()) for item in implementations} == {
        ("Square", "src/types/implementation_sample.ts"),
        ("Circle", "src/types/implementation_other.ts"),
    }
    for item in implementations:
        assert item["kind"] == "Class"
        source_lines = (get_repo_path(LanguageServerId.VUE) / item["relative_path"]).read_text(encoding="utf-8").splitlines()
        assert f"class {item['name_path']} implements Shape" in source_lines[item["body_location"]["start_line"]]
        assert item["body_location"]["end_line"] > item["body_location"]["start_line"]


def test_find_implementations_returns_empty_for_unimplemented_interface(vue_agent: SerenaAgent) -> None:
    result = vue_agent.get_tool(FindImplementationsTool).apply(
        name_path="UnimplementedShape",
        relative_path="src/types/implementation_sample.ts",
    )
    assert json.loads(result) == []
