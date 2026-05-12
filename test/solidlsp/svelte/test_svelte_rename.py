import os
from collections.abc import Iterable
from urllib.parse import unquote

import pytest

from serena.util.text_utils import find_text_coordinates
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import TextEdit, WorkspaceEdit
from test.solidlsp.conftest import read_repo_file

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
    assert workspace_edit is not None, "rename should return a WorkspaceEdit"

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


class TestSvelteRename:
    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_rename_svelte_export_updates_svelte_importers(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "lib", "components", "Counter.svelte")
        coords = find_text_coordinates(read_repo_file(language_server, file_path), r"(count)")

        workspace_edit = language_server.request_rename_symbol_edit(file_path, coords.line, coords.col, "score")

        _assert_rename_edit(
            workspace_edit,
            "score",
            {"src/lib/components/Counter.svelte", "src/lib/components/Header.svelte"},
        )

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_rename_svelte_export_updates_ts_and_svelte_files(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "lib", "components", "Words.svelte")
        coords = find_text_coordinates(read_repo_file(language_server, file_path), r"(words)")

        workspace_edit = language_server.request_rename_symbol_edit(file_path, coords.line, coords.col, "vocabulary")

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
    def test_rename_ts_export_declaration_site_workspace_edit(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "routes", "(sverdle)", "words.server.ts")
        coords = find_text_coordinates(read_repo_file(language_server, file_path), r"(allowed)")

        assert coords is not None

        workspace_edit = language_server.request_rename_symbol_edit(file_path, coords.line, coords.col, "allowedWords")

        _assert_rename_edit(
            workspace_edit,
            "allowedWords",
            {"src/routes/(sverdle)/words.server.ts"},
        )

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_rename_ts_class_cross_file_workspace_edit_when_supported(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "lib", "game.ts")
        coords = find_text_coordinates(read_repo_file(language_server, file_path), r"(Game)")

        assert coords is not None

        workspace_edit = language_server.request_rename_symbol_edit(file_path, coords.line, coords.col, "SverdleGame")

        assert workspace_edit is not None, (
            "SvelteLanguageServer.request_rename_symbol_edit returned None for a cross-file TS class rename; "
            "companion SvelteTypeScriptServer (typescript-svelte-plugin) should provide this edit."
        )

        _assert_rename_edit(
            workspace_edit,
            "SverdleGame",
            {
                "src/lib/game.ts",
                "src/routes/(sverdle)/+page.server.ts",
                "src/lib/components/Counter.svelte",
            },
        )
