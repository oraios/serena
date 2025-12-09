"""
Vue language server rename tests.

Tests symbol renaming functionality including single-file and
cross-file rename operations for Vue components and TypeScript files.
"""

import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language

pytestmark = pytest.mark.vue


class TestVueRename:
    """Tests for Vue symbol rename operations."""

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_rename_function_within_single_file(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        handle_digit_symbol = next((s for s in symbols[0] if s.get("name") == "handleDigit"), None)

        if not handle_digit_symbol or "selectionRange" not in handle_digit_symbol:
            pytest.skip("handleDigit symbol not found - test fixture may need updating")

        sel_start = handle_digit_symbol["selectionRange"]["start"]

        workspace_edit = language_server.request_rename_symbol_edit(file_path, sel_start["line"], sel_start["character"], "processDigit")

        assert workspace_edit is not None, "Should return WorkspaceEdit for rename operation"

        has_changes = "changes" in workspace_edit and workspace_edit["changes"]
        has_document_changes = "documentChanges" in workspace_edit and workspace_edit["documentChanges"]

        assert has_changes or has_document_changes, "WorkspaceEdit should contain either 'changes' or 'documentChanges'"

        if has_changes:
            changes = workspace_edit["changes"]
            assert len(changes) > 0, "Should have at least one file with changes"

            calculator_input_files = [uri for uri in changes.keys() if "CalculatorInput.vue" in uri]
            assert len(calculator_input_files) > 0, f"Should have edits for CalculatorInput.vue. Found edits for: {list(changes.keys())}"

            file_edits = changes[calculator_input_files[0]]
            assert len(file_edits) > 0, "Should have at least one TextEdit for the renamed symbol"

            for edit in file_edits:
                assert "range" in edit, "TextEdit should have a range"
                assert "newText" in edit, "TextEdit should have newText"
                assert edit["newText"] == "processDigit", f"newText should be 'processDigit', got {edit['newText']}"

                assert "start" in edit["range"], "Range should have start position"
                assert "end" in edit["range"], "Range should have end position"
                assert "line" in edit["range"]["start"], "Start position should have line number"
                assert "character" in edit["range"]["start"], "Start position should have character offset"

        elif has_document_changes:
            document_changes = workspace_edit["documentChanges"]
            assert isinstance(document_changes, list), "documentChanges should be a list"
            assert len(document_changes) > 0, "Should have at least one document change"

            calculator_input_changes = [dc for dc in document_changes if "CalculatorInput.vue" in dc.get("textDocument", {}).get("uri", "")]
            assert len(calculator_input_changes) > 0, "Should have edits for CalculatorInput.vue"

            for change in calculator_input_changes:
                assert "textDocument" in change, "Document change should have textDocument"
                assert "edits" in change, "Document change should have edits"

                edits = change["edits"]
                assert len(edits) > 0, "Should have at least one TextEdit for the renamed symbol"

                for edit in edits:
                    assert "range" in edit, "TextEdit should have a range"
                    assert "newText" in edit, "TextEdit should have newText"
                    assert edit["newText"] == "processDigit", f"newText should be 'processDigit', got {edit['newText']}"

                    assert "start" in edit["range"], "Range should have start position"
                    assert "end" in edit["range"], "Range should have end position"
                    assert "line" in edit["range"]["start"], "Start position should have line number"
                    assert "character" in edit["range"]["start"], "Start position should have character offset"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_rename_composable_function_cross_file(self, language_server: SolidLanguageServer) -> None:
        composable_file = os.path.join("src", "composables", "useFormatter.ts")

        symbols = language_server.request_document_symbols(composable_file).get_all_symbols_and_roots()
        use_formatter_symbol = next((s for s in symbols[0] if s.get("name") == "useFormatter"), None)

        if not use_formatter_symbol or "selectionRange" not in use_formatter_symbol:
            pytest.skip("useFormatter symbol not found - test fixture may need updating")

        sel_start = use_formatter_symbol["selectionRange"]["start"]

        workspace_edit = language_server.request_rename_symbol_edit(
            composable_file, sel_start["line"], sel_start["character"], "useNumberFormatter"
        )

        assert workspace_edit is not None, "Should return WorkspaceEdit for cross-file rename"

        has_changes = "changes" in workspace_edit and workspace_edit["changes"]
        has_document_changes = "documentChanges" in workspace_edit and workspace_edit["documentChanges"]

        assert has_changes or has_document_changes, "WorkspaceEdit should contain either 'changes' or 'documentChanges'"

        if has_changes:
            changes = workspace_edit["changes"]
            assert len(changes) > 0, "Should have at least one file with changes"

            composable_files = [uri for uri in changes.keys() if "useFormatter.ts" in uri]
            assert len(composable_files) > 0, f"Should have edits for useFormatter.ts (definition). Found edits for: {list(changes.keys())}"

            for uri, edits in changes.items():
                assert len(edits) > 0, f"File {uri} should have at least one edit"

                for edit in edits:
                    assert "range" in edit, f"TextEdit in {uri} should have a range"
                    assert "newText" in edit, f"TextEdit in {uri} should have newText"
                    assert edit["newText"] == "useNumberFormatter", f"newText should be 'useNumberFormatter', got {edit['newText']}"
                    assert "start" in edit["range"], f"Range in {uri} should have start position"
                    assert "end" in edit["range"], f"Range in {uri} should have end position"

        elif has_document_changes:
            document_changes = workspace_edit["documentChanges"]
            assert isinstance(document_changes, list), "documentChanges should be a list"
            assert len(document_changes) > 0, "Should have at least one document change"

            composable_changes = [dc for dc in document_changes if "useFormatter.ts" in dc.get("textDocument", {}).get("uri", "")]
            assert (
                len(composable_changes) > 0
            ), f"Should have edits for useFormatter.ts (definition). Found changes for: {[dc.get('textDocument', {}).get('uri', '') for dc in document_changes]}"

            for change in document_changes:
                assert "textDocument" in change, "Document change should have textDocument"
                assert "edits" in change, "Document change should have edits"

                uri = change["textDocument"]["uri"]
                edits = change["edits"]
                assert len(edits) > 0, f"File {uri} should have at least one edit"

                for edit in edits:
                    assert "range" in edit, f"TextEdit in {uri} should have a range"
                    assert "newText" in edit, f"TextEdit in {uri} should have newText"
                    assert edit["newText"] == "useNumberFormatter", f"newText should be 'useNumberFormatter', got {edit['newText']}"
                    assert "start" in edit["range"], f"Range in {uri} should have start position"
                    assert "end" in edit["range"], f"Range in {uri} should have end position"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_rename_verifies_correct_file_paths_and_ranges(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "App.vue")

        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        app_title_symbol = next((s for s in symbols[0] if s.get("name") == "appTitle"), None)

        if not app_title_symbol or "selectionRange" not in app_title_symbol:
            pytest.skip("appTitle symbol not found - test fixture may need updating")

        sel_start = app_title_symbol["selectionRange"]["start"]

        workspace_edit = language_server.request_rename_symbol_edit(
            file_path, sel_start["line"], sel_start["character"], "applicationTitle"
        )

        assert workspace_edit is not None, "Should return WorkspaceEdit for rename operation"
        assert isinstance(workspace_edit, dict), "WorkspaceEdit should be a dictionary"

        has_changes = "changes" in workspace_edit and workspace_edit["changes"]
        has_document_changes = "documentChanges" in workspace_edit and workspace_edit["documentChanges"]

        assert has_changes or has_document_changes, "WorkspaceEdit must have 'changes' or 'documentChanges'"

        if has_changes:
            changes = workspace_edit["changes"]

            assert isinstance(changes, dict), "changes should be a dict mapping URIs to TextEdit lists"

            assert len(changes) > 0, "Should have edits for at least one file"

            for uri, edits in changes.items():
                assert isinstance(uri, str), f"URI should be a string, got {type(uri)}"
                assert uri.startswith("file://"), f"URI should start with 'file://', got {uri}"

                assert isinstance(edits, list), f"Edits for {uri} should be a list, got {type(edits)}"
                assert len(edits) > 0, f"Should have at least one edit for {uri}"

                for idx, edit in enumerate(edits):
                    assert isinstance(edit, dict), f"Edit {idx} in {uri} should be a dict, got {type(edit)}"

                    assert "range" in edit, f"Edit {idx} in {uri} missing 'range'"
                    assert "newText" in edit, f"Edit {idx} in {uri} missing 'newText'"

                    range_obj = edit["range"]
                    assert "start" in range_obj, f"Edit {idx} range in {uri} missing 'start'"
                    assert "end" in range_obj, f"Edit {idx} range in {uri} missing 'end'"

                    for pos_name in ["start", "end"]:
                        pos = range_obj[pos_name]
                        assert "line" in pos, f"Edit {idx} range {pos_name} in {uri} missing 'line'"
                        assert "character" in pos, f"Edit {idx} range {pos_name} in {uri} missing 'character'"
                        assert isinstance(pos["line"], int), f"Line should be int, got {type(pos['line'])}"
                        assert isinstance(pos["character"], int), f"Character should be int, got {type(pos['character'])}"
                        assert pos["line"] >= 0, f"Line number should be >= 0, got {pos['line']}"
                        assert pos["character"] >= 0, f"Character offset should be >= 0, got {pos['character']}"

                    assert isinstance(edit["newText"], str), f"newText should be string, got {type(edit['newText'])}"
                    assert edit["newText"] == "applicationTitle", f"newText should be 'applicationTitle', got {edit['newText']}"

        elif has_document_changes:
            document_changes = workspace_edit["documentChanges"]
            assert isinstance(document_changes, list), "documentChanges should be a list"
            assert len(document_changes) > 0, "Should have at least one document change"

            for change in document_changes:
                assert isinstance(change, dict), "Each document change should be a dict"
                assert "textDocument" in change, "Document change should have textDocument"
                assert "edits" in change, "Document change should have edits"

                text_doc = change["textDocument"]
                assert "uri" in text_doc, "textDocument should have uri"
                assert text_doc["uri"].startswith("file://"), f"URI should start with 'file://', got {text_doc['uri']}"

                edits = change["edits"]
                assert isinstance(edits, list), "edits should be a list"
                assert len(edits) > 0, "Should have at least one edit"

                for idx, edit in enumerate(edits):
                    assert isinstance(edit, dict), f"Edit {idx} in {text_doc['uri']} should be a dict, got {type(edit)}"

                    assert "range" in edit, f"Edit {idx} in {text_doc['uri']} missing 'range'"
                    assert "newText" in edit, f"Edit {idx} in {text_doc['uri']} missing 'newText'"

                    range_obj = edit["range"]
                    assert "start" in range_obj, f"Edit {idx} range in {text_doc['uri']} missing 'start'"
                    assert "end" in range_obj, f"Edit {idx} range in {text_doc['uri']} missing 'end'"

                    for pos_name in ["start", "end"]:
                        pos = range_obj[pos_name]
                        assert "line" in pos, f"Edit {idx} range {pos_name} in {text_doc['uri']} missing 'line'"
                        assert "character" in pos, f"Edit {idx} range {pos_name} in {text_doc['uri']} missing 'character'"
                        assert isinstance(pos["line"], int), f"Line should be int, got {type(pos['line'])}"
                        assert isinstance(pos["character"], int), f"Character should be int, got {type(pos['character'])}"
                        assert pos["line"] >= 0, f"Line number should be >= 0, got {pos['line']}"
                        assert pos["character"] >= 0, f"Character offset should be >= 0, got {pos['character']}"

                    assert isinstance(edit["newText"], str), f"newText should be string, got {type(edit['newText'])}"
                    assert edit["newText"] == "applicationTitle", f"newText should be 'applicationTitle', got {edit['newText']}"
