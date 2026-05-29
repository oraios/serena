"""Tests for QueryProjectTool forwarding gates.

These tests run fully in-process with no language server: ``search_for_pattern`` is
non-symbolic and read-only, so ``_is_project_server_required`` returns ``False`` and the
tool executes via ``active_project_context`` without starting a language server.
"""

import json
import logging
from collections.abc import Callable, Iterator, Sequence

import pytest

from serena.agent import SerenaAgent
from serena.config.context_mode import SerenaAgentContext
from serena.config.serena_config import ProjectConfig, RegisteredProject, SerenaConfig
from serena.project import Project
from serena.tools.query_project_tools import QueryProjectTool
from solidlsp.ls_config import Language
from test.conftest import get_repo_path

PROJECT_NAME = "test_repo_python"


def _make_agent(
    context_excluded: Sequence[str] = (),
    global_excluded: Sequence[str] = (),
) -> SerenaAgent:
    config = SerenaConfig(gui_log_window=False, web_dashboard=False, log_level=logging.ERROR)
    config.excluded_tools = list(global_excluded)

    repo_path = get_repo_path(Language.PYTHON)
    project = Project(
        project_root=str(repo_path),
        project_config=ProjectConfig(
            project_name=PROJECT_NAME,
            languages=[Language.PYTHON],
            ignored_paths=[],
            excluded_tools=[],
            read_only=False,
            ignore_all_files_in_gitignore=True,
            initial_prompt="",
            encoding="utf-8",
        ),
        serena_config=config,
    )
    config.projects = [RegisteredProject.from_project_instance(project)]

    context = SerenaAgentContext(name="test-query-project", prompt="", excluded_tools=list(context_excluded))
    # no project activated at startup -> no language server is started
    return SerenaAgent(serena_config=config, context=context)


@pytest.fixture
def agent_factory() -> Iterator[Callable[..., SerenaAgent]]:
    created: list[SerenaAgent] = []

    def make(**kwargs: Sequence[str]) -> SerenaAgent:
        agent = _make_agent(**kwargs)
        created.append(agent)
        return agent

    yield make
    for agent in created:
        agent.on_shutdown(timeout=5)


def _forward(agent: SerenaAgent, tool_name: str, params: dict | None = None) -> str:
    tool = agent.get_tool(QueryProjectTool)
    return tool.apply(
        project_name=PROJECT_NAME,
        tool_name=tool_name,
        tool_params_json=json.dumps(params or {}),
    )


class TestQueryProjectForwardingGate:
    def test_context_excluded_readonly_tool_is_forwardable(self, agent_factory) -> None:
        """A read-only tool excluded only by the current context must still be forwardable."""
        agent = agent_factory(context_excluded=["search_for_pattern"])
        result = _forward(
            agent,
            "search_for_pattern",
            {"substring_pattern": "def ", "restrict_search_to_code_files": False},
        )
        matches = json.loads(result)
        assert matches, f"Expected non-empty search results, got: {result!r}"

    def test_non_readonly_tool_is_blocked(self, agent_factory) -> None:
        """A non-read-only tool must never be forwarded.

        Pinned to ``ValueError`` (not ``AssertionError``): accepting ``AssertionError`` would
        let a regression back to ``assert`` pass silently -- and ``assert`` can be stripped
        by ``python -O``, which is precisely the failure mode this gate guards against.
        """
        agent = agent_factory()
        with pytest.raises(ValueError, match="read-only"):
            _forward(agent, "create_text_file")

    def test_globally_excluded_tool_is_blocked(self, agent_factory) -> None:
        """A tool disabled in the global Serena configuration must remain blocked. Pinned to
        ``ValueError`` for the same reason as :meth:`test_non_readonly_tool_is_blocked`.
        """
        agent = agent_factory(global_excluded=["search_for_pattern"])
        with pytest.raises(ValueError, match="global"):
            _forward(
                agent,
                "search_for_pattern",
                {"substring_pattern": "def ", "restrict_search_to_code_files": False},
            )

    def test_unregistered_project_is_rejected(self, agent_factory) -> None:
        """Forwarding to a project the caller has not registered must raise ``ValueError``."""
        agent = agent_factory()
        tool = agent.get_tool(QueryProjectTool)
        with pytest.raises(ValueError, match="not registered"):
            tool.apply(
                project_name="no_such_project",
                tool_name="search_for_pattern",
                tool_params_json=json.dumps({"substring_pattern": "def "}),
            )
