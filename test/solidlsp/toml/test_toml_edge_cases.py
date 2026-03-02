"""
Tests for TOML language server edge cases and advanced features.

These tests cover:
- Inline tables
- Multiline strings
- Arrays of tables
- Nested tables
- Various TOML data types
"""

from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language

pytestmark = pytest.mark.toml


class TestTomlEdgeCases:
    """Test TOML language server handling of edge cases and advanced features."""

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_inline_table_detection(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that inline tables are properly detected."""
        all_symbols, root_symbols = language_server.request_document_symbols("config.toml").get_all_symbols_and_roots()

        assert all_symbols is not None
        assert len(all_symbols) > 0

        symbol_names = [sym.get("name") for sym in all_symbols]

        # The inline table 'endpoint' should be detected
        assert "endpoint" in symbol_names, "Should detect 'endpoint' inline table"

        # Find the endpoint symbol and check its properties
        endpoint_symbol = next((s for s in all_symbols if s.get("name") == "endpoint"), None)
        assert endpoint_symbol is not None
        # Inline tables should be kind 19 (object)
        assert endpoint_symbol.get("kind") == 19, "Inline table should have kind 19 (object)"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_nested_table_detection(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that deeply nested tables are properly detected."""
        all_symbols, root_symbols = language_server.request_document_symbols("config.toml").get_all_symbols_and_roots()

        symbol_names = [sym.get("name") for sym in all_symbols]

        # Should detect nested tables like server.ssl and database.pool
        has_ssl = any("ssl" in str(name).lower() for name in symbol_names if name)
        has_pool = any("pool" in str(name).lower() for name in symbol_names if name)

        assert has_ssl, f"Should detect 'server.ssl' nested table, got: {symbol_names}"
        assert has_pool, f"Should detect 'database.pool' nested table, got: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_array_of_tables_detection(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that [[array_of_tables]] syntax is properly detected."""
        all_symbols, root_symbols = language_server.request_document_symbols("config.toml").get_all_symbols_and_roots()

        symbol_names = [sym.get("name") for sym in all_symbols]

        # Should detect [[endpoints]] array of tables
        assert "endpoints" in symbol_names, f"Should detect '[[endpoints]]' array of tables, got: {symbol_names}"

        # Find the endpoints symbol
        endpoints_symbol = next((s for s in all_symbols if s.get("name") == "endpoints"), None)
        assert endpoints_symbol is not None

        # Array of tables should be kind 18 (array)
        assert endpoints_symbol.get("kind") == 18, "Array of tables should have kind 18 (array)"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_multiline_string_handling(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that multiline strings are handled correctly."""
        all_symbols, root_symbols = language_server.request_document_symbols("config.toml").get_all_symbols_and_roots()

        symbol_names = [sym.get("name") for sym in all_symbols]

        # Should detect connection_string and multiline fields
        assert "connection_string" in symbol_names, "Should detect 'connection_string' with multiline value"
        assert "multiline" in symbol_names, "Should detect 'multiline' literal string"

        # Find connection_string and verify it's a string type
        conn_symbol = next((s for s in all_symbols if s.get("name") == "connection_string"), None)
        assert conn_symbol is not None
        # String type should be kind 15
        assert conn_symbol.get("kind") == 15, "Multiline string should have kind 15 (string)"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_array_value_detection(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that array values are properly detected."""
        all_symbols, root_symbols = language_server.request_document_symbols("config.toml").get_all_symbols_and_roots()

        symbol_names = [sym.get("name") for sym in all_symbols]

        # Should detect 'outputs' and 'methods' arrays
        assert "outputs" in symbol_names, "Should detect 'outputs' array"
        assert "methods" in symbol_names, "Should detect 'methods' array"

        # Find outputs array and verify kind
        outputs_symbol = next((s for s in all_symbols if s.get("name") == "outputs"), None)
        assert outputs_symbol is not None
        # Arrays should have kind 18
        assert outputs_symbol.get("kind") == 18, "'outputs' should have kind 18 (array)"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_float_value_detection(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that float values are properly detected."""
        all_symbols, root_symbols = language_server.request_document_symbols("config.toml").get_all_symbols_and_roots()

        symbol_names = [sym.get("name") for sym in all_symbols]

        # Should detect 'timeout' which has a float value (30.5)
        assert "timeout" in symbol_names, "Should detect 'timeout' float value"

        # Find timeout and verify it's a number
        timeout_symbol = next((s for s in all_symbols if s.get("name") == "timeout"), None)
        assert timeout_symbol is not None
        # Numbers should have kind 16
        assert timeout_symbol.get("kind") == 16, "'timeout' should have kind 16 (number)"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_datetime_value_detection(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that datetime values are detected."""
        all_symbols, root_symbols = language_server.request_document_symbols("config.toml").get_all_symbols_and_roots()

        symbol_names = [sym.get("name") for sym in all_symbols]

        # Should detect metadata section with datetime values
        assert "metadata" in symbol_names, "Should detect 'metadata' section"
        assert "created" in symbol_names, "Should detect 'created' datetime field"
        assert "updated" in symbol_names, "Should detect 'updated' datetime field"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_symbol_body_with_inline_table(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that symbol bodies include inline table content."""
        all_symbols, root_symbols = language_server.request_document_symbols("config.toml").get_all_symbols_and_roots()

        # Find the endpoint symbol with body
        endpoint_symbol = next((s for s in all_symbols if s.get("name") == "endpoint"), None)
        assert endpoint_symbol is not None

        if "body" in endpoint_symbol:
            body = endpoint_symbol["body"].get_text()
            # Body should contain the inline table syntax
            assert "url" in body or "version" in body, f"Body should contain inline table contents, got: {body}"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_symbol_ranges_in_config(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that symbol ranges are correct in config.toml."""
        all_symbols, root_symbols = language_server.request_document_symbols("config.toml").get_all_symbols_and_roots()

        # Find the server symbol
        server_symbol = next((s for s in all_symbols if s.get("name") == "server"), None)
        assert server_symbol is not None
        assert "range" in server_symbol

        # Server should start near the beginning (line 2 is [server], 0-indexed: line 2)
        server_range = server_symbol["range"]
        assert server_range["start"]["line"] >= 0, "Server should start at or near the beginning"
        assert server_range["end"]["line"] > server_range["start"]["line"], "Server block should span multiple lines"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_comment_handling(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that comments don't interfere with symbol detection."""
        all_symbols, root_symbols = language_server.request_document_symbols("config.toml").get_all_symbols_and_roots()

        symbol_names = [sym.get("name") for sym in all_symbols]

        # File has comments but symbols should still be detected correctly
        expected_sections = {"server", "database", "logging", "endpoints", "metadata", "messages"}
        found_sections = expected_sections.intersection(set(symbol_names))

        assert len(found_sections) >= 4, f"Should find most sections despite comments, found: {found_sections}"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_special_characters_in_strings(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that strings with escape sequences are handled."""
        all_symbols, root_symbols = language_server.request_document_symbols("config.toml").get_all_symbols_and_roots()

        symbol_names = [sym.get("name") for sym in all_symbols]

        # Should detect the messages section with special strings
        assert "messages" in symbol_names, "Should detect 'messages' section"
        assert "with_escapes" in symbol_names, "Should detect 'with_escapes' field"
        assert "welcome" in symbol_names, "Should detect 'welcome' field"


class TestTomlDependencyTables:
    """Test handling of dependency-style tables common in Cargo.toml and pyproject.toml."""

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_complex_dependency_inline_table(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test detection of complex inline table dependencies like serde = { version = "1.0", features = ["derive"] }."""
        all_symbols, root_symbols = language_server.request_document_symbols("Cargo.toml").get_all_symbols_and_roots()

        symbol_names = [sym.get("name") for sym in all_symbols]

        # Should detect serde and tokio dependencies
        assert "serde" in symbol_names, "Should detect 'serde' dependency"
        assert "tokio" in symbol_names, "Should detect 'tokio' dependency"

        # Find serde symbol
        serde_symbol = next((s for s in all_symbols if s.get("name") == "serde"), None)
        assert serde_symbol is not None

        # Dependency with inline table should be kind 19 (object)
        assert serde_symbol.get("kind") == 19, "Complex dependency should have kind 19 (object)"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_simple_dependency_string(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test detection of simple string dependencies like proptest = "1.0"."""
        all_symbols, root_symbols = language_server.request_document_symbols("Cargo.toml").get_all_symbols_and_roots()

        symbol_names = [sym.get("name") for sym in all_symbols]

        # Should detect proptest dev-dependency
        assert "proptest" in symbol_names, "Should detect 'proptest' dependency"

        # Find proptest symbol
        proptest_symbol = next((s for s in all_symbols if s.get("name") == "proptest"), None)
        assert proptest_symbol is not None

        # Simple string dependency should be kind 15 (string)
        assert proptest_symbol.get("kind") == 15, "Simple string dependency should have kind 15 (string)"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_pyproject_dependencies_array(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test detection of pyproject.toml dependencies array."""
        all_symbols, root_symbols = language_server.request_document_symbols("pyproject.toml").get_all_symbols_and_roots()

        symbol_names = [sym.get("name") for sym in all_symbols]

        # Should detect dependencies array
        assert "dependencies" in symbol_names, "Should detect 'dependencies' array"

        # Find dependencies symbol
        deps_symbol = next((s for s in all_symbols if s.get("name") == "dependencies"), None)
        assert deps_symbol is not None

        # Dependencies array should be kind 18 (array)
        assert deps_symbol.get("kind") == 18, "Dependencies array should have kind 18 (array)"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_optional_dependencies_table(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test detection of optional-dependencies in pyproject.toml."""
        all_symbols, root_symbols = language_server.request_document_symbols("pyproject.toml").get_all_symbols_and_roots()

        symbol_names = [sym.get("name") for sym in all_symbols]

        # Should detect optional-dependencies or its nested form
        has_optional_deps = any("optional" in str(name).lower() for name in symbol_names if name)
        has_dev = "dev" in symbol_names

        assert has_optional_deps or has_dev, f"Should detect optional-dependencies or dev group, got: {symbol_names}"
