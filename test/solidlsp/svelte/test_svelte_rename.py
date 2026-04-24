import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language

pytestmark = pytest.mark.svelte


def assert_workspace_edit_shape(workspace_edit: dict, expected_new_text: str) -> None:
    has_changes = "changes" in workspace_edit and workspace_edit["changes"]
    has_document_changes = "documentChanges" in workspace_edit and workspace_edit["documentChanges"]
    assert has_changes or has_document_changes, "WorkspaceEdit should contain either 'changes' or 'documentChanges'"

    if has_changes:
        for uri, edits in workspace_edit["changes"].items():
            assert uri.startswith("file://"), f"URI should start with file://, got {uri}"
            assert len(edits) > 0, f"Expected at least one edit for {uri}"
            for edit in edits:
                assert "range" in edit, f"Edit in {uri} should contain range"
                assert "newText" in edit, f"Edit in {uri} should contain newText"
                assert edit["newText"] == expected_new_text, (
                    f"Expected newText '{expected_new_text}', got '{edit['newText']}'"
                )
    else:
        for change in workspace_edit["documentChanges"]:
            assert "textDocument" in change, "documentChanges entry missing textDocument"
            assert "edits" in change, "documentChanges entry missing edits"
            uri = change["textDocument"]["uri"]
            assert uri.startswith("file://"), f"URI should start with file://, got {uri}"
            assert len(change["edits"]) > 0, f"Expected at least one edit for {uri}"
            for edit in change["edits"]:
                assert "range" in edit, f"Edit in {uri} should contain range"
                assert "newText" in edit, f"Edit in {uri} should contain newText"
                assert edit["newText"] == expected_new_text, (
                    f"Expected newText '{expected_new_text}', got '{edit['newText']}'"
                )


class TestSvelteRename:
    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_rename_single_file_counter_function(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "routes", "Counter.svelte")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        modulo_symbol = next((s for s in symbols[0] if s.get("name") == "modulo"), None)

        if not modulo_symbol or "selectionRange" not in modulo_symbol:
            pytest.skip("modulo symbol not found in Counter.svelte - fixture may need updating")

        start = modulo_symbol["selectionRange"]["start"]
        workspace_edit = language_server.request_rename_symbol_edit(file_path, start["line"], start["character"], "normalizeModulo")

        assert workspace_edit is not None, "Expected WorkspaceEdit for single-file rename"
        assert_workspace_edit_shape(workspace_edit, "normalizeModulo")

        changes = workspace_edit.get("changes", {})
        if changes:
            assert any("Counter.svelte" in uri for uri in changes), (
                f"Expected rename edits for Counter.svelte, got {list(changes.keys())}"
            )

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_rename_cross_file_game_class(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "routes", "sverdle", "game.ts")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        game_symbol = next((s for s in symbols[0] if s.get("name") == "Game"), None)

        if not game_symbol or "selectionRange" not in game_symbol:
            pytest.skip("Game symbol not found in game.ts - fixture may need updating")

        start = game_symbol["selectionRange"]["start"]
        workspace_edit = language_server.request_rename_symbol_edit(file_path, start["line"], start["character"], "SverdleGame")

        assert workspace_edit is not None, "Expected WorkspaceEdit for cross-file rename"
        assert_workspace_edit_shape(workspace_edit, "SverdleGame")

        edited_uris: list[str] = []
        if workspace_edit.get("changes"):
            edited_uris.extend(workspace_edit["changes"].keys())
        if workspace_edit.get("documentChanges"):
            edited_uris.extend(change.get("textDocument", {}).get("uri", "") for change in workspace_edit["documentChanges"])

        assert any("game.ts" in uri for uri in edited_uris), f"Expected definition edits in game.ts, got {edited_uris}"
        assert any("%2Bpage.server.ts" in uri or "+page.server.ts" in uri for uri in edited_uris), (
            f"Expected import/usage edits in +page.server.ts, got {edited_uris}"
        )
