"""
Basic tests for R Language Server integration
"""

from pathlib import Path
import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.r
class TestRLanguageServer:
    """Test basic functionality of the R language server."""

    @pytest.mark.parametrize("language_server", [Language.R], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.R], indirect=True)
    def test_server_initialization(self, language_server: SolidLanguageServer, repo_path: Path):
        """Test that the R language server initializes properly."""
        assert language_server is not None
        assert language_server.language_id == "r"
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.R], indirect=True)
    def test_symbol_retrieval(self, language_server: SolidLanguageServer):
        """Test R document symbol extraction."""
        all_symbols, root_symbols = language_server.request_document_symbols("R/utils.R")

        # Should find the three exported functions
        function_symbols = [s for s in all_symbols if s.get("kind") == 12]  # Function kind
        assert len(function_symbols) >= 3
        
        # Check that we found the expected functions
        function_names = {s.get("name") for s in function_symbols}
        expected_functions = {"calculate_mean", "process_data", "create_data_frame"}
        assert expected_functions.issubset(function_names), f"Expected functions {expected_functions} but found {function_names}"

    @pytest.mark.parametrize("language_server", [Language.R], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.R], indirect=True)
    def test_find_definition_across_files(self, language_server: SolidLanguageServer, repo_path: Path):
        """Test finding function definitions across files."""
        analysis_file = str(repo_path / "examples/analysis.R")
        
        # In analysis.R line 7: create_data_frame(n = 50)
        # The function create_data_frame is defined in R/utils.R
        # Find definition of create_data_frame function call (0-indexed: line 6)
        definition_location_list = language_server.request_definition(analysis_file, 6, 17)  # cursor on 'create_data_frame'
        
        assert definition_location_list, f"Expected non-empty definition_location_list but got {definition_location_list=}"
        assert len(definition_location_list) >= 1
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("utils.R")
        # Definition should be around line 37 (0-indexed: 36) where create_data_frame is defined
        assert definition_location["range"]["start"]["line"] >= 35

    @pytest.mark.parametrize("language_server", [Language.R], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.R], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer, repo_path: Path):
        """Test finding function references across files."""
        utils_file = str(repo_path / "R/utils.R") 
        analysis_file = str(repo_path / "examples/analysis.R")
        
        # Find references to calculate_mean function from its definition in utils.R
        # calculate_mean is defined around line 6 in utils.R
        references = language_server.request_references(utils_file, 5, 0)  # cursor on function name
        
        assert references, f"Expected non-empty references for calculate_mean but got {references=}"
        # Should find at least the usage in analysis.R line 13: calculate_mean(clean_data$value)
        reference_files = [ref["uri"] for ref in references]
        assert any(uri.endswith("analysis.R") for uri in reference_files), "Reference in analysis.R not found"

    def test_file_matching(self):
        """Test that R files are properly matched."""
        from solidlsp.ls_config import Language
        matcher = Language.R.get_source_fn_matcher()
        
        assert matcher.matches("script.R")
        assert matcher.matches("analysis.r") 
        assert not matcher.matches("script.py")
        assert not matcher.matches("README.md")

    def test_r_language_enum(self):
        """Test R language enum value."""
        assert Language.R == "r"
        assert str(Language.R) == "r"
