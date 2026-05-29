"""Tests for the single-project `activate_project` gate and the opt-in `enable_project_activation` override.

These verify that, in a single-project context (e.g. ``claude-code``), the ``activate_project`` tool is excluded by
default but can be kept available -- enabling runtime project switching within the session -- either per-launch via the
CLI flag (threaded as ``SerenaAgent(enable_project_activation=...)``) or by the context's ``allow_project_activation``
field. ``get_current_config`` stays excluded in every case. The tests exercise ``_create_base_toolset`` directly, so no
language server is started.
"""

import logging
import tempfile

from solidlsp.ls_config import Language

from serena.agent import ActiveModes, SerenaAgent
from serena.config.context_mode import SerenaAgentContext
from serena.config.serena_config import LanguageBackend, ProjectConfig, SerenaConfig
from serena.project import Project
from serena.tools import ActivateProjectTool, GetCurrentConfigTool

_ACTIVATE_PROJECT = ActivateProjectTool.get_name_from_cls()
_GET_CURRENT_CONFIG = GetCurrentConfigTool.get_name_from_cls()


def _make_config() -> SerenaConfig:
    return SerenaConfig(gui_log_window=False, web_dashboard=False, log_level=logging.ERROR)


def _make_project(config: SerenaConfig) -> Project:
    return Project(
        project_root=tempfile.mkdtemp(),
        project_config=ProjectConfig(
            project_name="test_single_project_activation",
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


def _toolset_names(context: SerenaAgentContext, project: Project | None, *, enable_project_activation: bool) -> set[str]:
    config = _make_config()
    toolset = SerenaAgent._create_base_toolset(
        config,
        LanguageBackend.LSP,
        context,
        ActiveModes(),
        project,
        enable_project_activation=enable_project_activation,
    )
    return toolset.get_tool_names()


def test_single_project_excludes_activate_project_by_default() -> None:
    context = SerenaAgentContext.from_name("claude-code")
    assert context.single_project is True
    assert context.allow_project_activation is False
    names = _toolset_names(context, _make_project(_make_config()), enable_project_activation=False)
    assert _ACTIVATE_PROJECT not in names
    assert _GET_CURRENT_CONFIG not in names


def test_cli_flag_keeps_activate_project_available() -> None:
    context = SerenaAgentContext.from_name("claude-code")
    names = _toolset_names(context, _make_project(_make_config()), enable_project_activation=True)
    assert _ACTIVATE_PROJECT in names
    # get_current_config remains excluded regardless of the flag
    assert _GET_CURRENT_CONFIG not in names


def test_context_field_keeps_activate_project_available() -> None:
    context = SerenaAgentContext.from_name("claude-code")
    context.allow_project_activation = True
    names = _toolset_names(context, _make_project(_make_config()), enable_project_activation=False)
    assert _ACTIVATE_PROJECT in names
    assert _GET_CURRENT_CONFIG not in names


def test_no_startup_project_is_unaffected() -> None:
    # Without a startup project the session is not single-project, so activate_project is available regardless.
    context = SerenaAgentContext.from_name("claude-code")
    names = _toolset_names(context, None, enable_project_activation=False)
    assert _ACTIVATE_PROJECT in names
