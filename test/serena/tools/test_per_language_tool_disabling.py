"""Tests for the runtime behaviour of per-language tool disabling.

* Behaviour 1 (refuse): a pinned-file tool call targeting an excluded-language file is refused
  before the tool body executes; a call targeting a non-excluded file proceeds.
* Behaviour 3 (no-op): language-agnostic tools are never refused.

The guard logic (``Tool.get_target_relative_paths`` / ``Tool._check_language_exclusion``) is exercised
directly via a lightweight fake agent so the tests are deterministic and do not require a running
language server. An end-to-end test through ``apply_ex`` validates the wiring.
"""

import logging
import os
from pathlib import Path

import pytest

from serena.config.serena_config import ProjectConfig
from serena.project import Project
from serena.tools import Tool
from serena.tools.memory_tools import ReadMemoryTool
from serena.tools.symbol_tools import ReplaceSymbolBodyTool
from solidlsp.ls_config import Language
from test.conftest import create_default_serena_config, get_repo_path


class _FakeAgent:
    """Minimal agent stub exposing only what the per-language guard needs."""

    def __init__(self, project: Project):
        self._project = project
        self.serena_config = project.serena_config

    def get_active_project(self) -> Project | None:
        return self._project

    def get_active_project_or_raise(self) -> Project:
        return self._project

    def tool_is_active(self, tool_name: str) -> bool:
        return True


def _make_python_project(excluded: dict[Language, list[str]]) -> Project:
    repo_path = str(get_repo_path(Language.PYTHON))
    project_config = ProjectConfig(
        project_name="test_repo",
        languages=[Language.PYTHON],
        excluded_tools_by_language=excluded,
    )
    return Project(
        project_root=repo_path,
        project_config=project_config,
        serena_config=create_default_serena_config(),
    )


def _make_tool(tool_cls: type[Tool], project: Project) -> Tool:
    return tool_cls(_FakeAgent(project))  # type: ignore[arg-type]


class TestGetTargetRelativePaths:
    def test_returns_pinned_existing_file(self):
        project = _make_python_project({})
        tool = _make_tool(ReplaceSymbolBodyTool, project)
        rp = os.path.join("test_repo", "models.py")
        assert tool.get_target_relative_paths({"relative_path": rp}) == [rp]

    def test_returns_none_for_empty_path(self):
        project = _make_python_project({})
        tool = _make_tool(ReplaceSymbolBodyTool, project)
        assert tool.get_target_relative_paths({"relative_path": ""}) is None
        assert tool.get_target_relative_paths({}) is None

    def test_returns_none_for_directory(self):
        project = _make_python_project({})
        tool = _make_tool(ReplaceSymbolBodyTool, project)
        assert tool.get_target_relative_paths({"relative_path": "test_repo"}) is None

    def test_returns_none_for_nonexistent_file(self):
        project = _make_python_project({})
        tool = _make_tool(ReplaceSymbolBodyTool, project)
        assert tool.get_target_relative_paths({"relative_path": "does_not_exist.py"}) is None


class TestRefuseGuard:
    def test_refuses_pinned_excluded_language_file(self):
        project = _make_python_project({Language.PYTHON: ["replace_symbol_body"]})
        tool = _make_tool(ReplaceSymbolBodyTool, project)
        rp = os.path.join("test_repo", "models.py")
        msg = tool._check_language_exclusion({"relative_path": rp})
        assert msg is not None
        assert "disabled for python" in msg
        assert rp in msg

    def test_does_not_refuse_when_tool_not_excluded(self):
        project = _make_python_project({Language.PYTHON: ["find_symbol"]})
        tool = _make_tool(ReplaceSymbolBodyTool, project)
        rp = os.path.join("test_repo", "models.py")
        assert tool._check_language_exclusion({"relative_path": rp}) is None

    def test_does_not_refuse_file_of_other_language(self):
        # tool is disabled for haxe, but the pinned file is a python file -> not refused
        project = ProjectConfig(
            project_name="test_repo",
            languages=[Language.PYTHON, Language.HAXE],
            excluded_tools_by_language={Language.HAXE: ["replace_symbol_body"]},
        )
        proj = Project(
            project_root=str(get_repo_path(Language.PYTHON)),
            project_config=project,
            serena_config=create_default_serena_config(),
        )
        tool = _make_tool(ReplaceSymbolBodyTool, proj)
        rp = os.path.join("test_repo", "models.py")
        assert tool._check_language_exclusion({"relative_path": rp}) is None

    def test_no_active_project_is_noop(self):
        project = _make_python_project({Language.PYTHON: ["replace_symbol_body"]})
        tool = _make_tool(ReplaceSymbolBodyTool, project)
        # simulate no active project
        tool.agent._project = None  # type: ignore[attr-defined]
        assert tool._check_language_exclusion({"relative_path": "test_repo/models.py"}) is None

    def test_language_agnostic_tool_is_noop(self):
        # read_memory is configured but it does not target files -> guard never fires
        project = _make_python_project({Language.PYTHON: ["read_memory"]})
        tool = _make_tool(ReadMemoryTool, project)
        assert tool._check_language_exclusion({"memory_name": "anything"}) is None


@pytest.mark.python
class TestRefuseGuardEndToEnd:
    """End-to-end test through ``apply_ex`` using a real agent (validates the wiring)."""

    def test_apply_ex_refuses_without_executing(self):
        from serena.agent import SerenaAgent
        from serena.config.serena_config import RegisteredProject, SerenaConfig

        config = SerenaConfig(gui_log_window=False, web_dashboard=False, log_level=logging.ERROR)
        project = Project(
            project_root=str(get_repo_path(Language.PYTHON)),
            project_config=ProjectConfig(
                project_name="excl_test_repo",
                languages=[Language.PYTHON],
                excluded_tools_by_language={Language.PYTHON: ["replace_symbol_body"]},
            ),
            serena_config=config,
        )
        config.projects = [RegisteredProject.from_project_instance(project)]
        agent = SerenaAgent(project="excl_test_repo", serena_config=config)
        try:
            agent.execute_task(lambda: None)
            tool = agent.get_tool(ReplaceSymbolBodyTool)
            rp = str(Path("test_repo") / "models.py")
            # this must be refused BEFORE the LSP-backed edit is attempted; if the edit ran,
            # the (empty) body replacement would either error differently or mutate the file.
            result = tool.apply_ex(log_call=False, relative_path=rp, name_path="BaseModel", body="# replaced")
            assert "disabled for python" in result
            # the file must be unchanged (the edit must not have executed)
            assert "# replaced" not in project.read_file(rp)
        finally:
            agent.on_shutdown(timeout=10)
