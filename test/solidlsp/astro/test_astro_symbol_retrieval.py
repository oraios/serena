"""
Cross-file symbol retrieval and reference tests for the Astro language server.
"""

import os
from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId

pytestmark = pytest.mark.astro


class TestAstroSymbolRetrieval:
    """Symbol retrieval and cross-file code intelligence tests."""

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.ASTRO], indirect=True)
    def test_get_containing_symbol_in_typescript(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Verify symbols in .ts files are discoverable within an Astro project."""
        counter_path = os.path.join("src", "stores", "counter.ts")
        symbols = language_server.request_document_symbols(counter_path)
        assert symbols is not None, "Expected document symbols but got None"
        all_symbols, _roots = symbols.get_all_symbols_and_roots()
        symbol_names = [s["name"] for s in all_symbols]
        assert "CounterStore" in symbol_names
        assert "createCounter" in symbol_names

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.ASTRO], indirect=True)
    def test_find_references_to_typescript_export(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Verify finding references to a TypeScript export from an .astro component.

        createCounter is defined in counter.ts (line 6) and imported + called in
        src/pages/index.astro (lines 4 and 7). This exercises the dual-server cross-file path:
        the companion TypeScript server with @astrojs/ts-plugin must resolve the .astro usage.
        """
        counter_path = os.path.join("src", "stores", "counter.ts")
        references = language_server.request_references(counter_path, 6, 20)
        assert references is not None, "Expected references but got None"
        locations = {(ref["uri"].rsplit("/", 1)[-1], ref["range"]["start"]["line"]) for ref in references}
        # Definition in counter.ts line 6
        assert ("counter.ts", 6) in locations, f"Expected definition at counter.ts:6, got: {sorted(locations)}"
        # Import in index.astro line 4
        assert ("index.astro", 4) in locations, f"Expected import at index.astro:4, got: {sorted(locations)}"
        # Invocation in index.astro line 7
        assert ("index.astro", 7) in locations, f"Expected call at index.astro:7, got: {sorted(locations)}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.ASTRO], indirect=True)
    def test_go_to_definition_from_typescript(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Verify go-to-definition within TypeScript source in an Astro project."""
        counter_path = os.path.join("src", "stores", "counter.ts")
        definitions = language_server.request_definition(counter_path, 6, 35)
        assert definitions, "Expected at least one definition location"
        def_loc = definitions[0]
        assert def_loc["uri"].endswith("counter.ts")
        assert def_loc["range"]["start"]["line"] == 0
