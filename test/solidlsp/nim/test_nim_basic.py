"""
Basic integration tests for Nim language server functionality.

These tests validate symbol finding and cross-file reference capabilities
using nimlangserver (https://github.com/nim-lang/langserver).

Test Repository Structure:
- src/calculator.nim: Basic arithmetic procedures (add, subtract, multiply, divide, factorial, power)
- src/utils.nim: String utility procedures (trim, startsWith, endsWith, split, join)
- main.nim: Entry point using calculator and utils modules
"""

import shutil

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.nim
@pytest.mark.skipif(shutil.which("nimlangserver") is None, reason="nimlangserver not installed")
class TestNimLanguageServer:
    """Test Nim language server symbol finding and cross-file reference capabilities."""

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_find_symbols_in_calculator(self, language_server: SolidLanguageServer) -> None:
        """Test finding procedures in src/calculator.nim."""
        all_symbols, _ = language_server.request_document_symbols("src/calculator.nim").get_all_symbols_and_roots()

        assert all_symbols is not None
        assert len(all_symbols) > 0

        symbol_names = {s["name"] for s in all_symbols if isinstance(s, dict)}

        # Verify exact set of expected procedures
        expected_procs = {"add", "subtract", "multiply", "divide", "factorial", "power"}
        missing = expected_procs - symbol_names
        assert not missing, f"Missing expected procedures in calculator.nim: {missing}"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_find_symbols_in_utils(self, language_server: SolidLanguageServer) -> None:
        """Test finding procedures in src/utils.nim."""
        all_symbols, _ = language_server.request_document_symbols("src/utils.nim").get_all_symbols_and_roots()

        assert all_symbols is not None
        assert len(all_symbols) > 0

        symbol_names = {s["name"] for s in all_symbols if isinstance(s, dict)}

        # Verify exact set of expected utility functions
        expected_procs = {"trim", "startsWith", "endsWith", "split", "join"}
        missing = expected_procs - symbol_names
        assert not missing, f"Missing expected procedures in utils.nim: {missing}"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_find_symbols_in_main(self, language_server: SolidLanguageServer) -> None:
        """Test finding procedures in main.nim."""
        all_symbols, _ = language_server.request_document_symbols("main.nim").get_all_symbols_and_roots()

        assert all_symbols is not None
        assert len(all_symbols) > 0

        symbol_names = {s["name"] for s in all_symbols if isinstance(s, dict)}

        # Verify expected procedures in main.nim
        expected_procs = {"printBanner", "testCalculator", "testUtils"}
        missing = expected_procs - symbol_names
        assert not missing, f"Missing expected procedures in main.nim: {missing}"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_cross_file_references_calculator_add(self, language_server: SolidLanguageServer) -> None:
        """Test finding cross-file references to calculator.add."""
        all_symbols, _ = language_server.request_document_symbols("src/calculator.nim").get_all_symbols_and_roots()

        assert all_symbols is not None

        # Find the add procedure
        add_symbol = next((s for s in all_symbols if isinstance(s, dict) and s.get("name") == "add"), None)
        assert add_symbol is not None, "add procedure not found in calculator.nim"

        range_info = add_symbol.get("selectionRange", add_symbol.get("range"))
        assert range_info is not None, "add procedure has no range information"

        range_start = range_info["start"]
        refs = language_server.request_references("src/calculator.nim", range_start["line"], range_start["character"])

        assert refs is not None
        assert isinstance(refs, list)
        # add is called in main.nim (testCalculator procedure)
        assert len(refs) >= 1, f"Should find at least 1 reference to calculator.add, found {len(refs)}"

        # Verify cross-file references from main.nim
        main_refs = [ref for ref in refs if "main.nim" in ref.get("uri", "")]
        assert len(main_refs) >= 1, "calculator.add should be referenced in main.nim"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_cross_file_references_utils_trim(self, language_server: SolidLanguageServer) -> None:
        """Test finding cross-file references to utils.trim."""
        all_symbols, _ = language_server.request_document_symbols("src/utils.nim").get_all_symbols_and_roots()

        assert all_symbols is not None

        # Find the trim procedure
        trim_symbol = next((s for s in all_symbols if isinstance(s, dict) and s.get("name") == "trim"), None)
        assert trim_symbol is not None, "trim procedure not found in utils.nim"

        range_info = trim_symbol.get("selectionRange", trim_symbol.get("range"))
        assert range_info is not None, "trim procedure has no range information"

        range_start = range_info["start"]
        refs = language_server.request_references("src/utils.nim", range_start["line"], range_start["character"])

        assert refs is not None
        assert isinstance(refs, list)
        # trim is called in main.nim (testUtils procedure)
        assert len(refs) >= 1, f"Should find at least 1 reference to utils.trim, found {len(refs)}"

        # Verify cross-file references from main.nim
        main_refs = [ref for ref in refs if "main.nim" in ref.get("uri", "")]
        assert len(main_refs) >= 1, "utils.trim should be referenced in main.nim"
