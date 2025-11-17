"""
Basic integration tests for the YAML language server functionality.

These tests validate the functionality of the language server APIs
like request_document_symbols using the YAML test repository.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.yaml
class TestYAMLLanguageServerBasics:
    """Test basic functionality of the YAML language server."""

    @pytest.mark.parametrize("language_server", [Language.YAML], indirect=True)
    def test_yaml_language_server_initialization(self, language_server: SolidLanguageServer) -> None:
        """Test that YAML language server can be initialized successfully."""
        assert language_server is not None
        assert language_server.language == Language.YAML

    @pytest.mark.parametrize("language_server", [Language.YAML], indirect=True)
    def test_yaml_request_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols for YAML files."""
        # Test getting symbols from config.yaml
        all_symbols, _root_symbols = language_server.request_document_symbols("config.yaml", include_body=False)

        # YAML language server provides document symbols
        # The structure depends on what the language server returns
        assert all_symbols is not None, "Should return symbols for config.yaml"
        assert len(all_symbols) > 0, f"Should find symbols in config.yaml, found {len(all_symbols)}"

    @pytest.mark.parametrize("language_server", [Language.YAML], indirect=True)
    def test_yaml_services_file(self, language_server: SolidLanguageServer) -> None:
        """Test symbol detection in services.yml file."""
        # Test with services.yml
        all_symbols, _root_symbols = language_server.request_document_symbols("services.yml", include_body=False)

        assert all_symbols is not None, "Should return symbols for services.yml"
        assert len(all_symbols) > 0, f"Should find symbols in services.yml, found {len(all_symbols)}"

    @pytest.mark.parametrize("language_server", [Language.YAML], indirect=True)
    def test_yaml_data_file(self, language_server: SolidLanguageServer) -> None:
        """Test symbol detection in data.yaml file."""
        # Test with data.yaml
        all_symbols, _root_symbols = language_server.request_document_symbols("data.yaml", include_body=False)

        assert all_symbols is not None, "Should return symbols for data.yaml"
        assert len(all_symbols) > 0, f"Should find symbols in data.yaml, found {len(all_symbols)}"

    @pytest.mark.parametrize("language_server", [Language.YAML], indirect=True)
    def test_yaml_request_document_symbols_with_body(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols with body extraction."""
        # Test with include_body=True
        all_symbols, _root_symbols = language_server.request_document_symbols("config.yaml", include_body=True)

        assert all_symbols is not None, "Should return symbols for config.yaml"
        # The YAML language server may or may not support body extraction
        # This test just ensures it doesn't crash when requesting bodies
