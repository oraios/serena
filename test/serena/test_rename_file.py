"""
`rename_file`: a file is renamed or moved and the language server's `workspace/willRenameFiles` edit keeps the
code that imports it valid.
"""

import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from serena.code_editor import LanguageServerCodeEditor
from serena.symbol import LanguageServerSymbolRetriever
from solidlsp import ls_types
from solidlsp.ls_config import LanguageServerId
from test.conftest import get_pytest_markers, get_repo_path, project_with_explicit_ls_context

# pyrefly 1.1.1 advertises workspace/willRenameFiles and answers it with null; 1.2.0 answers the edits.
# lazy-blocking: in the default indexing mode pyrefly may answer before its reverse-dependency graph is built.
LS_SETTINGS = {"python_pyrefly": {"pyrefly_version": "1.2.0", "indexing_mode": "lazy-blocking"}}


@contextmanager
def _editor_on_repo_copy(ls_id: LanguageServerId) -> Iterator[tuple[LanguageServerCodeEditor, Path]]:
    """A code editor over a throwaway copy of the language's test repo, so the rename never touches the fixture."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_copy = Path(tmp_dir) / "repo"
        shutil.copytree(get_repo_path(ls_id), repo_copy)
        with project_with_explicit_ls_context(ls_id, repo_root_override=str(repo_copy), ls_specific_settings=LS_SETTINGS) as project:
            yield LanguageServerCodeEditor(LanguageServerSymbolRetriever(project)), repo_copy


def _files_importing(repo: Path, module_name: str, suffix: str) -> set[str]:
    return {
        str(path.relative_to(repo))
        for path in repo.rglob(f"*{suffix}")
        if module_name in path.read_text(encoding="utf-8") and "import" in path.read_text(encoding="utf-8")
    }


@pytest.mark.parametrize(
    "ls_id",
    [pytest.param(LanguageServerId.PYTHON_PYREFLY, marks=get_pytest_markers(LanguageServerId.PYTHON_PYREFLY), id="python_pyrefly")],
)
def test_rename_python_module_updates_importers(ls_id: LanguageServerId) -> None:
    """
    Pyrefly (1.2.0) rewrites the ABSOLUTE imports of the renamed module (`from test_repo.models import ...` in
    `examples/` and `scripts/`); a RELATIVE import of it (`from .models import ...` in `services.py`) it leaves
    alone — a limit of the server, which the tool's answer cannot see, hence its advice to search for the old name.
    """
    with _editor_on_repo_copy(ls_id) as (editor, repo):
        old_rel, new_rel = os.path.join("test_repo", "models.py"), os.path.join("test_repo", "entities.py")
        absolute_importers = {os.path.join("examples", "user_management.py"), os.path.join("scripts", "run_app.py")}
        assert absolute_importers <= _files_importing(repo, "test_repo.models", ".py")

        message = editor.rename_file(old_rel, new_rel)

        assert not (repo / old_rel).exists()
        assert (repo / new_rel).is_file()
        assert "updated the references to it in 2 file(s)" in message, message
        for importer in absolute_importers:
            content = (repo / importer).read_text(encoding="utf-8")
            assert "from test_repo.entities import" in content, (importer, content)
            assert "test_repo.models" not in content, (importer, content)


@pytest.mark.parametrize(
    "ls_id",
    [pytest.param(LanguageServerId.TYPESCRIPT, marks=get_pytest_markers(LanguageServerId.TYPESCRIPT), id="typescript")],
)
def test_move_typescript_module_updates_importers(ls_id: LanguageServerId) -> None:
    with _editor_on_repo_copy(ls_id) as (editor, repo):
        old_rel, new_rel = "formatters.ts", os.path.join("lib", "greeters.ts")

        message = editor.rename_file(old_rel, new_rel)

        assert not (repo / old_rel).exists()
        assert (repo / new_rel).is_file(), "the move creates the missing parent directory"
        assert "updated the references" in message, message
        index = (repo / "index.ts").read_text(encoding="utf-8")
        assert "./lib/greeters" in index, index
        assert "./formatters" not in index, index


@pytest.mark.parametrize(
    "ls_id",
    [pytest.param(LanguageServerId.PYTHON_PYREFLY, marks=get_pytest_markers(LanguageServerId.PYTHON_PYREFLY), id="python_pyrefly")],
)
def test_a_rename_the_server_includes_in_its_edit_creates_the_target_directory(ls_id: LanguageServerId) -> None:
    """
    A server may put the rename itself among the edit's `documentChanges` (`kind: rename`); applying that operation
    must create the target's parent directory like `rename_file` does when it moves the file itself.
    """
    with _editor_on_repo_copy(ls_id) as (editor, repo):
        old_rel, new_rel = os.path.join("test_repo", "models.py"), os.path.join("test_repo", "moved", "deeper", "models.py")
        workspace_edit = ls_types.WorkspaceEdit(
            documentChanges=[{"kind": "rename", "oldUri": (repo / old_rel).as_uri(), "newUri": (repo / new_rel).as_uri()}]
        )

        assert editor._apply_workspace_edit(workspace_edit) == 1

        assert not (repo / old_rel).exists()
        assert (repo / new_rel).is_file()


@pytest.mark.parametrize(
    "ls_id",
    [pytest.param(LanguageServerId.PYTHON_PYREFLY, marks=get_pytest_markers(LanguageServerId.PYTHON_PYREFLY), id="python_pyrefly")],
)
def test_rename_file_refuses_a_missing_source_and_an_existing_target(ls_id: LanguageServerId) -> None:
    with _editor_on_repo_copy(ls_id) as (editor, _repo):
        with pytest.raises(FileNotFoundError):
            editor.rename_file(os.path.join("test_repo", "nope.py"), os.path.join("test_repo", "whatever.py"))
        with pytest.raises(FileExistsError):
            editor.rename_file(os.path.join("test_repo", "models.py"), os.path.join("test_repo", "services.py"))
