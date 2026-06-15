"""Tests for Behaviour 2 (transparent scoping of whole-project / search calls) of the
per-language tool-disabling mechanism, plus the supporting helpers.

* ``LanguageServerManager.iter_language_servers(exclude_languages=...)`` filtering.
* ``Project.count_source_files_for_languages`` / ``_filter_out_languages``.
* ``_format_coverage_note`` formatting.
* ``SearchForPatternTool`` end-to-end: excluded-language files are skipped and a coverage note is
  emitted only when files were actually skipped.
"""

import logging

import pytest

from serena.config.serena_config import ProjectConfig, RegisteredProject, SerenaConfig
from serena.ls_manager import LanguageServerManager
from serena.project import Project, _filter_out_languages
from serena.tools.file_tools import SearchForPatternTool
from serena.tools.tools_base import _format_coverage_note
from solidlsp.ls_config import Language
from test.conftest import create_default_serena_config, get_repo_path


class _StubLS:
    def __init__(self, language: Language):
        self.language = language

    def is_running(self) -> bool:
        return True


class TestIterLanguageServersExclusion:
    def _manager(self) -> LanguageServerManager:
        servers = {
            Language.PYTHON: _StubLS(Language.PYTHON),
            Language.TYPESCRIPT: _StubLS(Language.TYPESCRIPT),
            Language.HAXE: _StubLS(Language.HAXE),
        }
        return LanguageServerManager(servers)  # type: ignore[arg-type]

    def test_no_exclusion_yields_all(self):
        manager = self._manager()
        langs = {ls.language for ls in manager.iter_language_servers()}
        assert langs == {Language.PYTHON, Language.TYPESCRIPT, Language.HAXE}

    def test_excludes_single_language(self):
        manager = self._manager()
        langs = {ls.language for ls in manager.iter_language_servers(exclude_languages={Language.HAXE})}
        assert langs == {Language.PYTHON, Language.TYPESCRIPT}

    def test_excludes_multiple_languages(self):
        manager = self._manager()
        langs = {ls.language for ls in manager.iter_language_servers(exclude_languages={Language.HAXE, Language.PYTHON})}
        assert langs == {Language.TYPESCRIPT}


class TestFormatCoverageNote:
    def test_empty_returns_none(self):
        assert _format_coverage_note({}) is None

    def test_zero_counts_return_none(self):
        assert _format_coverage_note({Language.HAXE: 0}) is None

    def test_single_language(self):
        note = _format_coverage_note({Language.HAXE: 12})
        assert note is not None
        assert "12 haxe" in note
        assert "disabled for haxe" in note

    def test_multiple_languages_sorted(self):
        note = _format_coverage_note({Language.PYTHON: 3, Language.HAXE: 12})
        assert note is not None
        # languages reported in alphabetical order
        assert note.index("haxe") < note.index("python")


class TestFilterOutLanguages:
    def test_removes_matching_extensions(self):
        paths = ["src/Main.hx", "src/app.py", "README.md", "lib/Util.hx"]
        assert _filter_out_languages(paths, {Language.HAXE}) == ["src/app.py", "README.md"]

    def test_empty_exclusion_is_identity(self):
        paths = ["a.py", "b.hx"]
        assert _filter_out_languages(paths, frozenset()) == paths


class TestCountSourceFilesForLanguages:
    def test_counts_python_files(self):
        project = Project(
            project_root=str(get_repo_path(Language.PYTHON)),
            project_config=ProjectConfig(project_name="test_repo", languages=[Language.PYTHON]),
            serena_config=create_default_serena_config(),
        )
        try:
            counts = project.count_source_files_for_languages({Language.PYTHON})
            assert counts.get(Language.PYTHON, 0) > 0
        finally:
            project.shutdown(timeout=5)

    def test_no_files_for_absent_language(self):
        project = Project(
            project_root=str(get_repo_path(Language.PYTHON)),
            project_config=ProjectConfig(project_name="test_repo", languages=[Language.PYTHON, Language.HAXE]),
            serena_config=create_default_serena_config(),
        )
        try:
            counts = project.count_source_files_for_languages({Language.HAXE})
            assert counts.get(Language.HAXE, 0) == 0
        finally:
            project.shutdown(timeout=5)


@pytest.mark.python
class TestSearchForPatternScoping:
    """End-to-end test of ``search_for_pattern`` scoping through a real agent."""

    def _make_agent(self, excluded: dict[Language, list[str]]):
        from serena.agent import SerenaAgent

        config = SerenaConfig(gui_log_window=False, web_dashboard=False, log_level=logging.ERROR)
        project = Project(
            project_root=str(get_repo_path(Language.PYTHON)),
            project_config=ProjectConfig(
                project_name="search_scope_repo",
                languages=[Language.PYTHON],
                excluded_tools_by_language=excluded,
            ),
            serena_config=config,
        )
        config.projects = [RegisteredProject.from_project_instance(project)]
        agent = SerenaAgent(project="search_scope_repo", serena_config=config)
        agent.execute_task(lambda: None)
        return agent

    def test_excluded_language_files_are_skipped_with_note(self):
        agent = self._make_agent({Language.PYTHON: ["search_for_pattern"]})
        try:
            tool = agent.get_tool(SearchForPatternTool)
            # search for something that certainly exists in the python sources
            result = tool.apply(substring_pattern="class ", restrict_search_to_code_files=True)
            assert "Coverage" in result, f"expected coverage note, got: {result}"
            assert "disabled for python" in result
            # no python file should appear in the (scoped-away) results
            assert ".py" not in result.split("\n", 1)[1] if "\n" in result else True
        finally:
            agent.on_shutdown(timeout=10)

    def test_no_note_when_tool_not_excluded(self):
        agent = self._make_agent({})
        try:
            tool = agent.get_tool(SearchForPatternTool)
            result = tool.apply(substring_pattern="class ", restrict_search_to_code_files=True)
            assert "Coverage" not in result
            # the python matches should be present
            assert ".py" in result
        finally:
            agent.on_shutdown(timeout=10)


@pytest.mark.python
class TestFindSymbolScoping:
    """End-to-end test of ``find_symbol`` whole-project scoping through a real agent."""

    def _make_agent(self, excluded: dict[Language, list[str]]):
        from serena.agent import SerenaAgent

        config = SerenaConfig(gui_log_window=False, web_dashboard=False, log_level=logging.ERROR)
        project = Project(
            project_root=str(get_repo_path(Language.PYTHON)),
            project_config=ProjectConfig(
                project_name="find_symbol_scope_repo",
                languages=[Language.PYTHON],
                excluded_tools_by_language=excluded,
            ),
            serena_config=config,
        )
        config.projects = [RegisteredProject.from_project_instance(project)]
        agent = SerenaAgent(project="find_symbol_scope_repo", serena_config=config)
        agent.execute_task(lambda: None)
        return agent

    def test_whole_project_search_scoped_away_with_note(self):
        from serena.tools.symbol_tools import FindSymbolTool

        agent = self._make_agent({Language.PYTHON: ["find_symbol"]})
        try:
            tool = agent.get_tool(FindSymbolTool)
            # whole-project search (no relative_path) for a symbol that exists in the python sources
            result = tool.apply(name_path_pattern="BaseModel")
            assert "Coverage" in result, f"expected coverage note, got: {result}"
            assert "disabled for python" in result
            # since python is the only language and it is excluded, no symbols are returned
            assert "BaseModel" not in result.split("\n", 1)[1] if "\n" in result else True
        finally:
            agent.on_shutdown(timeout=10)

    def test_pinned_file_is_refused_not_scoped(self):
        """A find_symbol call that pins an excluded-language file is refused (Behaviour 1), not scoped."""
        from serena.tools.symbol_tools import FindSymbolTool

        agent = self._make_agent({Language.PYTHON: ["find_symbol"]})
        try:
            tool = agent.get_tool(FindSymbolTool)
            rp = str(__import__("pathlib").Path("test_repo") / "models.py")
            result = tool.apply_ex(log_call=False, name_path_pattern="BaseModel", relative_path=rp)
            assert "disabled for python" in result
            assert "is a python file" in result
        finally:
            agent.on_shutdown(timeout=10)
