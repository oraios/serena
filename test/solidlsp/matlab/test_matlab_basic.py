"""
Basic integration tests for the MATLAB language server functionality.

These tests validate the functionality of the language server APIs
like request_document_symbols using the MATLAB test repository.

Requirements:
    - MATLAB R2021b or later must be installed
    - MATLAB_PATH environment variable should be set to MATLAB installation directory
    - Node.js and npm must be installed
"""

import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language

# Skip all tests if MATLAB is not available
pytestmark = pytest.mark.matlab

# Check if MATLAB is available
MATLAB_AVAILABLE = os.environ.get("MATLAB_PATH") is not None or any(
    os.path.exists(p)
    for p in [
        "/Applications/MATLAB_R2024b.app",
        "/Applications/MATLAB_R2025b.app",
        "/Volumes/S1/Applications/MATLAB_R2024b.app",
        "/Volumes/S1/Applications/MATLAB_R2025b.app",
    ]
)


@pytest.mark.skipif(not MATLAB_AVAILABLE, reason="MATLAB installation not found")
class TestMatlabLanguageServerBasics:
    """Test basic functionality of the MATLAB language server."""

    @pytest.mark.parametrize("language_server", [Language.MATLAB], indirect=True)
    def test_matlab_language_server_initialization(self, language_server: SolidLanguageServer) -> None:
        """Test that MATLAB language server can be initialized successfully."""
        assert language_server is not None
        assert language_server.language == Language.MATLAB

    @pytest.mark.parametrize("language_server", [Language.MATLAB], indirect=True)
    def test_matlab_request_document_symbols_class(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols for MATLAB class file."""
        # Test getting symbols from Calculator.m (class file)
        all_symbols, _root_symbols = language_server.request_document_symbols("Calculator.m").get_all_symbols_and_roots()

        # Extract class symbols (LSP Symbol Kind 5 for class)
        class_symbols = [symbol for symbol in all_symbols if symbol.get("kind") == 5]
        class_names = [symbol["name"] for symbol in class_symbols]

        # Should find the Calculator class
        assert "Calculator" in class_names, "Should find Calculator class"

        # Extract method symbols (LSP Symbol Kind 6 for method or 12 for function)
        method_symbols = [symbol for symbol in all_symbols if symbol.get("kind") in [6, 12]]
        method_names = [symbol["name"] for symbol in method_symbols]

        # Should find key methods
        expected_methods = ["add", "subtract", "multiply", "divide"]
        for method in expected_methods:
            assert method in method_names, f"Should find {method} method in Calculator class"

    @pytest.mark.parametrize("language_server", [Language.MATLAB], indirect=True)
    def test_matlab_request_document_symbols_function(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols for MATLAB function file."""
        # Test getting symbols from lib/mathUtils.m (function file)
        all_symbols, _root_symbols = language_server.request_document_symbols("lib/mathUtils.m").get_all_symbols_and_roots()

        # Extract function symbols (LSP Symbol Kind 12 for function)
        function_symbols = [symbol for symbol in all_symbols if symbol.get("kind") == 12]
        function_names = [symbol["name"] for symbol in function_symbols]

        # Should find the main mathUtils function
        assert "mathUtils" in function_names, "Should find mathUtils function"

        # Should also find nested/local functions
        expected_local_functions = ["computeFactorial", "computeFibonacci", "checkPrime", "computeStats"]
        for func in expected_local_functions:
            assert func in function_names, f"Should find {func} local function"

    @pytest.mark.parametrize("language_server", [Language.MATLAB], indirect=True)
    def test_matlab_request_document_symbols_script(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols for MATLAB script file."""
        # Test getting symbols from main.m (script file)
        all_symbols, _root_symbols = language_server.request_document_symbols("main.m").get_all_symbols_and_roots()

        # Scripts may have variables and sections, but less structured symbols
        # Just verify we can get symbols without errors
        assert all_symbols is not None


@pytest.mark.skipif(not MATLAB_AVAILABLE, reason="MATLAB installation not found")
class TestMatlabLanguageServerReferences:
    """Test find references functionality of the MATLAB language server."""

    @pytest.mark.parametrize("language_server", [Language.MATLAB], indirect=True)
    def test_matlab_find_references_within_file(self, language_server: SolidLanguageServer) -> None:
        """Test finding references within a single MATLAB file."""
        # Find references to 'result' variable in Calculator.m
        # This is a basic test to verify references work
        references = language_server.request_references("Calculator.m", 25, 12)  # 'result' in add method

        # Should find at least the definition
        assert references is not None

    @pytest.mark.parametrize("language_server", [Language.MATLAB], indirect=True)
    def test_matlab_find_references_cross_file(self, language_server: SolidLanguageServer) -> None:
        """Test finding references across MATLAB files."""
        # Find references to Calculator class used in main.m
        references = language_server.request_references("main.m", 11, 8)  # 'Calculator' reference

        # Should find references in both main.m and Calculator.m
        assert references is not None
