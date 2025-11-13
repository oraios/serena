"""
Basic integration tests for the Swift language server functionality.

These tests validate the functionality of the language server APIs
like request_references using the Swift test repository.
"""

import os
import platform

import pytest

from serena.project import Project
from serena.text_utils import LineType
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language

# Skip Swift tests on Windows due to complex GitHub Actions configuration
WINDOWS_SKIP = platform.system() == "Windows"
WINDOWS_SKIP_REASON = "GitHub Actions configuration for Swift on Windows is complex, skipping for now."

pytestmark = [pytest.mark.swift, pytest.mark.skipif(WINDOWS_SKIP, reason=WINDOWS_SKIP_REASON)]


class TestSwiftLanguageServerBasics:
    """Test basic functionality of the Swift language server."""

    @pytest.mark.parametrize("language_server", [Language.SWIFT], indirect=True)
    def test_goto_definition_calculator_class(self, language_server: SolidLanguageServer) -> None:
        """Test goto_definition on Calculator class usage."""
        file_path = os.path.join("src", "main.swift")

        # Find the Calculator usage at line 5: let calculator = Calculator()
        # Position should be at the "Calculator()" call
        definitions = language_server.request_definition(file_path, 4, 23)  # Position at Calculator() call
        assert isinstance(definitions, list), "Definitions should be a list"
        assert len(definitions) > 0, "Should find definition for Calculator class"

        # Verify the definition points to the Calculator class definition
        calculator_def = definitions[0]
        assert calculator_def.get("uri", "").endswith("main.swift"), "Definition should be in main.swift"

        # The Calculator class is defined starting at line 16
        start_line = calculator_def.get("range", {}).get("start", {}).get("line")
        assert start_line == 15, f"Calculator class definition should be at line 16, got {start_line + 1}"

    @pytest.mark.parametrize("language_server", [Language.SWIFT], indirect=True)
    def test_goto_definition_user_struct(self, language_server: SolidLanguageServer) -> None:
        """Test goto_definition on User struct usage."""
        file_path = os.path.join("src", "main.swift")

        # Find the User usage at line 9: let user = User(name: "Alice", age: 30)
        # Position should be at the "User(...)" call
        definitions = language_server.request_definition(file_path, 8, 18)  # Position at User(...) call
        assert isinstance(definitions, list), "Definitions should be a list"
        assert len(definitions) > 0, "Should find definition for User struct"

        # Verify the definition points to the User struct definition
        user_def = definitions[0]
        assert user_def.get("uri", "").endswith("main.swift"), "Definition should be in main.swift"

        # The User struct is defined starting at line 26
        start_line = user_def.get("range", {}).get("start", {}).get("line")
        assert start_line == 25, f"User struct definition should be at line 26, got {start_line + 1}"

    @pytest.mark.parametrize("language_server", [Language.SWIFT], indirect=True)
    def test_goto_definition_calculator_method(self, language_server: SolidLanguageServer) -> None:
        """Test goto_definition on Calculator method usage."""
        file_path = os.path.join("src", "main.swift")

        # Find the add method usage at line 6: let result = calculator.add(5, 3)
        # Position should be at the "add" method call
        definitions = language_server.request_definition(file_path, 5, 28)  # Position at add method call
        assert isinstance(definitions, list), "Definitions should be a list"

        # Verify the definition points to the add method definition
        add_def = definitions[0]
        assert add_def.get("uri", "").endswith("main.swift"), "Definition should be in main.swift"

        # The add method is defined starting at line 17
        start_line = add_def.get("range", {}).get("start", {}).get("line")
        assert start_line == 16, f"add method definition should be at line 17, got {start_line + 1}"

    @pytest.mark.parametrize("language_server", [Language.SWIFT], indirect=True)
    def test_goto_definition_cross_file(self, language_server: SolidLanguageServer) -> None:
        """Test goto_definition across files - Utils struct."""
        utils_file = os.path.join("src", "utils.swift")

        # First, let's check if Utils is used anywhere (it might not be in this simple test)
        # We'll test goto_definition on Utils struct itself
        symbols = language_server.request_document_symbols(utils_file).get_all_symbols_and_roots()
        utils_symbol = next((s for s in symbols[0] if s.get("name") == "Utils"), None)

        sel_start = utils_symbol["selectionRange"]["start"]
        definitions = language_server.request_definition(utils_file, sel_start["line"], sel_start["character"])
        assert isinstance(definitions, list), "Definitions should be a list"

        # Should find the Utils struct definition itself
        utils_def = definitions[0]
        assert utils_def.get("uri", "").endswith("utils.swift"), "Definition should be in utils.swift"

    @pytest.mark.parametrize("language_server", [Language.SWIFT], indirect=True)
    def test_request_references_calculator_class(self, language_server: SolidLanguageServer) -> None:
        """Test request_references on the Calculator class."""
        # Get references to the Calculator class in main.swift
        file_path = os.path.join("src", "main.swift")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        calculator_symbol = next((s for s in symbols[0] if s.get("name") == "Calculator"), None)

        sel_start = calculator_symbol["selectionRange"]["start"]
        references = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert isinstance(references, list), "References should be a list"
        assert len(references) > 0, "Calculator class should be referenced"

        # Validate that Calculator is referenced in the main function
        calculator_refs = [ref for ref in references if ref.get("uri", "").endswith("main.swift")]
        assert len(calculator_refs) > 0, "Calculator class should be referenced in main.swift"

        # Check that one reference is at line 5 (let calculator = Calculator())
        line_5_refs = [ref for ref in calculator_refs if ref.get("range", {}).get("start", {}).get("line") == 4]
        assert len(line_5_refs) > 0, "Calculator should be referenced at line 5"

    @pytest.mark.parametrize("language_server", [Language.SWIFT], indirect=True)
    def test_request_references_user_struct(self, language_server: SolidLanguageServer) -> None:
        """Test request_references on the User struct."""
        # Get references to the User struct in main.swift
        file_path = os.path.join("src", "main.swift")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        user_symbol = next((s for s in symbols[0] if s.get("name") == "User"), None)

        sel_start = user_symbol["selectionRange"]["start"]
        references = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert isinstance(references, list), "References should be a list"

        # Validate that User is referenced in the main function
        user_refs = [ref for ref in references if ref.get("uri", "").endswith("main.swift")]
        assert len(user_refs) > 0, "User struct should be referenced in main.swift"

        # Check that one reference is at line 9 (let user = User(...))
        line_9_refs = [ref for ref in user_refs if ref.get("range", {}).get("start", {}).get("line") == 8]
        assert len(line_9_refs) > 0, "User should be referenced at line 9"

    @pytest.mark.parametrize("language_server", [Language.SWIFT], indirect=True)
    def test_request_references_utils_struct(self, language_server: SolidLanguageServer) -> None:
        """Test request_references on the Utils struct."""
        # Get references to the Utils struct in utils.swift
        file_path = os.path.join("src", "utils.swift")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        utils_symbol = next((s for s in symbols[0] if s.get("name") == "Utils"), None)
        if not utils_symbol or "selectionRange" not in utils_symbol:
            raise AssertionError("Utils symbol or its selectionRange not found")
        sel_start = utils_symbol["selectionRange"]["start"]
        references = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert isinstance(references, list), "References should be a list"
        assert len(references) > 0, "Utils struct should be referenced"

        # Validate that Utils is referenced in main.swift
        utils_refs = [ref for ref in references if ref.get("uri", "").endswith("main.swift")]
        assert len(utils_refs) > 0, "Utils struct should be referenced in main.swift"

        # Check that one reference is at line 12 (Utils.calculateArea call)
        line_12_refs = [ref for ref in utils_refs if ref.get("range", {}).get("start", {}).get("line") == 11]
        assert len(line_12_refs) > 0, "Utils should be referenced at line 12"


class TestSwiftProjectBasics:
    @pytest.mark.parametrize("project", [Language.SWIFT], indirect=True)
    def test_retrieve_content_around_line(self, project: Project) -> None:
        """Test retrieve_content_around_line functionality with various scenarios."""
        file_path = os.path.join("src", "main.swift")

        # Scenario 1: Find Calculator class definition
        calculator_line = None
        for line_num in range(1, 50):  # Search first 50 lines
            try:
                line_content = project.retrieve_content_around_line(file_path, line_num)
                if line_content.lines and "class Calculator" in line_content.lines[0].line_content:
                    calculator_line = line_num
                    break
            except:
                continue

        assert calculator_line is not None, "Calculator class not found"
        line_calc = project.retrieve_content_around_line(file_path, calculator_line)
        assert len(line_calc.lines) == 1
        assert "class Calculator" in line_calc.lines[0].line_content
        assert line_calc.lines[0].line_number == calculator_line
        assert line_calc.lines[0].match_type == LineType.MATCH

        # Scenario 2: Context above and below Calculator class
        with_context_around_calculator = project.retrieve_content_around_line(file_path, calculator_line, 2, 2)
        assert len(with_context_around_calculator.lines) == 5
        assert "class Calculator" in with_context_around_calculator.matched_lines[0].line_content
        assert with_context_around_calculator.num_matched_lines == 1

        # Scenario 3: Search for struct definitions
        struct_pattern = r"struct\s+\w+"
        matches = project.search_source_files_for_pattern(struct_pattern)
        assert len(matches) > 0, "Should find struct definitions"
        # Should find User struct
        user_matches = [m for m in matches if "User" in str(m)]
        assert len(user_matches) > 0, "Should find User struct"

        # Scenario 4: Search for class definitions
        class_pattern = r"class\s+\w+"
        matches = project.search_source_files_for_pattern(class_pattern)
        assert len(matches) > 0, "Should find class definitions"
        # Should find Calculator and Circle classes
        calculator_matches = [m for m in matches if "Calculator" in str(m)]
        circle_matches = [m for m in matches if "Circle" in str(m)]
        assert len(calculator_matches) > 0, "Should find Calculator class"
        assert len(circle_matches) > 0, "Should find Circle class"

        # Scenario 5: Search for enum definitions
        enum_pattern = r"enum\s+\w+"
        matches = project.search_source_files_for_pattern(enum_pattern)
        assert len(matches) > 0, "Should find enum definitions"
        # Should find Status enum
        status_matches = [m for m in matches if "Status" in str(m)]
        assert len(status_matches) > 0, "Should find Status enum"
