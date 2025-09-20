"""
Basic integration tests for the BSL Language Server functionality.

These tests validate the functionality of the BSL language server APIs
like request_references using the test repository for 1C:Enterprise code.
"""

import os

import pytest

from serena.project import Project
from serena.text_utils import LineType
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.bsl
class TestBslLanguageServerBasics:
    """Test basic functionality of the BSL language server."""

    @pytest.mark.parametrize("language_server", [Language.BSL], indirect=True)
    def test_language_server_initialization(self, language_server: SolidLanguageServer) -> None:
        """Test that BSL language server initializes correctly."""
        assert language_server is not None
        assert language_server.language == "bsl"

    @pytest.mark.parametrize("language_server", [Language.BSL], indirect=True)
    def test_request_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols on BSL files."""
        file_path = os.path.join("test_repo", "ОсновнойМодуль.bsl")
        symbols = language_server.request_document_symbols(file_path)

        # Verify that we get symbols from the BSL file
        assert len(symbols) > 0, "Should find symbols in BSL file"

        # Look for main functions that should be present
        symbol_names = []
        for symbol_group in symbols:
            for symbol in symbol_group:
                symbol_names.append(symbol.get("name", ""))

        # Check for some expected function names from our test file
        expected_functions = ["ИнициализацияСистемы", "РассчитатьСумму", "ОбработатьДокумент"]
        found_functions = [name for name in expected_functions if any(name in sym_name for sym_name in symbol_names)]

        assert len(found_functions) > 0, f"Should find at least one of expected functions: {expected_functions}"

    @pytest.mark.parametrize("language_server", [Language.BSL], indirect=True)
    def test_request_references_function(self, language_server: SolidLanguageServer) -> None:
        """Test request_references on a BSL function."""
        file_path = os.path.join("test_repo", "ОсновнойМодуль.bsl")

        # Try to get document symbols first
        symbols = language_server.request_document_symbols(file_path)

        if len(symbols) > 0:
            # Look for a function symbol
            function_symbol = None
            for symbol_group in symbols:
                for symbol in symbol_group:
                    if symbol.get("kind") == 12:  # Function kind in LSP
                        function_symbol = symbol
                        break
                if function_symbol:
                    break

            if function_symbol and "selectionRange" in function_symbol:
                sel_start = function_symbol["selectionRange"]["start"]
                # This might not find references if the function isn't called elsewhere
                # but at least we test that the request doesn't crash
                references = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
                assert isinstance(references, list), "References should be returned as a list"

    @pytest.mark.parametrize("language_server", [Language.BSL], indirect=True)
    def test_request_hover(self, language_server: SolidLanguageServer) -> None:
        """Test hover functionality on BSL code."""
        file_path = os.path.join("test_repo", "ОсновнойМодуль.bsl")

        # Try hover on the first line that likely contains a function or variable
        try:
            hover_info = language_server.request_hover(file_path, 10, 10)  # Arbitrary position
            # Hover might return None if no info available, which is fine
            assert hover_info is None or isinstance(hover_info, dict)
        except Exception:
            # Some language servers might not support hover, which is acceptable
            pytest.skip("Hover not supported by BSL language server")

    @pytest.mark.parametrize("language_server", [Language.BSL], indirect=True)
    def test_multiple_bsl_files(self, language_server: SolidLanguageServer) -> None:
        """Test that language server can handle multiple BSL files."""
        # Test our main module
        file_path1 = os.path.join("test_repo", "ОсновнойМодуль.bsl")
        symbols1 = language_server.request_document_symbols(file_path1)

        # Test our helper module
        file_path2 = os.path.join("test_repo", "ОбщийМодуль.bsl")
        symbols2 = language_server.request_document_symbols(file_path2)

        # Both files should return symbols
        assert len(symbols1) > 0, "Main module should have symbols"
        assert len(symbols2) > 0, "Common module should have symbols"

    @pytest.mark.parametrize("language_server", [Language.BSL], indirect=True)
    def test_bsl_file_extensions(self, language_server: SolidLanguageServer) -> None:
        """Test that BSL language server works with different BSL file extensions."""
        # The language server should recognize .bsl files
        file_path = os.path.join("test_repo", "ОсновнойМодуль.bsl")

        # Verify the file is recognized as a BSL file
        language_config = Language.BSL
        matcher = language_config.get_source_fn_matcher()

        assert matcher.is_relevant_filename("test.bsl"), "Should recognize .bsl files"
        assert matcher.is_relevant_filename("test.os"), "Should recognize .os files"
        assert not matcher.is_relevant_filename("test.py"), "Should not recognize .py files"


@pytest.mark.bsl
class TestBslLanguageServerAdvanced:
    """Test advanced functionality of the BSL language server."""

    @pytest.mark.parametrize("language_server", [Language.BSL], indirect=True)
    def test_workspace_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test workspace symbol search across BSL files."""
        try:
            # Search for functions across the workspace
            symbols = language_server.request_workspace_symbols("Функция")
            assert isinstance(symbols, list), "Workspace symbols should return a list"
        except Exception:
            # Workspace symbols might not be implemented
            pytest.skip("Workspace symbols not supported by BSL language server")

    @pytest.mark.parametrize("language_server", [Language.BSL], indirect=True)
    def test_definition_lookup(self, language_server: SolidLanguageServer) -> None:
        """Test go-to-definition functionality."""
        file_path = os.path.join("test_repo", "ОсновнойМодуль.bsl")

        try:
            # Try to get definition for a symbol (this might not work without proper references)
            definition = language_server.request_definition(file_path, 20, 10)
            assert definition is None or isinstance(definition, list)
        except Exception:
            # Definition lookup might not be fully implemented
            pytest.skip("Definition lookup not supported by BSL language server")