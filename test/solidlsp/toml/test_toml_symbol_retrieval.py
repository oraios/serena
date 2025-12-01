"""
Tests for TOML language server symbol retrieval functionality.

These tests focus on advanced symbol operations:
- request_containing_symbol
- request_document_overview
- request_full_symbol_tree
- request_dir_overview
"""

from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language

pytestmark = pytest.mark.toml


class TestTomlSymbolRetrieval:
    """Test advanced symbol retrieval functionality for TOML files."""

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_request_containing_symbol_behavior(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test request_containing_symbol behavior for TOML files.

        Note: Taplo LSP doesn't support definition/containing symbol lookups for TOML files
        since TOML is a configuration format, not code. This test verifies the behavior.
        """
        # Line 2 (0-indexed: 1) is inside the [package] table
        containing_symbol = language_server.request_containing_symbol("Cargo.toml", 1, 5)

        # Taplo doesn't support containing symbol lookup - returns None
        # This is expected behavior for a configuration file format
        assert containing_symbol is None, "TOML LSP doesn't support containing symbol lookup"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_request_document_overview_cargo(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test request_document_overview for Cargo.toml."""
        overview = language_server.request_document_overview("Cargo.toml")

        assert overview is not None
        assert len(overview) > 0

        # Get symbol names from overview
        symbol_names = {symbol.get("name") for symbol in overview if "name" in symbol}

        # Verify expected top-level tables appear
        expected_tables = {"package", "dependencies", "dev-dependencies", "features", "workspace"}
        assert expected_tables.issubset(symbol_names), f"Missing expected tables in overview: {expected_tables - symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_request_document_overview_pyproject(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test request_document_overview for pyproject.toml."""
        overview = language_server.request_document_overview("pyproject.toml")

        assert overview is not None
        assert len(overview) > 0

        # Get symbol names from overview
        symbol_names = {symbol.get("name") for symbol in overview if "name" in symbol}

        # Verify expected top-level tables appear
        assert "project" in symbol_names, "Should detect 'project' table"
        assert "build-system" in symbol_names, "Should detect 'build-system' table"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_request_full_symbol_tree(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test request_full_symbol_tree returns TOML files."""
        symbol_tree = language_server.request_full_symbol_tree()

        assert symbol_tree is not None
        assert len(symbol_tree) > 0

        # The root should be test_repo
        root = symbol_tree[0]
        assert root["name"] == "test_repo"
        assert "children" in root

        # Children should include TOML files
        child_names = {child["name"] for child in root.get("children", [])}
        # Note: File names are stripped of extension in some cases
        assert (
            "Cargo" in child_names or "Cargo.toml" in child_names or any("cargo" in name.lower() for name in child_names)
        ), f"Should find Cargo.toml in tree, got: {child_names}"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_request_dir_overview(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test request_dir_overview returns symbols for TOML files."""
        overview = language_server.request_dir_overview(".")

        assert overview is not None
        assert len(overview) > 0

        # Should have entries for both Cargo.toml and pyproject.toml
        file_paths = list(overview.keys())
        assert any("Cargo.toml" in path for path in file_paths), f"Should find Cargo.toml in overview, got: {file_paths}"
        assert any("pyproject.toml" in path for path in file_paths), f"Should find pyproject.toml in overview, got: {file_paths}"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_symbol_hierarchy_in_cargo(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that symbol hierarchy is properly preserved in Cargo.toml."""
        all_symbols, root_symbols = language_server.request_document_symbols("Cargo.toml").get_all_symbols_and_roots()

        # Find the 'package' table
        package_symbol = next((s for s in root_symbols if s.get("name") == "package"), None)
        assert package_symbol is not None, "Should find 'package' as root symbol"

        # Verify it has children (nested keys)
        assert "children" in package_symbol, "'package' should have children"
        child_names = {child.get("name") for child in package_symbol.get("children", [])}

        # Package should have name, version, edition at minimum
        assert "name" in child_names, "'package' should have 'name' child"
        assert "version" in child_names, "'package' should have 'version' child"
        assert "edition" in child_names, "'package' should have 'edition' child"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_symbol_hierarchy_in_pyproject(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that symbol hierarchy is properly preserved in pyproject.toml."""
        all_symbols, root_symbols = language_server.request_document_symbols("pyproject.toml").get_all_symbols_and_roots()

        # Find the 'project' table
        project_symbol = next((s for s in root_symbols if s.get("name") == "project"), None)
        assert project_symbol is not None, "Should find 'project' as root symbol"

        # Verify it has children
        assert "children" in project_symbol, "'project' should have children"
        child_names = {child.get("name") for child in project_symbol.get("children", [])}

        # Project should have name, version, dependencies at minimum
        assert "name" in child_names, "'project' should have 'name' child"
        assert "version" in child_names, "'project' should have 'version' child"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_tool_section_hierarchy(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that tool sections in pyproject.toml are properly structured."""
        all_symbols, root_symbols = language_server.request_document_symbols("pyproject.toml").get_all_symbols_and_roots()

        # Get all symbol names
        all_names = [s.get("name") for s in all_symbols]

        # Should detect tool.ruff, tool.mypy, or tool.pytest
        has_ruff = any("ruff" in name.lower() for name in all_names if name)
        has_mypy = any("mypy" in name.lower() for name in all_names if name)
        has_pytest = any("pytest" in name.lower() for name in all_names if name)

        assert has_ruff or has_mypy or has_pytest, f"Should detect tool sections, got names: {all_names}"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.TOML], indirect=True)
    def test_array_of_tables_symbol(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that [[bin]] array of tables is detected."""
        all_symbols, root_symbols = language_server.request_document_symbols("Cargo.toml").get_all_symbols_and_roots()

        # Get all symbol names
        all_names = [s.get("name") for s in all_symbols]

        # Should detect bin array of tables
        has_bin = "bin" in all_names
        assert has_bin, f"Should detect [[bin]] array of tables, got names: {all_names}"

        # Find the bin symbol and verify its structure
        bin_symbol = next((s for s in all_symbols if s.get("name") == "bin"), None)
        assert bin_symbol is not None, "Should find bin symbol"

        # Array of tables should be kind 18 (array)
        assert bin_symbol.get("kind") == 18, "[[bin]] should have kind 18 (array)"

        # Children of array of tables are indexed by position ('0', '1', etc.)
        if "children" in bin_symbol:
            bin_children = bin_symbol.get("children", [])
            assert len(bin_children) > 0, "[[bin]] should have at least one child element"
            # First child is index '0'
            first_child = bin_children[0]
            assert first_child.get("name") == "0", f"First array element should be named '0', got: {first_child.get('name')}"

            # The '0' element should contain name and path as grandchildren
            if "children" in first_child:
                grandchild_names = {gc.get("name") for gc in first_child.get("children", [])}
                assert "name" in grandchild_names, f"[[bin]] element should have 'name' field, got: {grandchild_names}"
                assert "path" in grandchild_names, f"[[bin]] element should have 'path' field, got: {grandchild_names}"
