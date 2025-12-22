"""
Basic integration tests for the YAML language server functionality.

These tests validate the functionality of the language server APIs
like request_document_symbols using the YAML test repository.
"""

from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.yaml
class TestYAMLLanguageServerBasics:
    """Test basic functionality of the YAML language server."""

    @pytest.mark.parametrize("language_server", [Language.YAML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.YAML], indirect=True)
    def test_yaml_language_server_initialization(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that YAML language server can be initialized successfully."""
        assert language_server is not None
        assert language_server.language == Language.YAML
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.YAML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.YAML], indirect=True)
    def test_yaml_config_file_symbols(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test document symbols detection in config.yaml with specific symbol verification."""
        all_symbols, root_symbols = language_server.request_document_symbols("config.yaml").get_all_symbols_and_roots()

        assert all_symbols is not None, "Should return symbols for config.yaml"
        assert len(all_symbols) > 0, f"Should find symbols in config.yaml, found {len(all_symbols)}"

        # Verify specific top-level keys are detected
        symbol_names = [sym.get("name") for sym in all_symbols]
        assert "app" in symbol_names, "Should detect 'app' key in config.yaml"
        assert "database" in symbol_names, "Should detect 'database' key in config.yaml"
        assert "logging" in symbol_names, "Should detect 'logging' key in config.yaml"
        assert "features" in symbol_names, "Should detect 'features' key in config.yaml"

        # Verify nested symbols exist (child keys under 'app')
        assert "name" in symbol_names, "Should detect nested 'name' key"
        assert "port" in symbol_names, "Should detect nested 'port' key"
        assert "debug" in symbol_names, "Should detect nested 'debug' key"

        # Check symbol kinds are appropriate (LSP kinds: 2=module/namespace, 15=string, 16=number, 17=boolean)
        app_symbol = next((s for s in all_symbols if s.get("name") == "app"), None)
        assert app_symbol is not None, "Should find 'app' symbol"
        assert app_symbol.get("kind") == 2, "Top-level object should have kind 2 (module/namespace)"

        port_symbol = next((s for s in all_symbols if s.get("name") == "port"), None)
        assert port_symbol is not None, "Should find 'port' symbol"
        assert port_symbol.get("kind") == 16, "'port' should have kind 16 (number)"

        debug_symbol = next((s for s in all_symbols if s.get("name") == "debug"), None)
        assert debug_symbol is not None, "Should find 'debug' symbol"
        assert debug_symbol.get("kind") == 17, "'debug' should have kind 17 (boolean)"

    @pytest.mark.parametrize("language_server", [Language.YAML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.YAML], indirect=True)
    def test_yaml_services_file_symbols(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test symbol detection in services.yml Docker Compose file."""
        all_symbols, root_symbols = language_server.request_document_symbols("services.yml").get_all_symbols_and_roots()

        assert all_symbols is not None, "Should return symbols for services.yml"
        assert len(all_symbols) > 0, f"Should find symbols in services.yml, found {len(all_symbols)}"

        # Verify specific top-level keys from Docker Compose file
        symbol_names = [sym.get("name") for sym in all_symbols]
        assert "version" in symbol_names, "Should detect 'version' key"
        assert "services" in symbol_names, "Should detect 'services' key"
        assert "networks" in symbol_names, "Should detect 'networks' key"
        assert "volumes" in symbol_names, "Should detect 'volumes' key"

        # Verify service names
        assert "web" in symbol_names, "Should detect 'web' service"
        assert "api" in symbol_names, "Should detect 'api' service"
        assert "database" in symbol_names, "Should detect 'database' service"

        # Check that arrays are properly detected
        ports_symbols = [s for s in all_symbols if s.get("name") == "ports"]
        assert len(ports_symbols) > 0, "Should find 'ports' arrays in services"
        # Arrays should have kind 18
        for ports_sym in ports_symbols:
            assert ports_sym.get("kind") == 18, "'ports' should have kind 18 (array)"

    @pytest.mark.parametrize("language_server", [Language.YAML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.YAML], indirect=True)
    def test_yaml_data_file_symbols(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test symbol detection in data.yaml file with array structures."""
        all_symbols, root_symbols = language_server.request_document_symbols("data.yaml").get_all_symbols_and_roots()

        assert all_symbols is not None, "Should return symbols for data.yaml"
        assert len(all_symbols) > 0, f"Should find symbols in data.yaml, found {len(all_symbols)}"

        # Verify top-level keys
        symbol_names = [sym.get("name") for sym in all_symbols]
        assert "users" in symbol_names, "Should detect 'users' array"
        assert "projects" in symbol_names, "Should detect 'projects' array"

        # Verify array elements (indexed by position)
        # data.yaml has user entries and project entries
        assert "id" in symbol_names, "Should detect 'id' fields in array elements"
        assert "name" in symbol_names, "Should detect 'name' fields"
        assert "email" in symbol_names, "Should detect 'email' fields"
        assert "roles" in symbol_names, "Should detect 'roles' arrays"

    @pytest.mark.parametrize("language_server", [Language.YAML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.YAML], indirect=True)
    def test_yaml_symbols_with_body(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test request_document_symbols with body extraction."""
        all_symbols, root_symbols = language_server.request_document_symbols("config.yaml").get_all_symbols_and_roots()

        assert all_symbols is not None, "Should return symbols for config.yaml"
        assert len(all_symbols) > 0, "Should have symbols"

        # Find the 'app' symbol and verify its body
        app_symbol = next((s for s in all_symbols if s.get("name") == "app"), None)
        assert app_symbol is not None, "Should find 'app' symbol"

        # Check that body exists and contains expected content
        assert "body" in app_symbol, "'app' symbol should have body"
        app_body = app_symbol["body"]
        assert "app:" in app_body, "Body should start with 'app:'"
        assert "name: test-application" in app_body, "Body should contain 'name' field"
        assert "version: 1.0.0" in app_body, "Body should contain 'version' field"
        assert "port: 8080" in app_body, "Body should contain 'port' field"
        assert "debug: true" in app_body, "Body should contain 'debug' field"

        # Find a simple string value symbol and verify its body
        name_symbols = [s for s in all_symbols if s.get("name") == "name" and "body" in s]
        assert len(name_symbols) > 0, "Should find 'name' symbols with bodies"
        # At least one should contain "test-application"
        assert any("test-application" in s["body"] for s in name_symbols), "Should find name with test-application"

        # Find the database symbol and check its body
        database_symbol = next((s for s in all_symbols if s.get("name") == "database"), None)
        assert database_symbol is not None, "Should find 'database' symbol"
        assert "body" in database_symbol, "'database' symbol should have body"
        db_body = database_symbol["body"]
        assert "database:" in db_body, "Body should start with 'database:'"
        assert "host: localhost" in db_body, "Body should contain host configuration"
        assert "port: 5432" in db_body, "Body should contain port configuration"

    @pytest.mark.parametrize("language_server", [Language.YAML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.YAML], indirect=True)
    def test_yaml_symbol_ranges(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that symbols have proper range information."""
        all_symbols, root_symbols = language_server.request_document_symbols("config.yaml").get_all_symbols_and_roots()

        assert all_symbols is not None
        assert len(all_symbols) > 0

        # Check the 'app' symbol range
        app_symbol = next((s for s in all_symbols if s.get("name") == "app"), None)
        assert app_symbol is not None, "Should find 'app' symbol"
        assert "range" in app_symbol, "'app' symbol should have range"

        app_range = app_symbol["range"]
        assert "start" in app_range, "Range should have start"
        assert "end" in app_range, "Range should have end"
        assert app_range["start"]["line"] == 1, "'app' should start at line 1 (0-indexed, actual line 2)"
        # The app block spans from line 2 to line 7 in the file (1-indexed)
        # In 0-indexed LSP coordinates: line 1 (start) to line 6 (end)
        assert app_range["end"]["line"] == 6, "'app' should end at line 6 (0-indexed)"

        # Check a nested symbol range
        port_symbols = [s for s in all_symbols if s.get("name") == "port"]
        assert len(port_symbols) > 0, "Should find 'port' symbols"
        # Find the one under 'app' (should be at line 4 in 0-indexed, actual line 5)
        app_port = next((s for s in port_symbols if s["range"]["start"]["line"] == 4), None)
        assert app_port is not None, "Should find 'port' under 'app'"
        assert app_port["range"]["start"]["character"] == 2, "'port' should be indented 2 spaces"
