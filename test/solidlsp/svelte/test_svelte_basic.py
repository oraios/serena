import os
from pathlib import Path

import pytest

from serena.util.text_utils import find_text_coordinates
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from test.solidlsp.conftest import read_repo_file
from test.solidlsp.svelte import conftest as svelte_test_conftest
from test.solidlsp.util.diagnostics import assert_file_diagnostics

pytestmark = pytest.mark.svelte


class TestSvelteLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.SVELTE], indirect=True)
    def test_svelte_language_server_root_matches_repo_path(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        assert language_server.is_running()
        assert repo_path.resolve() == svelte_test_conftest.repo_path.resolve()
        assert Path(language_server.language_server.repo_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_svelte_and_typescript_files_in_symbol_tree(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()

        assert SymbolUtils.symbol_tree_contains_name(symbols, "game"), "game variable not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Game"), "Game class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "words"), "words export not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "count"), "count export not found in symbol tree"
        # GAME_VERSION is defined *only* in a .ts file (game.ts); it is merely imported elsewhere.
        # It therefore guards against the regression where .ts document symbols are not routed to the
        # companion TS server (unlike game/Game/words/count, which also appear in .svelte files).
        assert SymbolUtils.symbol_tree_contains_name(symbols, "GAME_VERSION"), (
            "GAME_VERSION (defined only in a .ts file) not found in symbol tree"
        )

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_document_symbols_inside_svelte_file(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "lib", "components", "Counter.svelte")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        symbol_names = [symbol.get("name") for symbol in symbols[0]]

        assert "offset" in symbol_names
        assert "modulo" in symbol_names

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_document_symbols_inside_typescript_file(self, language_server: SolidLanguageServer) -> None:
        # document symbols of a plain .ts file must be served by the companion TS server, not the
        # base svelte LS (which only provides documentSymbol for .svelte files); see issue #1552.
        file_path = os.path.join("src", "lib", "game.ts")
        symbol_names = {symbol["name"] for symbol in language_server.request_document_symbols(file_path).iter_symbols()}

        # top-level symbols
        assert "GAME_VERSION" in symbol_names, symbol_names
        assert "Game" in symbol_names, symbol_names
        # members nested inside the Game class
        assert "enter" in symbol_names, symbol_names
        assert "toString" in symbol_names, symbol_names

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_overview_of_typescript_file(self, language_server: SolidLanguageServer) -> None:
        # get_symbols_overview on a .ts file must not be empty in svelte-only mode (issue #1552).
        file_path = os.path.join("src", "lib", "game.ts")
        overview = language_server.request_overview(file_path)

        top_level_names = {symbol["name"] for symbols in overview.values() for symbol in symbols}
        assert "GAME_VERSION" in top_level_names, overview
        assert "Game" in top_level_names, overview

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_definition_from_component_import_to_svelte_file(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "lib", "components", "Header.svelte")
        coords = find_text_coordinates(read_repo_file(language_server, file_path), r"(count)")

        definitions = language_server.request_definition(file_path, coords.line, coords.col)

        assert len(definitions) == 1, definitions
        assert definitions[0]["relativePath"].replace("\\", "/") == "src/lib/components/Counter.svelte"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_diagnostics_in_typescript_file(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            os.path.join("src", "lib", "diagnostics_sample.ts"),
            ("missingGreeting", "missingConsumerValue"),
            min_count=2,
        )

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_diagnostics_in_svelte_file(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            os.path.join("src", "lib", "diagnostics_sample.svelte"),
            ("number", "string"),
            min_count=1,
        )
