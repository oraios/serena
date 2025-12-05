"""
Integration tests for Elixir language server with test repository.

These tests verify that the language server works correctly with a real Elixir project
and can perform advanced operations like cross-file symbol resolution.
"""

import os
from pathlib import Path

import pytest

from serena.project import Project
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language

from . import EXPERT_UNAVAILABLE, EXPERT_UNAVAILABLE_REASON

# These marks will be applied to all tests in this module
pytestmark = [pytest.mark.elixir, pytest.mark.skipif(EXPERT_UNAVAILABLE, reason=f"Next LS not available: {EXPERT_UNAVAILABLE_REASON}")]


class TestElixirIntegration:
    """Integration tests for Elixir language server with test repository."""

    @pytest.fixture
    def elixir_test_repo_path(self):
        """Get the path to the Elixir test repository."""
        test_dir = Path(__file__).parent.parent.parent
        return str(test_dir / "resources" / "repos" / "elixir" / "test_repo")

    def test_elixir_repo_structure(self, elixir_test_repo_path):
        """Test that the Elixir test repository has the expected structure."""
        repo_path = Path(elixir_test_repo_path)

        # Check that key files exist
        assert (repo_path / "mix.exs").exists(), "mix.exs should exist"
        assert (repo_path / "lib" / "test_repo.ex").exists(), "main module should exist"
        assert (repo_path / "lib" / "utils.ex").exists(), "utils module should exist"
        assert (repo_path / "lib" / "models.ex").exists(), "models module should exist"
        assert (repo_path / "lib" / "services.ex").exists(), "services module should exist"
        assert (repo_path / "lib" / "examples.ex").exists(), "examples module should exist"
        assert (repo_path / "test" / "test_repo_test.exs").exists(), "test file should exist"
        assert (repo_path / "test" / "models_test.exs").exists(), "models test should exist"

    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_cross_file_symbol_resolution(self, language_server: SolidLanguageServer):
        """Test that symbols can be resolved across different files."""
        # Test that User struct from models.ex can be found when referenced in services.ex
        services_file = os.path.join("lib", "services.ex")

        # Find where User is referenced in services.ex
        content = language_server.retrieve_full_file_content(services_file)
        lines = content.split("\n")
        user_reference_line = None
        for i, line in enumerate(lines):
            if "alias TestRepo.Models.{User" in line:
                user_reference_line = i
                break

        if user_reference_line is None:
            pytest.skip("Could not find User reference in services.ex")

        # Try to find the definition
        defining_symbol = language_server.request_defining_symbol(services_file, user_reference_line, 30)

        if defining_symbol and "location" in defining_symbol:
            # Should point to models.ex
            assert "models.ex" in defining_symbol["location"]["uri"]

    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_module_hierarchy_understanding(self, language_server: SolidLanguageServer):
        """Test that the language server understands Elixir module hierarchy."""
        models_file = os.path.join("lib", "models.ex")
        symbols = language_server.request_document_symbols(models_file).get_all_symbols_and_roots()

        if symbols:
            # Flatten symbol structure
            all_symbols = []
            for symbol_group in symbols:
                if isinstance(symbol_group, list):
                    all_symbols.extend(symbol_group)
                else:
                    all_symbols.append(symbol_group)

            symbol_names = [s.get("name", "") for s in all_symbols]

            # Should understand nested module structure
            expected_modules = ["TestRepo.Models", "User", "Item", "Order"]
            found_modules = [name for name in expected_modules if any(name in symbol_name for symbol_name in symbol_names)]
            assert len(found_modules) > 0, f"Expected modules {expected_modules}, found symbols {symbol_names}"

    def test_file_extension_matching(self):
        """Test that the Elixir language recognizes the correct file extensions."""
        language = Language.ELIXIR
        matcher = language.get_source_fn_matcher()

        # Test Elixir file extensions
        assert matcher.is_relevant_filename("lib/test_repo.ex")
        assert matcher.is_relevant_filename("test/test_repo_test.exs")
        assert matcher.is_relevant_filename("config/config.exs")
        assert matcher.is_relevant_filename("mix.exs")
        assert matcher.is_relevant_filename("lib/models.ex")
        assert matcher.is_relevant_filename("lib/services.ex")

        # Test non-Elixir files
        assert not matcher.is_relevant_filename("README.md")
        assert not matcher.is_relevant_filename("lib/test_repo.py")
        assert not matcher.is_relevant_filename("package.json")
        assert not matcher.is_relevant_filename("Cargo.toml")


class TestElixirProject:
    @pytest.mark.parametrize("project", [Language.ELIXIR], indirect=True)
    def test_comprehensive_symbol_search(self, project: Project):
        """Test comprehensive symbol search across the entire project."""
        # Search for all function definitions
        function_pattern = r"def\s+\w+\s*[\(\s]"
        function_matches = project.search_source_files_for_pattern(function_pattern)

        # Should find functions across multiple files
        if function_matches:
            files_with_functions = set()
            for match in function_matches:
                if match.source_file_path:
                    files_with_functions.add(os.path.basename(match.source_file_path))

            # Should find functions in multiple files
            expected_files = {"models.ex", "services.ex", "examples.ex", "utils.ex", "test_repo.ex"}
            found_files = expected_files.intersection(files_with_functions)
            assert len(found_files) > 0, f"Expected functions in {expected_files}, found in {files_with_functions}"

        # Search for struct definitions
        struct_pattern = r"defstruct\s+\["
        struct_matches = project.search_source_files_for_pattern(struct_pattern)

        if struct_matches:
            # Should find structs primarily in models.ex
            models_structs = [m for m in struct_matches if m.source_file_path and "models.ex" in m.source_file_path]
            assert len(models_structs) > 0, "Should find struct definitions in models.ex"

    @pytest.mark.parametrize("project", [Language.ELIXIR], indirect=True)
    def test_protocol_and_implementation_understanding(self, project: Project):
        """Test that the language server understands Elixir protocols and implementations."""
        # Search for protocol definitions
        protocol_pattern = r"defprotocol\s+\w+"
        protocol_matches = project.search_source_files_for_pattern(protocol_pattern, paths_include_glob="**/models.ex")

        if protocol_matches:
            # Should find the Serializable protocol
            serializable_matches = [m for m in protocol_matches if "Serializable" in str(m)]
            assert len(serializable_matches) > 0, "Should find Serializable protocol definition"

        # Search for protocol implementations
        impl_pattern = r"defimpl\s+\w+"
        impl_matches = project.search_source_files_for_pattern(impl_pattern, paths_include_glob="**/models.ex")

        if impl_matches:
            # Should find multiple implementations
            assert len(impl_matches) >= 3, f"Should find at least 3 protocol implementations, found {len(impl_matches)}"
