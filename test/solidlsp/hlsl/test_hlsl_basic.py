"""
Basic tests for HLSL language server integration (shader-language-server).

This module tests Language.HLSL using shader-language-server from antaalt/shader-sense.
Tests are skipped if the language server is not available.
"""

from typing import Any

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_types import SymbolKind
from solidlsp.ls_utils import SymbolUtils
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols


def _find_symbol_by_name(language_server: SolidLanguageServer, file_path: str, name: str) -> dict[str, Any] | None:
    """Find a top-level symbol by name in a file's document symbols."""
    symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
    return next((s for s in symbols[0] if s.get("name") == name), None)


# ── Symbol Discovery ─────────────────────────────────────────────


@pytest.mark.hlsl
class TestHlslSymbols:
    """Tests for document symbol extraction."""

    @pytest.mark.parametrize("language_server", [Language.HLSL], indirect=True)
    def test_find_struct(self, language_server: SolidLanguageServer) -> None:
        """VertexInput struct should appear in common.hlsl symbols."""
        symbol = _find_symbol_by_name(language_server, "common.hlsl", "VertexInput")
        assert symbol is not None, "Expected 'VertexInput' struct in document symbols"

    @pytest.mark.parametrize("language_server", [Language.HLSL], indirect=True)
    def test_find_function(self, language_server: SolidLanguageServer) -> None:
        """SafeNormalize function should appear in common.hlsl."""
        symbol = _find_symbol_by_name(language_server, "common.hlsl", "SafeNormalize")
        assert symbol is not None, "Expected 'SafeNormalize' function in document symbols"

    @pytest.mark.parametrize("language_server", [Language.HLSL], indirect=True)
    def test_find_cbuffer_members(self, language_server: SolidLanguageServer) -> None:
        """Cbuffer members should appear as variables in compute_test.hlsl.

        Note: shader-language-server reports cbuffer members as individual
        variables (kind 13), not the cbuffer name itself as a symbol.
        """
        symbol = _find_symbol_by_name(language_server, "compute_test.hlsl", "TextureSize")
        assert symbol is not None, "Expected 'TextureSize' cbuffer member in document symbols"

    @pytest.mark.parametrize("language_server", [Language.HLSL], indirect=True)
    def test_find_compute_kernel(self, language_server: SolidLanguageServer) -> None:
        """CSMain kernel should appear in compute_test.hlsl."""
        symbol = _find_symbol_by_name(language_server, "compute_test.hlsl", "CSMain")
        assert symbol is not None, "Expected 'CSMain' compute kernel in document symbols"

    @pytest.mark.parametrize("language_server", [Language.HLSL], indirect=True)
    def test_full_symbol_tree(self, language_server: SolidLanguageServer) -> None:
        """Full symbol tree should contain symbols from multiple files."""
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "VertexInput"), "VertexInput not in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculateDiffuse"), "CalculateDiffuse not in symbol tree"


# ── Go-to-Definition ─────────────────────────────────────────────


@pytest.mark.hlsl
class TestHlslDefinition:
    """Tests for go-to-definition capability."""

    @pytest.mark.parametrize("language_server", [Language.HLSL], indirect=True)
    def test_goto_definition_cross_file(self, language_server: SolidLanguageServer) -> None:
        """Navigating to SafeNormalize call in lighting.hlsl should resolve to common.hlsl.

        lighting.hlsl line 22 (0-indexed): "    float3 halfVec = SafeNormalize(-lightDir + viewDir);"
        SafeNormalize starts at column 21.
        """
        definitions = language_server.request_definition("lighting.hlsl", 22, 21)
        assert len(definitions) >= 1, f"Expected at least 1 definition, got {len(definitions)}"
        def_paths = [d.get("relativePath", d.get("uri", "")) for d in definitions]
        assert any("common.hlsl" in p for p in def_paths), f"Expected definition in common.hlsl, got: {def_paths}"

    @pytest.mark.parametrize("language_server", [Language.HLSL], indirect=True)
    def test_goto_definition_cross_file_remap(self, language_server: SolidLanguageServer) -> None:
        """Navigating to Remap call in compute_test.hlsl should resolve to common.hlsl.

        compute_test.hlsl line 20 (0-indexed): "        Remap(color.r, 0.0, 1.0, 0.2, 0.8),"
        Remap starts at column 8.
        """
        definitions = language_server.request_definition("compute_test.hlsl", 20, 8)
        assert len(definitions) >= 1, f"Expected at least 1 definition, got {len(definitions)}"
        def_paths = [d.get("relativePath", d.get("uri", "")) for d in definitions]
        assert any("common.hlsl" in p for p in def_paths), f"Expected definition in common.hlsl, got: {def_paths}"


# ── References ────────────────────────────────────────────────────


@pytest.mark.hlsl
class TestHlslReferences:
    """Tests for find-references capability.

    shader-language-server does not advertise referencesProvider, so
    request_references is expected to return an empty list.
    """

    @pytest.mark.parametrize("language_server", [Language.HLSL], indirect=True)
    def test_references_not_supported(self, language_server: SolidLanguageServer) -> None:
        """References request should raise because shader-language-server does not support it.

        common.hlsl line 17 (0-indexed): "float3 SafeNormalize(float3 v)"
        SafeNormalize starts at column 7.
        """
        with pytest.raises(SolidLSPException, match="Method not found"):
            language_server.request_references("common.hlsl", 17, 7)


# ── Hover ─────────────────────────────────────────────────────────


def _extract_hover_text(hover_info: dict[str, Any]) -> str:
    """Extract the text content from an LSP hover response."""
    contents = hover_info["contents"]
    if isinstance(contents, dict):
        return contents.get("value", "")
    elif isinstance(contents, str):
        return contents
    return str(contents)


@pytest.mark.hlsl
class TestHlslHover:
    """Tests for hover information."""

    @pytest.mark.parametrize("language_server", [Language.HLSL], indirect=True)
    def test_hover_on_function(self, language_server: SolidLanguageServer) -> None:
        """Hovering over SafeNormalize definition should return info.

        common.hlsl line 17 (0-indexed): "float3 SafeNormalize(float3 v)"
        SafeNormalize starts at column 7.
        """
        hover_info = language_server.request_hover("common.hlsl", 17, 7)
        assert hover_info is not None, "Hover should return information for SafeNormalize"
        assert "contents" in hover_info, "Hover should have contents"
        hover_text = _extract_hover_text(hover_info)
        assert len(hover_text) > 0, "Hover text should not be empty"

    @pytest.mark.parametrize("language_server", [Language.HLSL], indirect=True)
    def test_hover_on_struct(self, language_server: SolidLanguageServer) -> None:
        """Hovering over VertexInput should return struct info.

        common.hlsl line 3 (0-indexed): "struct VertexInput"
        VertexInput starts at column 7.
        """
        hover_info = language_server.request_hover("common.hlsl", 3, 7)
        assert hover_info is not None, "Hover should return information for VertexInput"
        assert "contents" in hover_info, "Hover should have contents"

    @pytest.mark.parametrize("language_server", [Language.HLSL], indirect=True)
    def test_bare_symbol_names(self, language_server) -> None:
        all_symbols = request_all_symbols(language_server)
        malformed_symbols = []
        for s in all_symbols:
            if has_malformed_name(s, period_allowed=s["kind"] == SymbolKind.File):
                malformed_symbols.append(s)
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )
