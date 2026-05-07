import os
from collections.abc import Iterable
from urllib.parse import unquote

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import TextEdit, WorkspaceEdit
from test.conftest import get_repo_path

pytestmark = pytest.mark.svelte


def _iter_workspace_edit_entries(workspace_edit: WorkspaceEdit) -> Iterable[tuple[str, TextEdit]]:
    if workspace_edit.get("changes"):
        for uri, edits in workspace_edit["changes"].items():
            for edit in edits:
                yield uri, edit

    for change in workspace_edit.get("documentChanges") or []:
        if "textDocument" not in change or "edits" not in change:
            continue
        uri = change["textDocument"]["uri"]
        for edit in change["edits"]:
            yield uri, edit


def _assert_rename_edit(
    workspace_edit: WorkspaceEdit | None,
    new_name: str,
    expected_path_fragments: set[str],
) -> None:
    assert workspace_edit is not None, "Svelte rename should return a WorkspaceEdit"

    entries = list(_iter_workspace_edit_entries(workspace_edit))
    assert entries, workspace_edit

    edited_paths = {unquote(uri).replace("\\", "/") for uri, _edit in entries}
    for expected_path in expected_path_fragments:
        assert any(expected_path in edited_path for edited_path in edited_paths), (
            f"Expected rename edit for {expected_path}, got {sorted(edited_paths)}"
        )

    for uri, edit in entries:
        assert "range" in edit, f"TextEdit in {uri} should have a range"
        assert "newText" in edit, f"TextEdit in {uri} should have newText"
        assert new_name in edit["newText"], f"TextEdit in {uri} should include {new_name}, got {edit['newText']}"
        assert edit["range"]["start"]["line"] >= 0
        assert edit["range"]["start"]["character"] >= 0


def _position_of_text(relative_file_path: str, text: str) -> tuple[int, int]:
    file_path = get_repo_path(Language.SVELTE) / relative_file_path
    for line_number, line in enumerate(file_path.read_text().splitlines()):
        if text in line:
            return line_number, line.index(text)
    raise AssertionError(f"Could not find {text!r} in {relative_file_path}")


class TestSvelteRename:
    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_rename_svelte_export_updates_svelte_importers(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "lib", "components", "Counter.svelte")
        line, col = _position_of_text(file_path, "count")

        workspace_edit = language_server.request_rename_symbol_edit(file_path, line, col, "score")

        _assert_rename_edit(
            workspace_edit,
            "score",
            {"src/lib/components/Counter.svelte", "src/lib/components/Header.svelte"},
        )

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_rename_svelte_export_updates_ts_and_svelte_files(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "lib", "components", "Words.svelte")
        line, col = _position_of_text(file_path, "words")

        workspace_edit = language_server.request_rename_symbol_edit(file_path, line, col, "vocabulary")

        _assert_rename_edit(
            workspace_edit,
            "vocabulary",
            {
                "src/lib/components/Words.svelte",
                "src/routes/(sverdle)/words.server.ts",
                "src/lib/game.ts",
                "src/routes/(sverdle)/+page.svelte",
            },
        )

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_rename_ts_export_updates_ts_importers(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "routes", "(sverdle)", "words.server.ts")
        line, col = _position_of_text(file_path, "allowed")

        workspace_edit = language_server.request_rename_symbol_edit(file_path, line, col, "allowedWords")

        _assert_rename_edit(
            workspace_edit,
            "allowedWords",
            {
                "src/routes/(sverdle)/words.server.ts",
                "src/lib/game.ts",
            },
        )

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_rename_ts_class_updates_ts_and_svelte_files(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "lib", "game.ts")
        line, col = _position_of_text(file_path, "Game")

        workspace_edit = language_server.request_rename_symbol_edit(file_path, line, col, "SverdleGame")

        _assert_rename_edit(
            workspace_edit,
            "SverdleGame",
            {
                "src/lib/game.ts",
                "src/routes/(sverdle)/+page.server.ts",
                "src/lib/components/Counter.svelte",
            },
        )
