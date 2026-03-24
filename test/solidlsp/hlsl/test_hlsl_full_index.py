"""
Regression tests for HLSL full symbol tree indexing.

These tests verify that request_full_symbol_tree() correctly indexes all files,
including .hlsl includes in subdirectories. This catches bugs where files are
silently dropped during workspace-wide indexing.
"""

from typing import Any

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind
from solidlsp.ls_utils import SymbolUtils


def _collect_file_names(symbols: list[dict[str, Any]]) -> set[str]:
    """Recursively collect the names of all File-kind symbols in the tree."""
    names: set[str] = set()
    for sym in symbols:
        if sym.get("kind") == SymbolKind.File:
            names.add(sym["name"])
        if "children" in sym:
            names.update(_collect_file_names(sym["children"]))
    return names


EXPECTED_FILES = {"common", "lighting", "compute_test", "terrain_sdf"}

TERRAIN_SDF_UNIQUE_SYMBOLS = {"SampleSDF", "CalculateGradient", "SDFBrickData"}


@pytest.mark.hlsl
class TestHlslFullIndex:
    """Tests for full symbol tree indexing completeness."""

    @pytest.mark.parametrize("language_server", [Language.HLSL], indirect=True)
    def test_all_files_indexed_in_symbol_tree(self, language_server: SolidLanguageServer) -> None:
        """Every .hlsl file in the test repo must appear as a File symbol in the tree."""
        symbols = language_server.request_full_symbol_tree()
        file_names = _collect_file_names(symbols)
        missing = EXPECTED_FILES - file_names
        assert not missing, f"Files missing from full symbol tree: {missing}. Found: {file_names}"

    @pytest.mark.parametrize("language_server", [Language.HLSL], indirect=True)
    def test_subdirectory_file_symbols_present(self, language_server: SolidLanguageServer) -> None:
        """Symbols unique to terrain/terrain_sdf.hlsl must appear in the full tree."""
        symbols = language_server.request_full_symbol_tree()
        for name in TERRAIN_SDF_UNIQUE_SYMBOLS:
            assert SymbolUtils.symbol_tree_contains_name(symbols, name), (
                f"Expected '{name}' from terrain/terrain_sdf.hlsl in full symbol tree"
            )

    @pytest.mark.parametrize("language_server", [Language.HLSL], indirect=True)
    def test_include_file_document_symbols_directly(self, language_server: SolidLanguageServer) -> None:
        """request_document_symbols on terrain/terrain_sdf.hlsl should return its symbols."""
        doc_symbols = language_server.request_document_symbols("terrain/terrain_sdf.hlsl")
        all_symbols = doc_symbols.get_all_symbols_and_roots()
        symbol_names = {s.get("name") for s in all_symbols[0]}
        for name in TERRAIN_SDF_UNIQUE_SYMBOLS:
            assert name in symbol_names, f"Expected '{name}' in document symbols for terrain/terrain_sdf.hlsl, got: {symbol_names}"
