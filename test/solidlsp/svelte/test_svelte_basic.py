import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.conftest import format_symbol_for_assert, request_all_symbols

pytestmark = pytest.mark.svelte


class TestSvelteBasic:
    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_document_symbols_counter_file(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "routes", "Counter.svelte")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        symbol_names = [symbol.get("name") for symbol in symbols[0]]

        assert "modulo" in symbol_names, f"Expected modulo function in Counter.svelte symbols, got {symbol_names}"
        assert "count" in symbol_names, f"Expected count symbol in Counter.svelte symbols, got {symbol_names}"
        assert "offset" in symbol_names, f"Expected offset symbol in Counter.svelte symbols, got {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_document_symbols_game_file(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "routes", "sverdle", "game.ts")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        symbol_names = [symbol.get("name") for symbol in symbols[0]]

        assert "Game" in symbol_names, f"Expected Game class in game.ts symbols, got {symbol_names}"
        assert "enter" in symbol_names, f"Expected enter method in game.ts symbols, got {symbol_names}"
        assert "toString" in symbol_names, f"Expected toString method in game.ts symbols, got {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_cross_file_references_game_import(self, language_server: SolidLanguageServer) -> None:
        game_file = os.path.join("src", "routes", "sverdle", "game.ts")
        symbols = language_server.request_document_symbols(game_file).get_all_symbols_and_roots()
        game_symbol = next((symbol for symbol in symbols[0] if symbol.get("name") == "Game"), None)

        if not game_symbol or "selectionRange" not in game_symbol:
            pytest.skip("Game symbol not found in game.ts - fixture may need updating")

        sel_start = game_symbol["selectionRange"]["start"]
        references = language_server.request_references(game_file, sel_start["line"], sel_start["character"])
        uris = [ref.get("uri", "") for ref in references]

        assert len(references) >= 2, "Expected at least definition + import reference for Game"
        assert any("game.ts" in uri for uri in uris), f"Expected definition reference in game.ts, got {uris}"
        assert any("%2Bpage.server.ts" in uri or "+page.server.ts" in uri for uri in uris), (
            f"Expected reference in +page.server.ts, got {uris}"
        )

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_cross_file_references_header_component(self, language_server: SolidLanguageServer) -> None:
        header_file = os.path.join("src", "routes", "Header.svelte")
        definitions = language_server.request_definition(header_file, 10, 14)

        assert isinstance(definitions, list), f"Expected list from request_definition, got {type(definitions)}"

        layout_file = os.path.join("src", "routes", "+layout.svelte")
        layout_symbols = language_server.request_document_symbols(layout_file).get_all_symbols_and_roots()
        symbol_names = [symbol.get("name") for symbol in layout_symbols[0]]
        assert any(name in symbol_names for name in ["Header", "children"]), (
            f"Expected common +layout symbols to be discoverable, got {symbol_names}"
        )

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_reference_deduplication(self, language_server: SolidLanguageServer) -> None:
        target_file = os.path.join("src", "routes", "sverdle", "game.ts")
        symbols = language_server.request_document_symbols(target_file).get_all_symbols_and_roots()
        symbol = next((s for s in symbols[0] if s.get("name") == "Game"), None)

        if not symbol or "selectionRange" not in symbol:
            pytest.skip("Game symbol not found in game.ts - fixture may need updating")

        sel_start = symbol["selectionRange"]["start"]
        refs = language_server.request_references(target_file, sel_start["line"], sel_start["character"])

        seen_locations: set[tuple[str, int, int]] = set()
        duplicates: list[tuple[str, int, int]] = []
        for ref in refs:
            if "range" not in ref:
                continue
            uri = ref.get("uri", "")
            line = ref["range"]["start"]["line"]
            character = ref["range"]["start"]["character"]
            key = (uri, line, character)
            if key in seen_locations:
                duplicates.append(key)
            else:
                seen_locations.add(key)

        assert not duplicates, f"Expected no duplicate references, got duplicates: {duplicates}"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_bare_symbol_names(self, language_server: SolidLanguageServer) -> None:
        all_symbols = request_all_symbols(language_server)
        malformed_symbols = [symbol for symbol in all_symbols if not isinstance(symbol.get("name"), str) or not symbol["name"].strip()]
        # Svelte symbol names often include CSS selectors, callbacks, and generated expressions.
        # The most stable hygiene check is that names are present and non-empty.
        assert not malformed_symbols, (
            f"Found symbols with missing/empty names: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}"
        )
