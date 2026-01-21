"""
Basic integration tests for the TOML language server functionality.

These tests validate the functionality of the Taplo language server APIs
like request_document_symbols using the TOML test repository.
"""

from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.toml
class TestTomlLanguageServerBasics:
    """Test basic functionality of the TOML language server (Taplo)."""

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_toml_language_server_initialization(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that TOML language server can be initialized successfully."""
        assert language_server is not None
        assert language_server.language == Language.TOML
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_toml_cargo_file_symbols(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test document symbols detection in Cargo.toml with specific symbol verification."""
        all_symbols, root_symbols = language_server.request_document_symbols("Cargo.toml").get_all_symbols_and_roots()

        assert all_symbols is not None, "Should return symbols for Cargo.toml"
        assert len(all_symbols) > 0, f"Should find symbols in Cargo.toml, found {len(all_symbols)}"

        # Verify specific top-level table names are detected
        symbol_names = [sym.get("name") for sym in all_symbols]
        assert "package" in symbol_names, "Should detect 'package' table in Cargo.toml"
        assert "dependencies" in symbol_names, "Should detect 'dependencies' table in Cargo.toml"
        assert "dev-dependencies" in symbol_names, "Should detect 'dev-dependencies' table in Cargo.toml"
        assert "features" in symbol_names, "Should detect 'features' table in Cargo.toml"
        assert "workspace" in symbol_names, "Should detect 'workspace' table in Cargo.toml"

        # Verify nested symbols exist (keys under 'package')
        assert "name" in symbol_names, "Should detect nested 'name' key"
        assert "version" in symbol_names, "Should detect nested 'version' key"
        assert "edition" in symbol_names, "Should detect nested 'edition' key"

        # Check symbol kind for tables - Taplo uses kind 19 (object) for TOML tables
        package_symbol = next((s for s in all_symbols if s.get("name") == "package"), None)
        assert package_symbol is not None, "Should find 'package' symbol"
        assert package_symbol.get("kind") == 19, "Top-level table should have kind 19 (object)"

        dependencies_symbol = next((s for s in all_symbols if s.get("name") == "dependencies"), None)
        assert dependencies_symbol is not None, "Should find 'dependencies' symbol"
        assert dependencies_symbol.get("kind") == 19, "'dependencies' table should have kind 19 (object)"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_toml_pyproject_file_symbols(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test document symbols detection in pyproject.toml."""
        all_symbols, root_symbols = language_server.request_document_symbols("pyproject.toml").get_all_symbols_and_roots()

        assert all_symbols is not None, "Should return symbols for pyproject.toml"
        assert len(all_symbols) > 0, f"Should find symbols in pyproject.toml, found {len(all_symbols)}"

        # Verify specific top-level table names
        symbol_names = [sym.get("name") for sym in all_symbols]
        assert "project" in symbol_names, "Should detect 'project' table"
        assert "build-system" in symbol_names, "Should detect 'build-system' table"

        # Verify tool sections (nested tables)
        # These could appear as 'tool' or 'tool.ruff' depending on Taplo's parsing
        has_tool_section = any("tool" in name for name in symbol_names if name)
        assert has_tool_section, "Should detect tool sections"

        # Verify nested keys under project
        assert "name" in symbol_names, "Should detect 'name' under project"
        assert "version" in symbol_names, "Should detect 'version' under project"
        assert "requires-python" in symbol_names or "dependencies" in symbol_names, "Should detect project dependencies"

        # Check symbol kind for tables - Taplo uses kind 19 (object) for TOML tables
        project_symbol = next((s for s in all_symbols if s.get("name") == "project"), None)
        assert project_symbol is not None, "Should find 'project' symbol"
        assert project_symbol.get("kind") == 19, "'project' table should have kind 19 (object)"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_toml_symbol_kinds(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that TOML symbols have appropriate LSP kinds for different value types."""
        all_symbols, root_symbols = language_server.request_document_symbols("Cargo.toml").get_all_symbols_and_roots()

        assert all_symbols is not None
        assert len(all_symbols) > 0

        # Check boolean symbol kind (lto = true at line 22)
        # LSP kind 17 = boolean
        lto_symbol = next((s for s in all_symbols if s.get("name") == "lto"), None)
        assert lto_symbol is not None, "Should find 'lto' boolean symbol"
        assert lto_symbol.get("kind") == 17, "'lto' should have kind 17 (boolean)"

        # Check number symbol kind (opt-level = 3 at line 23)
        # LSP kind 16 = number
        opt_level_symbol = next((s for s in all_symbols if s.get("name") == "opt-level"), None)
        assert opt_level_symbol is not None, "Should find 'opt-level' number symbol"
        assert opt_level_symbol.get("kind") == 16, "'opt-level' should have kind 16 (number)"

        # Check string symbol kind (name = "test_project" at line 2)
        # LSP kind 15 = string
        name_symbols = [s for s in all_symbols if s.get("name") == "name"]
        assert len(name_symbols) > 0, "Should find 'name' symbols"
        # At least one should be a string
        string_name_symbol = next((s for s in name_symbols if s.get("kind") == 15), None)
        assert string_name_symbol is not None, "Should find 'name' with kind 15 (string)"

        # Check array symbol kind (default = ["feature1"] at line 17)
        # LSP kind 18 = array
        default_symbol = next((s for s in all_symbols if s.get("name") == "default"), None)
        assert default_symbol is not None, "Should find 'default' array symbol"
        assert default_symbol.get("kind") == 18, "'default' should have kind 18 (array)"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_toml_symbols_with_body(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test request_document_symbols with body extraction."""
        all_symbols, root_symbols = language_server.request_document_symbols("Cargo.toml").get_all_symbols_and_roots()

        assert all_symbols is not None, "Should return symbols for Cargo.toml"
        assert len(all_symbols) > 0, "Should have symbols"

        # Find the 'package' symbol and verify its body
        package_symbol = next((s for s in all_symbols if s.get("name") == "package"), None)
        assert package_symbol is not None, "Should find 'package' symbol"

        # Check that body exists and contains expected content
        # Note: Taplo includes the section header in the body
        assert "body" in package_symbol, "'package' symbol should have body"
        package_body = package_symbol["body"].get_text()
        assert 'name = "test_project"' in package_body, "Body should contain 'name' field"
        assert 'version = "0.1.0"' in package_body, "Body should contain 'version' field"
        assert 'edition = "2021"' in package_body, "Body should contain 'edition' field"

        # Find the dependencies symbol and check its body
        deps_symbol = next((s for s in all_symbols if s.get("name") == "dependencies"), None)
        assert deps_symbol is not None, "Should find 'dependencies' symbol"
        assert "body" in deps_symbol, "'dependencies' symbol should have body"
        deps_body = deps_symbol["body"].get_text()
        assert "serde" in deps_body, "Body should contain serde dependency"
        assert "tokio" in deps_body, "Body should contain tokio dependency"

        # Find the top-level [features] section (not the nested 'features' in serde dependency)
        # The [features] section should be kind 19 (object) and at line 15 (0-indexed)
        features_symbols = [s for s in all_symbols if s.get("name") == "features"]
        # Find the top-level one - should be kind 19 (object) with children
        features_symbol = next(
            (s for s in features_symbols if s.get("kind") == 19 and s.get("children")),
            None,
        )
        assert features_symbol is not None, "Should find top-level 'features' table symbol"
        assert "body" in features_symbol, "'features' symbol should have body"
        features_body = features_symbol["body"].get_text()
        assert "default" in features_body, "Body should contain 'default' feature"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_toml_symbol_ranges(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that symbols have proper range information."""
        all_symbols, root_symbols = language_server.request_document_symbols("Cargo.toml").get_all_symbols_and_roots()

        assert all_symbols is not None
        assert len(all_symbols) > 0

        # Check the 'package' symbol range - should start at line 0 (0-indexed, actual line 1)
        package_symbol = next((s for s in all_symbols if s.get("name") == "package"), None)
        assert package_symbol is not None, "Should find 'package' symbol"
        assert "range" in package_symbol, "'package' symbol should have range"

        package_range = package_symbol["range"]
        assert "start" in package_range, "Range should have start"
        assert "end" in package_range, "Range should have end"
        assert package_range["start"]["line"] == 0, "'package' should start at line 0 (0-indexed, actual line 1)"
        # Package block spans from line 1 to line 7 in file (1-indexed)
        # In 0-indexed LSP coordinates: line 0 (start) to line 6 or 7 (end)
        assert package_range["end"]["line"] >= 6, "'package' should end at or after line 6 (0-indexed)"

        # Check a nested symbol range - 'name' under package at line 2 (1-indexed), line 1 (0-indexed)
        name_symbols = [s for s in all_symbols if s.get("name") == "name"]
        assert len(name_symbols) > 0, "Should find 'name' symbols"
        # Find the one under 'package' (should be at line 1 in 0-indexed)
        package_name = next((s for s in name_symbols if s["range"]["start"]["line"] == 1), None)
        assert package_name is not None, "Should find 'name' under 'package'"

        # Check the dependencies range - starts at line 9 (1-indexed), line 8 (0-indexed)
        deps_symbol = next((s for s in all_symbols if s.get("name") == "dependencies"), None)
        assert deps_symbol is not None, "Should find 'dependencies' symbol"
        deps_range = deps_symbol["range"]
        assert deps_range["start"]["line"] == 8, "'dependencies' should start at line 8 (0-indexed, actual line 9)"

        # Check that range includes line and character positions
        assert "line" in package_range["start"], "Start should have line"
        assert "character" in package_range["start"], "Start should have character"
        assert "line" in package_range["end"], "End should have line"
        assert "character" in package_range["end"], "End should have character"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_toml_nested_table_symbols(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test detection of nested table symbols like profile.release and tool.ruff."""
        # Test Cargo.toml for profile.release
        cargo_symbols, _ = language_server.request_document_symbols("Cargo.toml").get_all_symbols_and_roots()

        assert cargo_symbols is not None
        symbol_names = [sym.get("name") for sym in cargo_symbols]

        # Should detect profile.release or profile section
        has_profile = any("profile" in name for name in symbol_names if name)
        assert has_profile, "Should detect profile section in Cargo.toml"

        # Test pyproject.toml for tool sections
        pyproject_symbols, _ = language_server.request_document_symbols("pyproject.toml").get_all_symbols_and_roots()

        assert pyproject_symbols is not None
        pyproject_names = [sym.get("name") for sym in pyproject_symbols]

        # Should detect tool.ruff, tool.mypy sections
        has_ruff = any("ruff" in name for name in pyproject_names if name)
        has_mypy = any("mypy" in name for name in pyproject_names if name)
        assert has_ruff or has_mypy, "Should detect tool sections in pyproject.toml"

        # Verify pyproject has expected boolean: strict = true
        strict_symbol = next((s for s in pyproject_symbols if s.get("name") == "strict"), None)
        if strict_symbol:
            assert strict_symbol.get("kind") == 17, "'strict' should have kind 17 (boolean)"
