"""Agent-level symbol discovery/navigation for plain .ts files of a svelte-only project.

Reproduces https://github.com/oraios/serena/issues/1552: in ``languages: [svelte]`` mode,
document-symbol requests for .ts/.js files were answered by the base svelte LS (which only
serves .svelte files) instead of being routed to the companion, svelte-plugin-aware TS server.
As a consequence, symbols defined in plain .ts files were undiscoverable through ``find_symbol``/
``get_symbols_overview``, and ``find_referencing_symbols`` failed with ``No symbol matching ...``
because it must first locate the target symbol via ``documentSymbol``.

These tests exercise the high-level :class:`LanguageServerSymbolRetriever` that backs those agent
tools, complementing the lower-level checks in ``test_svelte_basic.py``.
"""

import os

import pytest

from serena.project import Project
from serena.symbol import LanguageServerSymbolRetriever
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind

pytestmark = pytest.mark.svelte

# a plain .ts module whose exported symbols are consumed by both .ts and .svelte files
GAME_TS = os.path.join("src", "lib", "game.ts")


class TestSvelteTypeScriptSymbolDiscovery:
    @pytest.mark.parametrize("project_with_ls", [Language.SVELTE], indirect=True)
    def test_find_symbol_in_typescript_file(self, project_with_ls: Project) -> None:
        retriever = LanguageServerSymbolRetriever(project_with_ls)

        # GAME_VERSION is *defined* only in game.ts (merely imported elsewhere)
        version_symbols = retriever.find("GAME_VERSION", within_relative_path=GAME_TS)
        assert [s.name for s in version_symbols] == ["GAME_VERSION"]
        assert version_symbols[0].relative_path is not None
        assert version_symbols[0].relative_path.replace("\\", "/") == "src/lib/game.ts"

        # the Game class is discoverable and correctly typed
        game_symbols = retriever.find("Game", within_relative_path=GAME_TS, include_kinds=[SymbolKind.Class])
        assert len(game_symbols) == 1, game_symbols
        assert game_symbols[0].symbol_kind == SymbolKind.Class

        # nested members of the .ts class are discoverable via their name path
        enter_symbols = retriever.find("Game/enter", within_relative_path=GAME_TS)
        assert len(enter_symbols) == 1, enter_symbols
        assert enter_symbols[0].get_name_path() == "Game/enter"

    @pytest.mark.parametrize("project_with_ls", [Language.SVELTE], indirect=True)
    def test_find_referencing_symbols_locates_typescript_symbol(self, project_with_ls: Project) -> None:
        retriever = LanguageServerSymbolRetriever(project_with_ls)

        # The core of issue #1552 for find-references: the target symbol must first be located via
        # documentSymbol. Before the fix, .ts document symbols were empty, so locating the symbol
        # raised ValueError("No symbol matching 'GAME_VERSION' found") *before the companion TS
        # server was ever consulted*. Verify the symbol is now uniquely discoverable.
        symbol = retriever.find_unique("GAME_VERSION", within_relative_path=GAME_TS)
        assert symbol.name == "GAME_VERSION"
        assert symbol.relative_path is not None
        assert symbol.relative_path.replace("\\", "/") == "src/lib/game.ts"

        # The end-to-end find_referencing_symbols call must now get past symbol discovery without
        # raising. (The cross-file/.svelte reference *content* is covered by test_svelte_references.py
        # and depends on the companion TS server's reference graph rather than on this fix.)
        references = retriever.find_referencing_symbols("GAME_VERSION", GAME_TS)
        assert isinstance(references, list)
