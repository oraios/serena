"""
Tests for the editing facade API (backend-independent parts, without a language server).
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from serena.code_editor import CodeEditor
from serena.config.serena_config import SerenaConfig
from serena.project import Project
from serena.repl.api.edit_api import SUCCESS_RESULT, EditApi, ReplacementPreview
from serena.repl.facade import ApiScope, Facade
from serena.symbol import PositionInFile
from solidlsp.ls_utils import TextUtils


@pytest.fixture
def project(tmp_path: Path) -> Project:
    (tmp_path / "a.py").write_text("x = foo(1)\ny = foo(2)\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("z = foo(3)\n", encoding="utf-8")
    return Project.load(str(tmp_path), serena_config=SerenaConfig(gui_log_window=False, web_dashboard=False))


@pytest.fixture
def api(project: Project) -> EditApi:
    agent = MagicMock()
    agent.get_active_project_or_raise.return_value = project
    agent.serena_config.default_max_tool_answer_chars = 10000
    return EditApi(agent)


def test_facade_exposes_editing_operations(api: EditApi) -> None:
    default_methods = {
        "replace_content",
        "replace_in_files",
        "replace_symbol_body",
        "insert_after_symbol",
        "insert_before_symbol",
    }
    optional_methods = {"delete_lines", "replace_lines", "insert_at_line"}  # the line-level operations are optional (as are the tools)

    facade = Facade.from_api(api, ApiScope())
    assert facade.name == "edit"
    assert set(facade.enabled_method_names) == default_methods
    for name in optional_methods:
        assert facade.get_method(name).info.optional
    assert all(facade.get_method(name).info.can_edit for name in default_methods | optional_methods)


def test_replace_in_files_dry_run_returns_inspectable_preview(api: EditApi, project: Project) -> None:
    preview = api.replace_in_files("foo", "bar", mode="literal", dry_run=True)
    assert isinstance(preview, ReplacementPreview)

    # the occurrences are accessible from code
    assert [o.relative_path for o in preview.occurrences] == ["a.py", "a.py", "b.py"]
    assert preview.affected_files == ["a.py", "b.py"]
    assert all(o.replacement == "bar" for o in preview.occurrences)

    # the rendering lists the occurrence ids and diffs; nothing was modified
    rendered = preview.represent()
    assert "DRY RUN" in rendered
    assert all(o.occurrence_id in rendered for o in preview.occurrences)
    assert (Path(project.project_root) / "a.py").read_text(encoding="utf-8") == "x = foo(1)\ny = foo(2)\n"


def test_replace_in_files_guard_failure_includes_preview(api: EditApi) -> None:
    with pytest.raises(ValueError, match="expected_count=1") as exc_info:
        api.replace_in_files("foo", "bar", mode="literal", expected_count=1)
    assert "b.py" in str(exc_info.value)  # the listing of prospective changes is included


class _TextOpsEditedFile(CodeEditor.EditedFile):
    """An ``EditedFile`` whose edits are applied to the in-memory text with the primitives the real backends use."""

    def __init__(self, relative_path: str, contents: str, fail_on_insert: bool = False) -> None:
        super().__init__(relative_path)
        self._contents = contents
        self.fail_on_insert = fail_on_insert

    def get_contents(self) -> str:
        return self._contents

    def set_contents(self, contents: str) -> None:
        self._contents = contents

    def delete_text_between_positions(self, start_pos: PositionInFile, end_pos: PositionInFile) -> None:
        self._contents, _ = TextUtils.delete_text_between_positions(
            self._contents, start_pos.line, start_pos.col, end_pos.line, end_pos.col
        )

    def insert_text_at_position(self, pos: PositionInFile, text: str) -> None:
        if self.fail_on_insert:
            raise RuntimeError("simulated insert failure")
        self._contents, _, _ = TextUtils.insert_text_at_position(self._contents, pos.line, pos.col, text)


class _LineEditingCodeEditor(CodeEditor[Any]):
    """A ``CodeEditor`` that edits a real file, so the line-level operations run without a language server."""

    def __init__(self, project: Project) -> None:
        super().__init__(project)
        self.fail_on_insert = False

    @contextmanager
    def _open_file_context(self, relative_path: str) -> Iterator[CodeEditor.EditedFile]:
        with open(os.path.join(self.project_root, relative_path), encoding=self.encoding) as f:
            contents = f.read()
        yield _TextOpsEditedFile(relative_path, contents, fail_on_insert=self.fail_on_insert)

    def _find_unique_symbol(self, name_path: str, relative_file_path: str) -> Any:
        raise NotImplementedError

    def rename_symbol(self, name_path: str, relative_path: str, new_name: str) -> str:
        raise NotImplementedError


@pytest.fixture
def line_editing_api(tmp_path: Path) -> tuple[EditApi, _LineEditingCodeEditor]:
    (tmp_path / "a.py").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    project = Project.load(str(tmp_path), serena_config=SerenaConfig(gui_log_window=False, web_dashboard=False))
    editor = _LineEditingCodeEditor(project)
    agent = MagicMock()
    agent.get_active_project_or_raise.return_value = project
    agent.serena_config.default_max_tool_answer_chars = 10000
    agent.get_language_backend.return_value.create_code_editor.return_value = editor
    return EditApi(agent), editor


def test_replace_lines_replaces_the_range(line_editing_api: tuple[EditApi, _LineEditingCodeEditor], tmp_path: Path) -> None:
    api, _ = line_editing_api

    result = api.replace_lines("a.py", start_line=1, end_line=2, content="TWO\nTHREE")

    assert result == SUCCESS_RESULT
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "one\nTWO\nTHREE\nfour\n"


def test_replace_lines_keeps_the_file_when_the_insert_fails(
    line_editing_api: tuple[EditApi, _LineEditingCodeEditor], tmp_path: Path
) -> None:
    """The range must not be deleted durably if the replacement cannot be written.

    Deleting the range and inserting the replacement as two separate operations persists
    the first one, so a failure in between leaves the caller with a file that has lost
    the lines it asked to replace.
    """
    api, editor = line_editing_api
    editor.fail_on_insert = True

    with pytest.raises(RuntimeError, match="simulated insert failure"):
        api.replace_lines("a.py", start_line=1, end_line=2, content="TWO\nTHREE")

    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "one\ntwo\nthree\nfour\n"
