"""Tests for the communication channels of the per-language tool-disabling mechanism:

* Channel 2: the upfront summary injected into the project activation message
  (``SerenaAgent._format_excluded_tools_by_language_summary``).
* Channel 3: the per-language caveat appended to the tool description
  (``SerenaAgent.get_tool_description_override``).
"""

import logging

import pytest

from serena.agent import SerenaAgent
from serena.config.serena_config import ProjectConfig, RegisteredProject, SerenaConfig
from serena.project import Project
from solidlsp.ls_config import Language
from test.conftest import get_repo_path


class TestActivationSummary:
    def test_none_when_empty(self):
        config = ProjectConfig(project_name="p", languages=[Language.PYTHON])
        assert SerenaAgent._format_excluded_tools_by_language_summary(config) is None

    def test_summary_lists_languages_and_tools(self):
        config = ProjectConfig(
            project_name="p",
            languages=[Language.HAXE, Language.PYTHON],
            excluded_tools_by_language={
                Language.HAXE: ["find_symbol", "replace_symbol_body"],
                Language.PYTHON: ["replace_content"],
            },
        )
        summary = SerenaAgent._format_excluded_tools_by_language_summary(config)
        assert summary is not None
        assert "haxe → find_symbol, replace_symbol_body" in summary
        assert "python → replace_content" in summary
        assert "search_for_pattern" in summary  # mentions the recommended fallback

    def test_empty_tool_lists_yield_none(self):
        config = ProjectConfig(
            project_name="p",
            languages=[Language.HAXE],
            excluded_tools_by_language={Language.HAXE: []},
        )
        assert SerenaAgent._format_excluded_tools_by_language_summary(config) is None


@pytest.mark.python
class TestToolDescriptionCaveat:
    def _make_agent(self, excluded: dict[Language, list[str]]) -> SerenaAgent:
        config = SerenaConfig(gui_log_window=False, web_dashboard=False, log_level=logging.ERROR)
        project = Project(
            project_root=str(get_repo_path(Language.PYTHON)),
            project_config=ProjectConfig(
                project_name="comms_repo",
                languages=[Language.PYTHON],
                excluded_tools_by_language=excluded,
            ),
            serena_config=config,
        )
        config.projects = [RegisteredProject.from_project_instance(project)]
        agent = SerenaAgent(project="comms_repo", serena_config=config)
        agent.execute_task(lambda: None)
        return agent

    def test_caveat_added_for_excluded_tool(self):
        agent = self._make_agent({Language.PYTHON: ["find_symbol"]})
        try:
            override = agent.get_tool_description_override("find_symbol")
            assert override is not None
            assert "disabled for python" in override
        finally:
            agent.on_shutdown(timeout=10)

    def test_no_caveat_for_non_excluded_tool(self):
        agent = self._make_agent({Language.PYTHON: ["find_symbol"]})
        try:
            # search_for_pattern is not excluded; without a context override this should be None
            assert agent.get_tool_description_override("search_for_pattern") is None
        finally:
            agent.on_shutdown(timeout=10)

    def test_activation_message_contains_summary(self):
        agent = self._make_agent({Language.PYTHON: ["find_symbol"]})
        try:
            msg = agent.get_project_activation_message(session_id="test")
            assert "disabled per language" in msg
            assert "python → find_symbol" in msg
        finally:
            agent.on_shutdown(timeout=10)
