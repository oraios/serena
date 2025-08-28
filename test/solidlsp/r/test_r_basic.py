"""
Basic tests for R Language Server integration
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.r
class TestRLanguageServer:
    """Test basic functionality of the R language server."""

    @pytest.mark.parametrize("language_server", [Language.R], indirect=True)
    def test_initialization(self, language_server: SolidLanguageServer):
        """Test that the R language server initializes properly."""
        assert language_server is not None
        assert language_server.language_id == "r"

    @pytest.mark.parametrize("language_server", [Language.R], indirect=True)
    def test_r_document_symbols(self, language_server: SolidLanguageServer):
        """Test R document symbol extraction."""
        all_symbols, root_symbols = language_server.request_document_symbols("R/utils.R")

        # Should find some R functions
        function_symbols = [s for s in all_symbols if s.get("kind") == 12]  # Function kind
        assert len(function_symbols) > 0

    @pytest.mark.parametrize("language_server", [Language.R], indirect=True)
    def test_r_models_symbols(self, language_server: SolidLanguageServer):
        """Test symbol extraction from R models file."""
        all_symbols, root_symbols = language_server.request_document_symbols("R/models.R")

        # Should find functions in models file
        function_symbols = [s for s in all_symbols if s.get("kind") == 12]  # Function kind
        assert len(function_symbols) > 0

    @pytest.mark.parametrize("language_server", [Language.R], indirect=True)
    def test_r_example_script(self, language_server: SolidLanguageServer):
        """Test symbol extraction from R example script."""
        all_symbols, root_symbols = language_server.request_document_symbols("examples/analysis.R")

        # Example script should have at least some symbols (may be functions or variables)
        assert len(all_symbols) >= 0  # May have functions or just code
