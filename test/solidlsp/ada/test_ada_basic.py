from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols


@pytest.mark.ada
class TestAdaLanguageServer:
    """Tests for AdaCore's Ada Language Server (covers Ada and SPARK).

    Source layout (test/resources/repos/ada/test_repo):

        default.gpr
        src/
          helper.ads      package spec, declares ``Greet`` and ``Greeting_Style``
          helper.adb      package body, defines ``Greet``
          main.adb        ``with Helper;`` and calls ``Helper.Greet``

    LSP positions are 0-indexed. Below, the layout is annotated with the
    columns used by each test so that future edits to the fixtures are
    obviously test-affecting.
    """

    @pytest.mark.parametrize("language_server", [Language.ADA], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.ADA], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.ADA], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.ADA], indirect=True)
    def test_find_definition_within_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        # main.adb (1-indexed source / 0-indexed LSP):
        #   5/4:    Greeting : constant String := Helper.Greet ("Ada");
        #   7/6:    Ada.Text_IO.Put_Line (Greeting);
        # `Greeting` in `Put_Line (Greeting)` starts at column 25 on LSP line 6.
        main_path = str(repo_path / "src" / "main.adb")
        definitions = language_server.request_definition(main_path, 6, 26)

        assert definitions, f"Expected non-empty definition list but got {definitions=}"
        assert len(definitions) == 1
        loc = definitions[0]
        assert loc["uri"].endswith("main.adb")
        # `Greeting` is declared on LSP line 4; ALS points at the identifier (column 3).
        assert loc["range"]["start"]["line"] == 4

    @pytest.mark.parametrize("language_server", [Language.ADA], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.ADA], indirect=True)
    def test_find_definition_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        # main.adb LSP line 4 / column 40 sits on the `G` of `Helper.Greet`:
        #   `   Greeting : constant String := Helper.Greet ("Ada");`
        #                                            ^ col 40
        # ALS resolves cross-file `Helper.Greet` to its spec declaration in helper.ads
        # (LSP line 4, column 12 — the `G` of `Greet` after `   function `).
        main_path = str(repo_path / "src" / "main.adb")
        definitions = language_server.request_definition(main_path, 4, 40)

        assert definitions, f"Expected non-empty definition list but got {definitions=}"
        assert len(definitions) == 1
        loc = definitions[0]
        assert loc["uri"].endswith("helper.ads")
        assert loc["range"]["start"]["line"] == 4
        assert loc["range"]["start"]["character"] == 12

    @pytest.mark.parametrize("language_server", [Language.ADA], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.ADA], indirect=True)
    def test_find_references_within_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        # Click on `Helper` in `with Helper;` (main.adb LSP line 1, column 5).
        # Serena's request_references uses includeDeclaration=False, so we need a symbol with
        # at least one non-declaration usage in the same file. `Helper` is referenced as a
        # context clause on line 1 and again as the qualifier of `Helper.Greet` on line 4.
        main_path = str(repo_path / "src" / "main.adb")
        references = language_server.request_references(main_path, 1, 5)

        assert references, f"Expected non-empty references for Helper but got {references=}"
        ref_lines_in_main = {loc["range"]["start"]["line"] for loc in references if loc["uri"].endswith("main.adb")}
        # The qualifier usage on LSP line 4 of main.adb must appear among the references.
        assert 4 in ref_lines_in_main, f"Expected reference on line 4 of main.adb, got {ref_lines_in_main}"

    @pytest.mark.parametrize("language_server", [Language.ADA], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.ADA], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        # Click on the `G` of `Greet` in the spec:
        # helper.ads LSP line 4: `   function Greet (Name : String) return String;`
        # `Greet` starts at column 12 (`   ` + `function ` = 3 + 9 = 12).
        spec_path = str(repo_path / "src" / "helper.ads")
        references = language_server.request_references(spec_path, 4, 12)

        assert references, f"Expected non-empty references for Helper.Greet but got {references=}"
        ref_files = {loc["uri"].split("/")[-1] for loc in references}
        # The call site in main.adb must appear in the references.
        assert "main.adb" in ref_files, f"Expected reference in main.adb, got {ref_files}"

    @pytest.mark.parametrize("language_server", [Language.ADA], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        from solidlsp.ls_utils import SymbolUtils

        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Helper"), "Helper package not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Greet"), "Greet subprogram not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Main"), "Main procedure not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.ADA], indirect=True)
    def test_document_symbols_helper(self, language_server: SolidLanguageServer) -> None:
        doc_symbols = language_server.request_document_symbols(str(Path("src") / "helper.ads"))
        all_symbols, _ = doc_symbols.get_all_symbols_and_roots()
        names = {sym.get("name") for sym in all_symbols if sym.get("name")}
        assert "Helper" in names, f"Helper package not found in helper.ads document symbols. Found: {names}"
        assert "Greet" in names, f"Greet not found in helper.ads document symbols. Found: {names}"

    @pytest.mark.parametrize("language_server", [Language.ADA], indirect=True)
    def test_document_symbols_hierarchical_structure(self, language_server: SolidLanguageServer) -> None:
        """ALS must return hierarchical DocumentSymbol[] with subprograms nested under their package."""
        all_symbols, root_symbols = language_server.request_document_symbols(str(Path("src") / "helper.ads")).get_all_symbols_and_roots()

        root_names = [s.get("name") for s in root_symbols]
        assert "Helper" in root_names, f"Helper package not at root level. Roots: {root_names}"

        helper_symbol = next((s for s in root_symbols if s.get("name") == "Helper"), None)
        assert helper_symbol is not None, "Helper package missing from root symbols"
        helper_children = helper_symbol.get("children", [])
        helper_child_names = [c.get("name") for c in helper_children]
        assert helper_child_names, f"Helper package has no children — hierarchicalDocumentSymbolSupport is not working. Roots: {root_names}"
        assert "Greet" in helper_child_names, f"Greet not nested under Helper. Children: {helper_child_names}"

        # Greet must NOT appear at root level — that would indicate the flat fallback format.
        assert "Greet" not in root_names, f"Greet should be a child of Helper, not at root level. Roots: {root_names}"

    @pytest.mark.parametrize("language_server", [Language.ADA], indirect=True)
    def test_bare_symbol_names(self, language_server: SolidLanguageServer) -> None:
        # ALS surfaces a few Ada-specific synthetic groupings as symbols:
        #   - "With clauses" — namespace-kind group containing all `with` statements in a unit
        #   - dotted unit names like "Ada.Text_IO" — references to library packages
        # Both are legitimate names for Ada; allow whitespace and periods accordingly.
        all_symbols = request_all_symbols(language_server)
        malformed_symbols = [s for s in all_symbols if has_malformed_name(s, whitespace_allowed=True, period_allowed=True)]
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )
