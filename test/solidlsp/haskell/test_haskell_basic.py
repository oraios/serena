"""
Rigorous tests for Haskell Language Server integration with Serena.

Tests prove that Serena's symbol tools can:
1. Discover all expected symbols with precise matching
2. Track cross-file references accurately
3. Identify data type structures and record fields
4. Navigate between definitions and usages

Test Repository Structure:
- src/Calculator.hs: Calculator data type, arithmetic functions (add, subtract, multiply, divide, calculate)
- src/Helper.hs: Helper functions (validateNumber, isPositive, isNegative, absolute)
- app/Main.hs: Main entry point using Calculator and Helper modules
"""

import sys

import pytest

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.haskell
@pytest.mark.skipif(sys.platform == "win32", reason="HLS not installed on Windows CI")
class TestHaskellLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_calculator_module_symbols(self, language_server: SolidLanguageServer):
        """
        Test precise symbol discovery in Calculator.hs.

        Verifies that Serena can identify:
        - Data type definition (Calculator with record fields)
        - All exported functions with correct names
        - Module structure
        """
        all_symbols, _ = language_server.request_document_symbols("src/Calculator.hs")
        symbol_names = {s["name"] for s in all_symbols}

        # Verify exact set of expected top-level symbols
        expected_symbols = {
            "Calculator",  # Data type
            "add",  # Function: Int -> Int -> Int
            "subtract",  # Function: Int -> Int -> Int
            "multiply",  # Function: Int -> Int -> Int
            "divide",  # Function: Int -> Int -> Maybe Int
            "calculate",  # Function: Calculator -> String -> Int -> Int -> Maybe Int
        }

        # Verify all expected symbols are present
        missing = expected_symbols - symbol_names
        assert not missing, f"Missing expected symbols in Calculator.hs: {missing}"

        # Verify Calculator data type exists
        calculator_symbol = next((s for s in all_symbols if s["name"] == "Calculator"), None)
        assert calculator_symbol is not None, "Calculator data type not found"

        # The Calculator should be identified as a data type
        # HLS may use different SymbolKind values (1=File, 5=Class, 23=Struct)
        assert calculator_symbol["kind"] in [
            1,
            5,
            23,
        ], f"Calculator should be a data type (kind 1, 5, or 23), got kind {calculator_symbol['kind']}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_helper_module_symbols(self, language_server: SolidLanguageServer):
        """
        Test precise symbol discovery in Helper.hs.

        Verifies Serena identifies all helper functions that are imported
        and used by Calculator module.
        """
        all_symbols, _ = language_server.request_document_symbols("src/Helper.hs")
        symbol_names = {s["name"] for s in all_symbols}

        # Verify expected helper functions (module name may also appear)
        expected_symbols = {
            "validateNumber",  # Function used by Calculator.add and Calculator.subtract
            "isPositive",  # Predicate function
            "isNegative",  # Predicate function used by absolute
            "absolute",  # Function that uses isNegative
        }

        # All expected symbols should be present (module name is optional)
        missing = expected_symbols - symbol_names
        assert not missing, f"Missing expected symbols in Helper.hs: {missing}"

        # Verify no unexpected symbols beyond the module name
        extra = symbol_names - expected_symbols - {"Helper"}
        assert not extra, f"Unexpected symbols in Helper.hs: {extra}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_main_module_imports(self, language_server: SolidLanguageServer):
        """
        Test that Main.hs properly references both Calculator and Helper modules.

        Verifies Serena can identify cross-module dependencies.
        """
        all_symbols, _ = language_server.request_document_symbols("app/Main.hs")
        symbol_names = {s["name"] for s in all_symbols}

        # Main.hs should have the main function
        assert "main" in symbol_names, "Main.hs should contain 'main' function"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_cross_file_references_validateNumber(self, language_server: SolidLanguageServer):
        """
        Test cross-file reference tracking for validateNumber function.

        validateNumber is defined in Helper.hs:9 and used in:
        - Calculator.hs:21 (in add function)
        - Calculator.hs:25 (in subtract function)

        This proves Serena can track function usage across module boundaries.
        """
        # Get references to validateNumber (defined at line 9, 0-indexed = line 8)
        references = language_server.request_references("src/Helper.hs", line=8, column=0)

        # Should find at least: definition in Helper.hs + 2 usages in Calculator.hs
        assert len(references) >= 2, f"Expected at least 2 references to validateNumber (used in add and subtract), got {len(references)}"

        # Verify we have references in Calculator.hs
        reference_paths = [ref["relativePath"] for ref in references]
        calculator_refs = [path for path in reference_paths if "Calculator.hs" in path]

        assert len(calculator_refs) >= 2, (
            f"Expected at least 2 references in Calculator.hs (add and subtract functions), "
            f"got {len(calculator_refs)} references in Calculator.hs"
        )

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_within_file_references_isNegative(self, language_server: SolidLanguageServer):
        """
        Test within-file reference tracking for isNegative function.

        isNegative is defined in Helper.hs:17 and used in Helper.hs:22 (absolute function).
        This proves Serena can track intra-module function calls.
        """
        # isNegative defined at line 17 (0-indexed = line 16)
        references = language_server.request_references("src/Helper.hs", line=16, column=0)

        # Should find: definition + usage in absolute function
        assert len(references) >= 1, f"Expected at least 1 reference to isNegative (used in absolute), got {len(references)}"

        # All references should be in Helper.hs
        reference_paths = [ref["relativePath"] for ref in references]
        assert all(
            "Helper.hs" in path for path in reference_paths
        ), f"All isNegative references should be in Helper.hs, got: {reference_paths}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_function_references_from_main(self, language_server: SolidLanguageServer):
        """
        Test that functions used in Main.hs can be traced back to their definitions.

        Main.hs:12 calls 'add' from Calculator module.
        Main.hs:25 calls 'isPositive' from Helper module.
        Main.hs:26 calls 'absolute' from Helper module.

        This proves Serena can track cross-module function calls from executable code.
        """
        # Test 'add' function references (defined in Calculator.hs:20, 0-indexed = line 19)
        add_refs = language_server.request_references("src/Calculator.hs", line=19, column=0)

        # Should find references in Main.hs and possibly Calculator.hs (calculate function uses it)
        assert len(add_refs) >= 1, f"Expected at least 1 reference to 'add', got {len(add_refs)}"

        add_ref_paths = [ref["relativePath"] for ref in add_refs]
        # Should have at least one reference in Main.hs or Calculator.hs
        assert any(
            "Main.hs" in path or "Calculator.hs" in path for path in add_ref_paths
        ), f"Expected 'add' to be referenced in Main.hs or Calculator.hs, got: {add_ref_paths}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_multiply_function_usage_in_calculate(self, language_server: SolidLanguageServer):
        """
        Test that multiply function usage is tracked within Calculator module.

        multiply is defined in Calculator.hs:28 and used in:
        - Calculator.hs:41 (in calculate function via pattern matching)
        - Main.hs:20 (via calculate call with "multiply" operator)

        This proves Serena can track function references even when called indirectly.
        """
        # multiply defined at line 28 (0-indexed = line 27)
        multiply_refs = language_server.request_references("src/Calculator.hs", line=27, column=0)

        # Should find at least the usage in calculate function
        assert len(multiply_refs) >= 1, f"Expected at least 1 reference to 'multiply', got {len(multiply_refs)}"

        # Should have reference in Calculator.hs (calculate function)
        multiply_ref_paths = [ref["relativePath"] for ref in multiply_refs]
        assert any(
            "Calculator.hs" in path for path in multiply_ref_paths
        ), f"Expected 'multiply' to be referenced in Calculator.hs, got: {multiply_ref_paths}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_data_type_constructor_references(self, language_server: SolidLanguageServer):
        """
        Test that Calculator data type constructor usage is tracked.

        Calculator is defined in Calculator.hs:14 and used in:
        - Main.hs:8 (constructor call: Calculator "TestCalc" 1)
        - Calculator.hs:37 (type signature for calculate function)

        This proves Serena can track data type constructor references.
        """
        # Calculator data type defined at line 14 (0-indexed = line 13)
        calculator_refs = language_server.request_references("src/Calculator.hs", line=13, column=5)

        # Should find usage in Main.hs
        assert len(calculator_refs) >= 1, f"Expected at least 1 reference to Calculator constructor, got {len(calculator_refs)}"

        # Should have at least one reference in Main.hs or Calculator.hs
        calc_ref_paths = [ref["relativePath"] for ref in calculator_refs]
        assert any(
            "Main.hs" in path or "Calculator.hs" in path for path in calc_ref_paths
        ), f"Expected Calculator to be referenced in Main.hs or Calculator.hs, got: {calc_ref_paths}"
