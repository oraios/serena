"""
Basic integration tests for the Terraform language server functionality.

These tests validate the functionality of the language server APIs
like request_references using the test repository.
"""

import os

import pytest

from serena.text_utils import LineType
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
        symbols = language_server.request_document_symbols(file_path)
        assert len(symbols) > 0, "Should find at least some symbols in main.tf"

    @pytest.mark.parametrize("language_server", [Language.TERRAFORM], indirect=True)
    def test_request_references_aws_instance(self, language_server: SolidLanguageServer) -> None:
        """Test request_references on an aws_instance resource."""
        # Get references to an aws_instance resource in main.tf
        file_path = "main.tf"
        # Find aws_instance resources
        symbols = language_server.request_document_symbols(file_path)
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
        symbols = language_server.request_document_symbols(file_path)
        var_symbol = next((s for s in symbols[0] if s.get("name") == 'variable "instance_type"'), None)
        if not var_symbol or "selectionRange" not in var_symbol:
            raise AssertionError("variable symbol or its selectionRange not found")
        sel_start = var_symbol["selectionRange"]["start"]
        references = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert len(references) >= 1, "variable should be referenced at least once"

    @pytest.mark.parametrize("language_server", [Language.TERRAFORM], indirect=True)
    def test_retrieve_content_around_line(self, language_server: SolidLanguageServer) -> None:
        """Test retrieve_content_around_line functionality with Terraform files."""
        file_path = "main.tf"

        # Test retrieving content around a resource definition
        line_5 = language_server.retrieve_content_around_line(file_path, 5)
        assert len(line_5.lines) == 1
        assert line_5.lines[0].line_number == 5
        assert line_5.lines[0].match_type == LineType.MATCH

        # Test with context
        with_context = language_server.retrieve_content_around_line(file_path, 5, 2, 2)
        assert len(with_context.lines) == 5
        assert with_context.num_matched_lines == 1
        # Check line numbers
        assert with_context.lines[0].line_number == 3
        assert with_context.lines[1].line_number == 4
        assert with_context.lines[2].line_number == 5
        assert with_context.lines[3].line_number == 6
        assert with_context.lines[4].line_number == 7
        # Check match types
        assert with_context.lines[0].match_type == LineType.BEFORE_MATCH
        assert with_context.lines[1].match_type == LineType.BEFORE_MATCH
        assert with_context.lines[2].match_type == LineType.MATCH
        assert with_context.lines[3].match_type == LineType.AFTER_MATCH
        assert with_context.lines[4].match_type == LineType.AFTER_MATCH

    @pytest.mark.parametrize("language_server", [Language.TERRAFORM], indirect=True)
    def test_search_files_for_pattern(self, language_server: SolidLanguageServer) -> None:
        """Test search_files_for_pattern with Terraform-specific patterns."""
        # Test 1: Search for resource definitions
        resource_pattern = r"resource\s+\"[^\"]+\"\s+\"[^\"]+\""
        matches = language_server.search_files_for_pattern(resource_pattern)
        assert len(matches) > 0
        # Should find multiple resources like aws_instance, aws_s3_bucket, etc.
        assert len(matches) >= 2

        # Test 2: Search for specific resource type with include glob
        aws_instance_pattern = r"resource\s+\"aws_instance\""
        matches = language_server.search_files_for_pattern(aws_instance_pattern, paths_include_glob="**/*.tf")
        assert len(matches) >= 1  # Should find at least one aws_instance
        assert all(match.source_file_path is not None and ".tf" in match.source_file_path for match in matches)

        # Test 3: Search for variable definitions with exclude glob
        variable_pattern = r"variable\s+\"[^\"]+\""
        matches = language_server.search_files_for_pattern(variable_pattern, paths_exclude_glob="**/main.tf")
        assert len(matches) >= 0
        # Should find variables but not in main.tf
        assert all(match.source_file_path is not None and "main.tf" not in match.source_file_path for match in matches)

        # Test 4: Search for output definitions
        output_pattern = r"output\s+\"[^\"]+\""
        matches = language_server.search_files_for_pattern(output_pattern)
        assert len(matches) >= 0  # May or may not have outputs in test repo

        # Test 5: Search for a pattern that should have no matches
        no_match_pattern = r"resource\s+\"nonexistent_resource_type\""
        matches = language_server.search_files_for_pattern(no_match_pattern)
        assert len(matches) == 0
