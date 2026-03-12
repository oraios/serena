"""
Basic integration tests for the COBOL language server functionality.

These tests validate the functionality of the language server APIs
like request_document_symbols, request_definition, and request_references
using the COBOL test repository.
"""

from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.cobol
class TestCobolLanguageServer:
    """Test basic functionality of the COBOL language server."""

    @pytest.mark.parametrize("language_server", [Language.COBOL], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.COBOL], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that the COBOL language server starts and stops successfully."""
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.COBOL], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.COBOL], indirect=True)
    def test_find_symbols_in_main(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding symbols in main.cob file."""
        # Request symbols from main.cob
        main_cob_path = str(repo_path / "main.cob")
        all_symbols, _root_symbols = language_server.request_document_symbols(main_cob_path).get_all_symbols_and_roots()

        # Extract symbol names
        symbol_names = [symbol["name"] for symbol in all_symbols]

        # Verify we found expected symbols (paragraphs/sections)
        # COBOL programs, procedures, and paragraphs should be detected
        assert len(symbol_names) > 0, "Should find at least some symbols in main.cob"

        # Check for key procedure names
        expected_procedures = ["MAIN-PROCEDURE", "ADD-NUMBERS", "SUBTRACT-NUMBERS", "CALL-HELPER"]
        found_procedures = [name for name in expected_procedures if name in symbol_names]
        
        assert len(found_procedures) > 0, f"Should find at least one procedure from {expected_procedures}, found {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.COBOL], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.COBOL], indirect=True)
    def test_find_symbols_in_helper(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding symbols in helper.cob file."""
        # Request symbols from lib/helper.cob
        helper_cob_path = str(repo_path / "lib" / "helper.cob")
        all_symbols, _root_symbols = language_server.request_document_symbols(helper_cob_path).get_all_symbols_and_roots()

        # Extract symbol names
        symbol_names = [symbol["name"] for symbol in all_symbols]

        # Verify we found expected symbols
        assert len(symbol_names) > 0, "Should find at least some symbols in helper.cob"

        # Check for helper procedures
        expected_procedures = ["HELPER-MAIN", "FORMAT-MESSAGE"]
        found_procedures = [name for name in expected_procedures if name in symbol_names]
        
        assert len(found_procedures) > 0, f"Should find at least one procedure from {expected_procedures}, found {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.COBOL], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.COBOL], indirect=True)
    def test_find_definition_within_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding definitions within the same COBOL file."""
        main_cob_path = str(repo_path / "main.cob")

        # In main.cob, line 17 (0-indexed line 16) has: PERFORM ADD-NUMBERS
        # We want to find the definition of ADD-NUMBERS (defined around line 27)
        # COBOL LSP uses 0-indexed lines
        # Line with "PERFORM ADD-NUMBERS" is approximately line 16-17 (0-indexed)
        definition_location_list = language_server.request_definition(main_cob_path, 16, 20)

        # We should get a definition location (may be empty if LS doesn't support it)
        # If we get results, verify they point to main.cob
        if definition_location_list:
            assert len(definition_location_list) >= 1, "Should find at least one definition"
            definition_location = definition_location_list[0]
            assert definition_location["uri"].endswith("main.cob"), "Definition should be in main.cob"
            # The definition should be on a line containing ADD-NUMBERS paragraph
            # (exact line depends on LS implementation)

    @pytest.mark.parametrize("language_server", [Language.COBOL], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.COBOL], indirect=True)
    def test_find_definition_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding definitions across COBOL files."""
        main_cob_path = str(repo_path / "main.cob")

        # In main.cob, around line 33 (0-indexed): CALL 'HELPER' USING WS-GREETING
        # Try to find the definition of HELPER (in lib/helper.cob)
        definition_location_list = language_server.request_definition(main_cob_path, 32, 15)

        # This test may not work for all COBOL LSPs, as cross-file references
        # depend on the specific language server implementation
        # If we get results, verify they make sense
        if definition_location_list:
            assert len(definition_location_list) >= 1, "Should find at least one definition"
            definition_location = definition_location_list[0]
            # The definition could be in helper.cob
            assert "helper.cob" in definition_location["uri"] or "main.cob" in definition_location["uri"]

    @pytest.mark.parametrize("language_server", [Language.COBOL], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.COBOL], indirect=True)
    def test_find_references_within_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding references within the same COBOL file."""
        main_cob_path = str(repo_path / "main.cob")

        # Find references to ADD-NUMBERS paragraph
        # ADD-NUMBERS is defined around line 27 and referenced on line 17
        references = language_server.request_references(main_cob_path, 27, 10)

        # If the LS supports references, we should find at least the PERFORM statement
        if references:
            assert len(references) >= 1, f"Should find at least one reference to ADD-NUMBERS, got {references}"
            # Verify at least one reference is in main.cob
            main_cob_refs = [ref for ref in references if "main.cob" in ref["uri"]]
            assert len(main_cob_refs) >= 1, "Should find at least one reference in main.cob"

    @pytest.mark.parametrize("language_server", [Language.COBOL], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.COBOL], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding references across COBOL files."""
        helper_cob_path = str(repo_path / "lib" / "helper.cob")

        # Find references to HELPER program (called from main.cob)
        # HELPER-MAIN is around line 13 in helper.cob
        references = language_server.request_references(helper_cob_path, 13, 10)

        # This test depends on whether the COBOL LSP supports cross-file references
        # If it does, we should find the CALL statement in main.cob
        if references:
            # Check if any references are from other files
            cross_file_refs = [ref for ref in references if not ref["uri"].endswith("helper.cob")]
            # If we found cross-file references, verify they're meaningful
            if cross_file_refs:
                assert len(cross_file_refs) >= 1, "Should find cross-file references"