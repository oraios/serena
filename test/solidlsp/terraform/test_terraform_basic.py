"""
Basic integration tests for the Terraform language server functionality.

These tests validate the functionality of the language server APIs
like request_references using the test repository.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.terraform
class TestLanguageServerBasics:
    """Test basic functionality of the Terraform language server."""

    @pytest.mark.parametrize("language_server", [Language.TERRAFORM], indirect=True)
    def test_basic_definition(self, language_server: SolidLanguageServer) -> None:
        """Test basic definition lookup functionality."""
        # Simple test to verify the language server is working
        file_path = "main.tf"
        # Just try to get document symbols - this should work without hanging
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        assert len(symbols) > 0, "Should find at least some symbols in main.tf"

    @pytest.mark.parametrize("language_server", [Language.TERRAFORM], indirect=True)
    def test_request_references_aws_instance(self, language_server: SolidLanguageServer) -> None:
        """Test request_references on an aws_instance resource."""
        # Get references to an aws_instance resource in main.tf
        file_path = "main.tf"
        # Find aws_instance resources
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        aws_instance_symbol = next((s for s in symbols[0] if s.get("name") == 'resource "aws_instance" "web_server"'), None)
        if not aws_instance_symbol or "selectionRange" not in aws_instance_symbol:
            raise AssertionError("aws_instance symbol or its selectionRange not found")
        sel_start = aws_instance_symbol["selectionRange"]["start"]
        references = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert len(references) >= 1, "aws_instance should be referenced at least once"

    @pytest.mark.parametrize("language_server", [Language.TERRAFORM], indirect=True)
    def test_request_references_variable(self, language_server: SolidLanguageServer) -> None:
        """Test request_references on a variable."""
        # Get references to a variable in variables.tf
        file_path = "variables.tf"
        # Find variable definitions
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        var_symbol = next((s for s in symbols[0] if s.get("name") == 'variable "instance_type"'), None)
        if not var_symbol or "selectionRange" not in var_symbol:
            raise AssertionError("variable symbol or its selectionRange not found")
        sel_start = var_symbol["selectionRange"]["start"]
        references = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert len(references) >= 1, "variable should be referenced at least once"
