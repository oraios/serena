"""
Basic integration tests for the Gleam language server.

These tests validate startup, document symbols, same-file and cross-file
reference search, and diagnostics, using the Gleam test repository at
``test/resources/repos/gleam/test_repo``.

Requires the ``gleam`` compiler on PATH (the language server is bundled with it
and started via ``gleam lsp``).
"""

import os
from pathlib import Path

import pytest

from serena.util.text_utils import find_text_coordinates
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_utils import SymbolUtils
from test.conftest import language_server_tests_enabled
from test.solidlsp.conftest import read_repo_file
from test.solidlsp.util.diagnostics import assert_file_diagnostics

pytestmark = [
    pytest.mark.gleam,
    pytest.mark.skipif(
        not language_server_tests_enabled(LanguageServerId.GLEAM),
        reason="Gleam tests are disabled (gleam compiler not available)",
    ),
]


class TestGleamLanguageServer:
    """Test Gleam language server startup and basic features."""

    @pytest.mark.parametrize("language_server", [LanguageServerId.GLEAM], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer) -> None:
        """The language server starts successfully."""
        assert language_server.is_running()

    @pytest.mark.parametrize("language_server", [LanguageServerId.GLEAM], indirect=True)
    def test_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Document symbols for calculator.gleam include the public functions and the type."""
        file_path = os.path.join("src", "calculator.gleam")
        doc_symbols = language_server.request_document_symbols(file_path)
        all_symbols, _ = doc_symbols.get_all_symbols_and_roots()

        names = {s.get("name") for s in all_symbols if s.get("name")}
        assert "add" in names, f"'add' missing from calculator.gleam symbols: {names}"
        assert "subtract" in names, f"'subtract' missing: {names}"
        assert "multiply" in names, f"'multiply' missing: {names}"
        assert "Calculator" in names, f"'Calculator' type missing: {names}"
        assert "demo" in names, f"'demo' missing: {names}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.GLEAM], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        """The full project symbol tree includes symbols from both modules.

        ``find_symbol`` (serena's most-used tool) is backed by ``request_full_symbol_tree``;
        verify it sees public symbols from calculator.gleam and utils.gleam across files.
        """
        symbols = language_server.request_full_symbol_tree()
        # calculator.gleam symbols
        assert SymbolUtils.symbol_tree_contains_name(symbols, "add"), "calculator 'add' missing from symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Calculator"), "Calculator type missing from symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "demo"), "calculator 'demo' missing from symbol tree"
        # utils.gleam symbols (cross-file)
        assert SymbolUtils.symbol_tree_contains_name(symbols, "format_output"), "utils 'format_output' missing from symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "is_non_empty"), "utils 'is_non_empty' missing from symbol tree"

    @pytest.mark.parametrize("language_server", [LanguageServerId.GLEAM], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.GLEAM], indirect=True)
    def test_find_references_within_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """References to ``add`` include its call site in ``demo`` (same file).

        ``add`` is defined in calculator.gleam and called once in ``demo``; both the
        declaration and the call site should be returned by ``request_references``.
        """
        rel = os.path.join("src", "calculator.gleam")
        file_path = str(repo_path / rel)
        content = read_repo_file(language_server, rel)

        coords = find_text_coordinates(content, r"pub fn (add)\(")
        assert coords is not None, "Could not locate `pub fn add` definition in calculator.gleam"

        references = language_server.request_references(file_path, coords.line, coords.col + 1)
        assert references, f"Expected non-empty references for add, got {references=}"

        ref_files = {loc["uri"].split("/")[-1] for loc in references}
        assert "calculator.gleam" in ref_files, f"Expected reference in calculator.gleam, got {ref_files}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.GLEAM], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.GLEAM], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Cross-file references: ``format_output`` (defined in utils.gleam) is called in calculator.gleam."""
        rel = os.path.join("src", "utils.gleam")
        file_path = str(repo_path / rel)
        content = read_repo_file(language_server, rel)

        coords = find_text_coordinates(content, r"pub fn (format_output)\(")
        assert coords is not None, "Could not locate `pub fn format_output` definition in utils.gleam"

        references = language_server.request_references(file_path, coords.line, coords.col + 1)
        assert references, f"Expected non-empty references for format_output, got {references=}"

        ref_files = {loc["uri"].split("/")[-1] for loc in references}
        assert "calculator.gleam" in ref_files, f"Expected cross-file reference in calculator.gleam, got {ref_files}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.GLEAM], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        """diagnostics_sample.gleam references an undefined symbol; the LSP should report it."""
        assert_file_diagnostics(
            language_server,
            os.path.join("src", "diagnostics_sample.gleam"),
            (),
            min_count=1,
        )
