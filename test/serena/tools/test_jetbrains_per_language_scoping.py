"""Tests for Behaviour 2 (language scoping + coverage note) of the per-language tool-disabling
mechanism under the JetBrains backend, specifically for ``jet_brains_find_symbol``.

The JetBrains plugin client is stubbed so the tests need neither a running IDE nor a language
server; only the in-tool scoping/filtering logic is exercised. We disable the tool for *python*
(the language that actually has files in the python test repo) so that the coverage-note file
count is > 0 and the note is emitted.
"""

import pytest

from serena.config.serena_config import ProjectConfig
from serena.project import Project
from serena.tools.jetbrains_tools import JetBrainsFindSymbolTool
from solidlsp.ls_config import Language
from test.conftest import create_default_serena_config, get_repo_path


class _FakeAgent:
    """Minimal agent stub exposing only what the tool + scoping helper need."""

    def __init__(self, project: Project):
        self._project = project
        self.serena_config = project.serena_config

    def get_active_project(self) -> Project | None:
        return self._project

    def get_active_project_or_raise(self) -> Project:
        return self._project


class _FakeClient:
    """Stub for JetBrainsPluginClient used as a context manager."""

    def __init__(self, symbols):
        self._symbols = symbols

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def find_symbol(self, **kwargs):
        return {"symbols": self._symbols}


_PY_SYMBOLS = [
    {"name_path": "BaseModel", "type": "Class", "relative_path": "test_repo/models.py"},
    {"name_path": "Helper", "type": "Class", "relative_path": "test_repo/utils.py"},
]


def _make_tool(excluded, monkeypatch, symbols) -> JetBrainsFindSymbolTool:
    project = Project(
        project_root=str(get_repo_path(Language.PYTHON)),
        project_config=ProjectConfig(
            project_name="jb_scope_repo",
            languages=[Language.PYTHON],
            excluded_tools_by_language=excluded,
        ),
        serena_config=create_default_serena_config(),
    )
    monkeypatch.setattr(
        "serena.tools.jetbrains_tools.JetBrainsPluginClient.from_project",
        lambda _project: _FakeClient(symbols),
    )
    return JetBrainsFindSymbolTool(_FakeAgent(project))  # type: ignore[arg-type]


def test_whole_project_search_scoped_away_with_note(monkeypatch):
    tool = _make_tool({Language.PYTHON: ["jet_brains_find_symbol"]}, monkeypatch, _PY_SYMBOLS)
    try:
        result = tool.apply(name_path_pattern="BaseModel")
        assert "Coverage" in result, f"expected coverage note, got: {result}"
        assert "disabled for python" in result
        # the python symbols must have been scoped away (only the note remains, not the symbol body)
        assert "BaseModel" not in result.split("\n", 1)[1]
    finally:
        tool.project.shutdown(timeout=5)


def test_no_note_when_tool_not_excluded(monkeypatch):
    tool = _make_tool({}, monkeypatch, _PY_SYMBOLS)
    try:
        result = tool.apply(name_path_pattern="BaseModel")
        assert "Coverage" not in result
        assert "BaseModel" in result  # nothing scoped away
    finally:
        tool.project.shutdown(timeout=5)


def test_external_dependency_symbols_are_not_scoped(monkeypatch):
    symbols = [
        {"name_path": "BaseModel", "type": "Class", "relative_path": "test_repo/models.py"},
        {"name_path": "ExtThing", "type": "Class", "relative_path": "<ext:lib/foo.py>"},
    ]
    tool = _make_tool({Language.PYTHON: ["jet_brains_find_symbol"]}, monkeypatch, symbols)
    try:
        result = tool.apply(name_path_pattern="Thing", search_deps=True)
        assert "Coverage" in result  # in-project python files were skipped
        body = result.split("\n", 1)[1]
        assert "ExtThing" in body          # external symbol retained
        assert "BaseModel" not in body     # in-project python symbol scoped away
    finally:
        tool.project.shutdown(timeout=5)
