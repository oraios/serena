import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind
from solidlsp.ls_utils import SymbolUtils
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols


@pytest.mark.haxe
class TestHaxeLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.HAXE], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer) -> None:
        """Test that the Haxe language server starts successfully."""
        assert language_server.is_running()

    @pytest.mark.parametrize("language_server", [Language.HAXE], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Main"), "Main class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "greet"), "greet method not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "calculateResult"), "calculateResult method not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Helper"), "Helper class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "addNumbers"), "addNumbers method not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "formatMessage"), "formatMessage method not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.HAXE], indirect=True)
    def test_bare_symbol_names(self, language_server: SolidLanguageServer) -> None:
        """Test that symbol names do not contain unexpected formatting characters."""
        all_symbols = request_all_symbols(language_server)
        malformed_symbols = []
        for s in all_symbols:
            if has_malformed_name(s):
                malformed_symbols.append(s)
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )

    @pytest.mark.parametrize("language_server", [Language.HAXE], indirect=True)
    def test_find_references_within_file(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "Main.hx")
        all_symbols, _ = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        greet_symbol = next((s for s in all_symbols if s.get("name") == "greet"), None)
        assert greet_symbol is not None, "Could not find 'greet' symbol in Main.hx"
        sel_start = greet_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])

        assert refs, f"Expected non-empty references for greet but got {refs=}"

        # Convert references to a comparable format
        actual_locations = [
            {
                "uri_suffix": os.path.basename(ref.get("relativePath", ref.get("uri", ""))),
                "line": ref["range"]["start"]["line"],
            }
            for ref in refs
        ]

        # greet is called on line 15 (0-indexed) in Main.hx: `message = greet("World");`
        call_site = {"uri_suffix": "Main.hx", "line": 15}
        assert call_site in actual_locations, f"Expected reference to greet at line 15 in Main.hx, got {actual_locations}"

        # All references should be within Main.hx (greet is not used in other files)
        assert all(loc["uri_suffix"] == "Main.hx" for loc in actual_locations), (
            f"Expected all greet references in Main.hx, got {actual_locations}"
        )

    @pytest.mark.parametrize("language_server", [Language.HAXE], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer) -> None:
        # Test addNumbers which is defined in Helper.hx and used in Main.hx
        helper_path = os.path.join("src", "utils", "Helper.hx")
        all_symbols, _ = language_server.request_document_symbols(helper_path).get_all_symbols_and_roots()
        add_numbers_symbol = next((s for s in all_symbols if s.get("name") == "addNumbers"), None)
        assert add_numbers_symbol is not None, "Could not find 'addNumbers' symbol in Helper.hx"

        sel_start = add_numbers_symbol["selectionRange"]["start"]
        refs = language_server.request_references(helper_path, sel_start["line"], sel_start["character"])

        assert refs, f"Expected non-empty references for addNumbers but got {refs=}"

        # Convert references to a comparable format
        actual_locations = [
            {
                "uri_suffix": os.path.basename(ref.get("relativePath", ref.get("uri", ""))),
                "line": ref["range"]["start"]["line"],
            }
            for ref in refs
        ]

        # addNumbers is called on line 16 in Main.hx: `count = Helper.addNumbers(5, 10);`
        call_site_1 = {"uri_suffix": "Main.hx", "line": 16}
        assert call_site_1 in actual_locations, f"Expected reference to addNumbers at line 16 in Main.hx, got {actual_locations}"

        # addNumbers is called on line 30 in Main.hx: `var sum = Helper.addNumbers(count, 20);`
        call_site_2 = {"uri_suffix": "Main.hx", "line": 30}
        assert call_site_2 in actual_locations, f"Expected reference to addNumbers at line 30 in Main.hx, got {actual_locations}"

        # Verify cross-file: at least one reference is in Main.hx (different file from definition)
        main_refs = [loc for loc in actual_locations if loc["uri_suffix"] == "Main.hx"]
        assert len(main_refs) >= 2, f"Expected at least 2 references in Main.hx (lines 16 and 30), got {main_refs}"

    @pytest.mark.parametrize("language_server", [Language.HAXE], indirect=True)
    def test_document_symbols_structure(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "Main.hx")
        result = language_server.request_document_symbols(file_path)
        all_symbols, roots = result.get_all_symbols_and_roots()

        # Main class should be a root symbol
        main_symbol = None
        for sym in roots:
            if sym.get("name") == "Main":
                main_symbol = sym
                break
        assert main_symbol is not None, "Main class not found as root symbol"
        assert main_symbol.get("kind") in (SymbolKind.Class, SymbolKind.Struct), f"Expected Main to be Class, got {main_symbol.get('kind')}"

        # Check that methods and fields exist and are children of Main
        child_names = {s.get("name") for s in all_symbols if s.get("name") != "Main"}
        assert "greet" in child_names, "greet method not found in symbols"
        assert "calculateResult" in child_names, "calculateResult method not found in symbols"
        assert "message" in child_names, "message field not found in symbols"
        assert "count" in child_names, "count field not found in symbols"

        # Verify symbol kinds for specific symbols
        for sym in all_symbols:
            if sym.get("name") == "greet":
                assert sym.get("kind") in (
                    SymbolKind.Method,
                    SymbolKind.Function,
                ), f"Expected greet to be Method/Function, got {sym.get('kind')}"
            if sym.get("name") == "message":
                assert sym.get("kind") in (
                    SymbolKind.Field,
                    SymbolKind.Variable,
                    SymbolKind.Property,
                ), f"Expected message to be Field/Variable, got {sym.get('kind')}"

    @pytest.mark.parametrize("language_server", [Language.HAXE], indirect=True)
    def test_workspace_symbol(self, language_server: SolidLanguageServer) -> None:
        result = language_server.request_workspace_symbol("Helper")
        assert result is not None, "Workspace symbol search returned None"
        assert len(result) > 0, "Workspace symbol search returned no results"
        assert any("Helper" in str(s.get("name", "")) for s in result), f"Expected at least one result containing 'Helper', got {result}"

    @pytest.mark.parametrize("language_server", [Language.HAXE], indirect=True)
    def test_go_to_definition_within_file(self, language_server: SolidLanguageServer) -> None:
        """Go to definition of greet from its call site in Main.hx -- should resolve within the same file."""
        main_path = os.path.join("src", "Main.hx")
        # Line 16 (0-indexed: 15): `message = greet("World");`
        # `greet` starts at character 12 on that line.
        definitions = language_server.request_definition(main_path, 15, 12)
        assert definitions, "Expected to find definition for greet"
        assert any("Main.hx" in d.get("uri", d.get("relativePath", "")) for d in definitions), (
            f"Expected definition in Main.hx, got {definitions}"
        )
        # greet is defined on line 23 (0-indexed: 22) in Main.hx
        definition_lines = [d["range"]["start"]["line"] for d in definitions if "Main.hx" in d.get("uri", d.get("relativePath", ""))]
        assert 22 in definition_lines, f"Expected definition of greet at line 22 in Main.hx, got lines {definition_lines}"

    @pytest.mark.parametrize("language_server", [Language.HAXE], indirect=True)
    def test_go_to_definition(self, language_server: SolidLanguageServer) -> None:
        """Go to definition of addNumbers from a call site in Main.hx -- should resolve to Helper.hx."""
        main_path = os.path.join("src", "Main.hx")
        # Line 17 (0-indexed: 16): `\t\tcount = Helper.addNumbers(5, 10);`
        # `addNumbers` starts at character 17 (0-indexed) on that line.
        definitions = language_server.request_definition(main_path, 16, 17)
        assert definitions, "Expected to find definition for addNumbers"
        assert any("Helper.hx" in d.get("uri", d.get("relativePath", "")) for d in definitions), (
            f"Expected definition in Helper.hx, got {definitions}"
        )
        # addNumbers is defined on line 18 (0-indexed) in Helper.hx
        definition_lines = [d["range"]["start"]["line"] for d in definitions if "Helper.hx" in d.get("uri", d.get("relativePath", ""))]
        assert 18 in definition_lines, f"Expected definition of addNumbers at line 18 in Helper.hx, got lines {definition_lines}"

    @pytest.mark.parametrize("language_server", [Language.HAXE], indirect=True)
    def test_hover(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "Main.hx")
        result = language_server.request_document_symbols(file_path)
        all_symbols, _ = result.get_all_symbols_and_roots()
        greet_symbol = next((s for s in all_symbols if s.get("name") == "greet"), None)
        assert greet_symbol is not None, "Could not find 'greet' symbol"

        sel_start = greet_symbol["selectionRange"]["start"]
        hover = language_server.request_hover(file_path, sel_start["line"], sel_start["character"])
        assert hover is not None, "Hover returned None for greet method"
        hover_str = str(hover)
        assert "String" in hover_str or "greet" in hover_str, f"Expected hover to contain type info, got {hover_str}"

    @pytest.mark.parametrize("language_server", [Language.HAXE], indirect=True)
    def test_hover_on_class_declaration(self, language_server: SolidLanguageServer) -> None:
        """Hovering on a class name should return hover info."""
        file_path = os.path.join("src", "Main.hx")
        result = language_server.request_document_symbols(file_path)
        all_symbols, _ = result.get_all_symbols_and_roots()

        main_symbol = next((s for s in all_symbols if s.get("name") == "Main"), None)
        assert main_symbol is not None

        sel_start = main_symbol["selectionRange"]["start"]
        hover = language_server.request_hover(file_path, sel_start["line"], sel_start["character"])
        assert hover is not None, "Hover on class declaration returned None"
        hover_str = str(hover)
        assert "Main" in hover_str, f"Expected hover to contain 'Main', got {hover_str}"

    @pytest.mark.parametrize("language_server", [Language.HAXE], indirect=True)
    def test_rename_symbol(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "Main.hx")
        result = language_server.request_document_symbols(file_path)
        all_symbols, _ = result.get_all_symbols_and_roots()
        greet_symbol = next((s for s in all_symbols if s.get("name") == "greet"), None)
        assert greet_symbol is not None, "Could not find 'greet' symbol"

        sel_start = greet_symbol["selectionRange"]["start"]
        edits = language_server.request_rename_symbol_edit(file_path, sel_start["line"], sel_start["character"], "sayHello")
        assert edits is not None, "Rename returned None"
        # Verify edits contain changes (WorkspaceEdit has 'changes' or 'documentChanges')
        edits_str = str(edits)
        assert "Main.hx" in edits_str, f"Expected rename edits for Main.hx, got {edits}"
        assert "sayHello" in edits_str, f"Expected new name 'sayHello' in rename edits, got {edits}"

    @pytest.mark.parametrize("language_server", [Language.HAXE], indirect=True)
    def test_completions(self, language_server: SolidLanguageServer) -> None:
        """Request completions after Helper. in calculateResult — should return Helper's static methods."""
        file_path = os.path.join("src", "Main.hx")
        # Line 31 (0-indexed: 30): `var sum = Helper.addNumbers(count, 20);`
        # Trigger completions after `Helper.` — character 19 is right after the dot.
        completions = language_server.request_completions(file_path, 30, 19)
        assert completions, "Expected non-empty completions after Helper."
        completion_texts = [c.get("completionText", c.get("label", "")) for c in completions]
        assert "addNumbers" in completion_texts, f"Expected 'addNumbers' in completions after Helper., got {completion_texts[:10]}"

    @pytest.mark.parametrize("language_server", [Language.HAXE], indirect=True)
    def test_document_overview(self, language_server: SolidLanguageServer) -> None:
        overview = language_server.request_document_overview(os.path.join("src", "Main.hx"))
        assert overview, "Document overview returned empty list"
        symbol_names = [s.get("name", "") for s in overview]
        assert any("Main" in name for name in symbol_names), f"Expected 'Main' in overview, got {symbol_names}"
        main_entry = next((s for s in overview if s.get("name") == "Main"), None)
        assert main_entry is not None, f"Expected 'Main' entry in overview, got {symbol_names}"
        assert main_entry.get("kind") in (SymbolKind.Class, SymbolKind.Struct), (
            f"Expected Main to be Class/Struct in overview, got kind {main_entry.get('kind')}"
        )
        for s in overview:
            assert s.get("name"), "Symbol missing 'name' field"
            assert s.get("kind"), "Symbol missing 'kind' field"

    @pytest.mark.parametrize("language_server", [Language.HAXE], indirect=True)
    def test_rapid_successive_requests(self, language_server: SolidLanguageServer) -> None:
        """Verify that rapid successive requests don't return empty results.

        The Haxe LS triggers a recompilation on didOpen. Without suppression,
        subsequent requests during recompilation may return empty results.
        """
        main_path = os.path.join("src", "Main.hx")
        helper_path = os.path.join("src", "utils", "Helper.hx")

        # First request: hover on greet in Main.hx (line 22 is the greet method definition)
        hover1 = language_server.request_hover(main_path, 22, 20)

        # Second request: references in a different file (triggers another didOpen)
        all_symbols, _ = language_server.request_document_symbols(helper_path).get_all_symbols_and_roots()
        add_numbers = next((s for s in all_symbols if s.get("name") == "addNumbers"), None)
        assert add_numbers is not None
        sel_start = add_numbers["selectionRange"]["start"]
        refs = language_server.request_references(helper_path, sel_start["line"], sel_start["character"])

        # Third request: back to Main.hx hover (would be affected by recompilation)
        hover2 = language_server.request_hover(main_path, 22, 20)

        # All three should return non-empty results
        assert hover1 is not None, "First hover returned None"
        assert refs, "References returned empty after switching files"
        assert hover2 is not None, "Second hover returned None after file switching"
