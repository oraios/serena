"""
Basic tests for Fortran language server integration.

Note: These tests require fortls to be installed: pip install fortls
"""

import os

import pytest

from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings

# Mark all tests in this module as fortran tests
pytestmark = pytest.mark.fortran


@pytest.fixture
def fortran_repo_path():
    """Get the path to the Fortran test repository."""
    test_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(test_dir, "resources", "repos", "fortran", "test_repo")


@pytest.fixture
def fortran_ls(fortran_repo_path):
    """Create and initialize a Fortran language server instance."""
    config = LanguageServerConfig(code_language=Language.FORTRAN)
    logger = LanguageServerLogger()
    settings = SolidLSPSettings()

    # Import here to avoid import errors if fortls is not installed
    from solidlsp.language_servers.fortran_language_server import FortranLanguageServer

    ls = FortranLanguageServer(config, logger, fortran_repo_path, settings)
    ls.start()  # Start the language server
    yield ls
    ls.stop()


def test_fortran_ls_initialization(fortran_ls):
    """Test that the Fortran language server initializes correctly."""
    assert fortran_ls is not None
    assert fortran_ls.server_ready.is_set()


def test_find_module_symbol(fortran_ls):
    """Test finding a module symbol in Fortran code."""
    all_symbols, root_symbols = fortran_ls.request_document_symbols("lib/math_utils.f90")

    # Find module symbols (LSP kind 2 is Module)
    module_names = [s.get("name") for s in all_symbols if s.get("kind") == 2]

    assert "math_utils" in module_names, f"Module 'math_utils' not found. Found symbols: {[s.get('name') for s in all_symbols]}"


def test_find_function_symbols(fortran_ls):
    """Test finding function symbols in Fortran code."""
    all_symbols, root_symbols = fortran_ls.request_document_symbols("lib/math_utils.f90")

    # Find function symbols (LSP kind 12 is Function)
    function_names = [s.get("name") for s in all_symbols if s.get("kind") == 12]

    assert "add_numbers" in function_names, f"Function 'add_numbers' not found. Found functions: {function_names}"
    assert "multiply_numbers" in function_names, f"Function 'multiply_numbers' not found. Found functions: {function_names}"


def test_find_subroutine_symbols(fortran_ls):
    """Test finding subroutine symbols in Fortran code."""
    all_symbols, root_symbols = fortran_ls.request_document_symbols("lib/math_utils.f90")

    # Find function symbols (subroutines are also kind 12 in LSP)
    symbol_names = [s.get("name") for s in all_symbols if s.get("kind") == 12]

    assert "print_result" in symbol_names, f"Subroutine 'print_result' not found. Found symbols: {symbol_names}"


def test_find_program_symbol(fortran_ls):
    """Test finding a program symbol in Fortran code."""
    all_symbols, root_symbols = fortran_ls.request_document_symbols("main.f90")

    # Find all symbol names
    all_names = [s.get("name") for s in all_symbols]

    assert "test_program" in all_names, f"Program 'test_program' not found. Found symbols: {all_names}"


def test_cross_file_module_usage(fortran_ls):
    """Test that the language server can detect cross-file module usage."""
    # Open both files to ensure they're indexed
    fortran_ls.open_file("main.f90")
    fortran_ls.open_file("lib/math_utils.f90")

    # Get symbols from main.f90
    all_symbols, root_symbols = fortran_ls.request_document_symbols("main.f90")

    # The main program should be detected
    program_names = [s.get("name") for s in all_symbols]
    assert "test_program" in program_names, f"Program not found in main.f90. Found: {program_names}"
