"""
Tests for Lean 4 Language Server integration with Serena.

Tests prove that Serena's symbol tools can:
1. Start the Lean 4 language server
2. Discover all expected symbols with precise matching
3. Track within-file references
4. Track cross-file references

Test Repository Structure:
- Helper.lean: Calculator structure, arithmetic functions (add, subtract), predicates (isPositive, absolute)
- Main.lean: Main entry point using Helper, plus multiply and calculate functions
"""

import pytest

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.lean4
class TestLean4LanguageServer:
    @pytest.mark.parametrize("language_server", [Language.LEAN4], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer) -> None:
        """Test that the Lean 4 language server starts successfully."""
        assert language_server.is_running()

    @pytest.mark.parametrize("language_server", [Language.LEAN4], indirect=True)
    def test_helper_symbols(self, language_server: SolidLanguageServer) -> None:
        """
        Test symbol discovery in Helper.lean.

        Verifies that Serena can identify:
        - Structure definition (Calculator)
        - All functions (add, subtract, isPositive, absolute)
        """
        all_symbols, _ = language_server.request_document_symbols("Helper.lean").get_all_symbols_and_roots()
        symbol_names = {s["name"] for s in all_symbols}

        expected_symbols = {
            "Calculator",
            "add",
            "subtract",
            "isPositive",
            "absolute",
        }

        missing = expected_symbols - symbol_names
        assert not missing, f"Missing expected symbols in Helper.lean: {missing}"

    @pytest.mark.parametrize("language_server", [Language.LEAN4], indirect=True)
    def test_main_symbols(self, language_server: SolidLanguageServer) -> None:
        """
        Test symbol discovery in Main.lean.

        Verifies that Serena can identify locally defined functions.
        """
        all_symbols, _ = language_server.request_document_symbols("Main.lean").get_all_symbols_and_roots()
        symbol_names = {s["name"] for s in all_symbols}

        expected_symbols = {
            "multiply",
            "calculate",
            "main",
        }

        missing = expected_symbols - symbol_names
        assert not missing, f"Missing expected symbols in Main.lean: {missing}"

    @pytest.mark.parametrize("language_server", [Language.LEAN4], indirect=True)
    def test_within_file_references(self, language_server: SolidLanguageServer) -> None:
        """
        Test within-file reference tracking for isPositive.

        isPositive is defined in Helper.lean line 11 (0-indexed) and used by absolute on line 15.
        """
        # isPositive defined at line 11, column 4
        references = language_server.request_references("Helper.lean", line=11, column=4)

        assert len(references) >= 1, f"Expected at least 1 reference to isPositive (used in absolute), got {len(references)}"

        # Check that isPositive is referenced within Helper.lean at line 15 (absolute calls isPositive)
        ref_locations = [(ref["relativePath"], ref["range"]["start"]["line"]) for ref in references]
        helper_refs = [(path, line) for path, line in ref_locations if "Helper.lean" in path]
        assert any(
            line == 15 for _, line in helper_refs
        ), f"Expected isPositive reference at Helper.lean:15 (in absolute), got: {ref_locations}"

    @pytest.mark.parametrize("language_server", [Language.LEAN4], indirect=True)
    def test_cross_file_references_add(self, language_server: SolidLanguageServer) -> None:
        """
        Test cross-file reference tracking for add function.

        add is defined in Helper.lean line 5 (0-indexed) and used in Main.lean on lines 7 and 15.
        """
        # add defined at line 5, column 4
        references = language_server.request_references("Helper.lean", line=5, column=4)

        assert len(references) >= 1, f"Expected at least 1 reference to add in Main.lean, got {len(references)}"

        # Check for references in Main.lean with specific lines
        ref_locations = [(ref["relativePath"], ref["range"]["start"]["line"]) for ref in references]
        main_refs = [(path, line) for path, line in ref_locations if "Main.lean" in path]
        assert len(main_refs) >= 1, f"Expected at least 1 reference to add in Main.lean, got: {ref_locations}"
        main_ref_lines = {line for _, line in main_refs}
        # add is used in Main.lean line 7 (in calculate) and line 15 (in main)
        assert (
            7 in main_ref_lines or 15 in main_ref_lines
        ), f"Expected add references at Main.lean lines 7 or 15, got lines: {main_ref_lines}"

    @pytest.mark.parametrize("language_server", [Language.LEAN4], indirect=True)
    def test_cross_file_references_calculator(self, language_server: SolidLanguageServer) -> None:
        """
        Test cross-file reference tracking for Calculator structure.

        Calculator is defined in Helper.lean line 0 (0-indexed) and used in Main.lean lines 5 and 13.
        """
        # Calculator defined at line 0, column 10
        references = language_server.request_references("Helper.lean", line=0, column=10)

        assert len(references) >= 1, f"Expected at least 1 reference to Calculator in Main.lean, got {len(references)}"

        ref_locations = [(ref["relativePath"], ref["range"]["start"]["line"]) for ref in references]
        main_refs = [(path, line) for path, line in ref_locations if "Main.lean" in path]
        assert len(main_refs) >= 1, f"Expected at least 1 reference to Calculator in Main.lean, got: {ref_locations}"
        main_ref_lines = {line for _, line in main_refs}
        # Calculator is used in Main.lean line 5 (calculate signature) and line 13 (let c : Calculator)
        assert (
            5 in main_ref_lines or 13 in main_ref_lines
        ), f"Expected Calculator references at Main.lean lines 5 or 13, got lines: {main_ref_lines}"

    @pytest.mark.parametrize("language_server", [Language.LEAN4], indirect=True)
    def test_go_to_definition_within_file(self, language_server: SolidLanguageServer) -> None:
        """
        Test go-to-definition within a file.

        In Main.lean line 19, calculate is called: 'match calculate c "multiply" 6 7 with'.
        calculate is defined at Main.lean line 5.
        """
        # calculate usage in Main.lean line 19, 'calculate' starts at col 8
        definitions = language_server.request_definition("Main.lean", line=19, column=8)

        assert len(definitions) >= 1, f"Expected at least 1 definition for calculate, got {len(definitions)}"

        def_location = definitions[0]
        assert def_location["uri"].endswith("Main.lean"), f"Expected definition in Main.lean, got: {def_location['uri']}"
        assert def_location["range"]["start"]["line"] == 5, f"Expected definition at line 5, got: {def_location['range']['start']['line']}"

    @pytest.mark.parametrize("language_server", [Language.LEAN4], indirect=True)
    def test_go_to_definition_across_files(self, language_server: SolidLanguageServer) -> None:
        """
        Test go-to-definition across files.

        In Main.lean line 15, add is called: 'add 5 3'.
        add is defined in Helper.lean line 5.
        """
        # add usage in Main.lean line 15, 'add' starts at col 19
        definitions = language_server.request_definition("Main.lean", line=15, column=19)

        assert len(definitions) >= 1, f"Expected at least 1 definition for add, got {len(definitions)}"

        def_location = definitions[0]
        assert def_location["uri"].endswith("Helper.lean"), f"Expected definition in Helper.lean, got: {def_location['uri']}"
        assert def_location["range"]["start"]["line"] == 5, f"Expected definition at line 5, got: {def_location['range']['start']['line']}"
