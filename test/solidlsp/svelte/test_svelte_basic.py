import os
import re

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from serena.util.text_utils import find_text_coordinates
from test.solidlsp.conftest import read_repo_file

pytestmark = pytest.mark.svelte


class TestSvelteLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_svelte_and_typescript_files_in_symbol_tree(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()

        assert SymbolUtils.symbol_tree_contains_name(symbols, "game"), "game variable not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Game"), "Game class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "words"), "words export not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "count"), "count export not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_document_symbols_inside_svelte_file(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "lib", "components", "Counter.svelte")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        symbol_names = [symbol.get("name") for symbol in symbols[0]]

        assert "offset" in symbol_names
        assert "modulo" in symbol_names

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_definition_from_component_import_to_svelte_file(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "lib", "components", "Header.svelte")
        line, col = find_text_coordinates(read_repo_file(language_server, file_path), r"(count)")

        definitions = language_server.request_definition(file_path, line, col)

        assert len(definitions) == 1, definitions
        assert definitions[0]["relativePath"].replace("\\", "/") == "src/lib/components/Counter.svelte"
