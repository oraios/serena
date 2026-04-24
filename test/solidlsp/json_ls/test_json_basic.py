"""
Basic integration tests for the JSON language server functionality.

These tests validate the functionality of the language server APIs
like request_document_symbols using the JSON test repository.
"""

from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols


@pytest.mark.json
class TestJsonLanguageServerBasics:
    """Test basic functionality of the JSON language server."""

    @pytest.mark.parametrize("language_server", [Language.JSON], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.JSON], indirect=True)
    def test_json_language_server_initialization(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that JSON language server can be initialized successfully."""
        assert language_server is not None
        assert language_server.language == Language.JSON
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.JSON], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.JSON], indirect=True)
    def test_json_config_file_symbols(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test document symbols detection in config.json with specific symbol verification."""
        all_symbols, root_symbols = language_server.request_document_symbols("config.json").get_all_symbols_and_roots()

        assert all_symbols is not None, "Should return symbols for config.json"
        assert len(all_symbols) > 0, f"Should find symbols in config.json, found {len(all_symbols)}"

        symbol_names = [sym.get("name") for sym in all_symbols]
        assert "app" in symbol_names, "Should detect 'app' key in config.json"
        assert "database" in symbol_names, "Should detect 'database' key in config.json"
        assert "logging" in symbol_names, "Should detect 'logging' key in config.json"
        assert "features" in symbol_names, "Should detect 'features' key in config.json"

        # Verify nested symbols
        assert "name" in symbol_names, "Should detect nested 'name' key"
        assert "port" in symbol_names, "Should detect nested 'port' key"
        assert "debug" in symbol_names, "Should detect nested 'debug' key"

    @pytest.mark.parametrize("language_server", [Language.JSON], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.JSON], indirect=True)
    def test_json_data_file_symbols(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test symbol detection in data.json with array structures."""
        all_symbols, root_symbols = language_server.request_document_symbols("data.json").get_all_symbols_and_roots()

        assert all_symbols is not None, "Should return symbols for data.json"
        assert len(all_symbols) > 0, f"Should find symbols in data.json, found {len(all_symbols)}"

        symbol_names = [sym.get("name") for sym in all_symbols]
        assert "users" in symbol_names, "Should detect 'users' array"
        assert "projects" in symbol_names, "Should detect 'projects' array"
        assert "name" in symbol_names, "Should detect 'name' fields"
        assert "email" in symbol_names, "Should detect 'email' fields"
        assert "id" in symbol_names, "Should detect 'id' fields"

    @pytest.mark.parametrize("language_server", [Language.JSON], indirect=True)
    def test_bare_symbol_names(self, language_server: SolidLanguageServer) -> None:
        """Test that symbol names do not contain malformed characters."""
        all_symbols = request_all_symbols(language_server)
        malformed_symbols = []
        for s in all_symbols:
            if has_malformed_name(s, period_allowed=True):
                malformed_symbols.append(s)
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )
