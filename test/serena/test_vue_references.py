# SPDX-License-Identifier: GPL-3.0-or-later
"""Component reverse references through the public Serena tool."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from serena.agent import SerenaAgent
from serena.config.serena_config import ProjectConfig, RegisteredProject
from serena.project import Project
from serena.tools.symbol_tools import FindReferencingSymbolsTool
from solidlsp.ls_config import LanguageServerId
from test.conftest import create_default_serena_config, get_repo_path

pytestmark = pytest.mark.vue


@pytest.fixture(scope="module")
def vue_agent() -> Iterator[SerenaAgent]:
    config = create_default_serena_config()
    project = Project(
        project_root=str(get_repo_path(LanguageServerId.VUE).parent / "component_references"),
        project_config=ProjectConfig(project_name="vue_references", language_servers=[LanguageServerId.VUE]),
        serena_config=config,
    )
    config.projects = [RegisteredProject.from_project_instance(project)]
    agent = SerenaAgent(project="vue_references", serena_config=config)
    try:
        agent.execute_task(lambda: None)
        yield agent
    finally:
        agent.on_shutdown()


def test_find_referencing_symbols_from_component(vue_agent: SerenaAgent) -> None:
    result = vue_agent.get_tool(FindReferencingSymbolsTool).apply(name_path="script setup", relative_path="src/components/Child.vue")
    references = {Path(path).as_posix(): groups for path, groups in json.loads(result).items()}
    assert set(references) == {"src/components/Parent.vue", "src/components/使用 方.vue"}, result
    for groups in references.values():
        symbols = [symbol for group in groups.values() for symbol in group]
        assert any(
            symbol["name_path"] == "script setup"
            and "import Child from './Child.vue'" in symbol["content_around_reference"]
            and ">   1:" in symbol["content_around_reference"]
            for symbol in symbols
        ), groups


def test_find_referencing_symbols_for_unused_component(vue_agent: SerenaAgent) -> None:
    result = vue_agent.get_tool(FindReferencingSymbolsTool).apply(name_path="script setup", relative_path="src/components/UnusedChild.vue")
    assert json.loads(result) == {}
