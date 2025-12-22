"""
Basic integration tests for the language server functionality.

These tests validate the functionality of the language server APIs
like request_references using the test repository.
"""

import os

import pytest

from serena.project import Project
from serena.text_utils import LineType
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.python
class TestLanguageServerBasics:
    """Test basic functionality of the language server."""

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_request_references_user_class(self, language_server: SolidLanguageServer) -> None:
        """Test request_references on the User class."""
        # Get references to the User class in models.py
        file_path = os.path.join("test_repo", "models.py")
        # Line 31 contains the User class definition
        # Use selectionRange only
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        user_symbol = next((s for s in symbols[0] if s.get("name") == "User"), None)
        if not user_symbol or "selectionRange" not in user_symbol:
            raise AssertionError("User symbol or its selectionRange not found")
        sel_start = user_symbol["selectionRange"]["start"]
        references = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert len(references) > 1, "User class should be referenced in multiple files (using selectionRange if present)"

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_request_references_item_class(self, language_server: SolidLanguageServer) -> None:
        """Test request_references on the Item class."""
        # Get references to the Item class in models.py
        file_path = os.path.join("test_repo", "models.py")
        # Line 56 contains the Item class definition
        # Use selectionRange only
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        item_symbol = next((s for s in symbols[0] if s.get("name") == "Item"), None)
        if not item_symbol or "selectionRange" not in item_symbol:
            raise AssertionError("Item symbol or its selectionRange not found")
        sel_start = item_symbol["selectionRange"]["start"]
        references = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        services_references = [ref for ref in references if "services.py" in ref["uri"]]
        assert len(services_references) > 0, "At least one reference should be in services.py (using selectionRange if present)"

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_request_references_function_parameter(self, language_server: SolidLanguageServer) -> None:
        """Test request_references on a function parameter."""
        # Get references to the id parameter in get_user method
        file_path = os.path.join("test_repo", "services.py")
        # Line 24 contains the get_user method with id parameter
        # Use selectionRange only
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        get_user_symbol = next((s for s in symbols[0] if s.get("name") == "get_user"), None)
        if not get_user_symbol or "selectionRange" not in get_user_symbol:
            raise AssertionError("get_user symbol or its selectionRange not found")
        sel_start = get_user_symbol["selectionRange"]["start"]
        references = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert len(references) > 0, "id parameter should be referenced within the method (using selectionRange if present)"

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_request_references_create_user_method(self, language_server: SolidLanguageServer) -> None:
        # Get references to the create_user method in UserService
        file_path = os.path.join("test_repo", "services.py")
        # Line 15 contains the create_user method definition
        # Use selectionRange only
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        create_user_symbol = next((s for s in symbols[0] if s.get("name") == "create_user"), None)
        if not create_user_symbol or "selectionRange" not in create_user_symbol:
            raise AssertionError("create_user symbol or its selectionRange not found")
        sel_start = create_user_symbol["selectionRange"]["start"]
        references = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert len(references) > 1, "Should get valid references for create_user (using selectionRange if present)"


class TestProjectBasics:
    @pytest.mark.parametrize("project", [Language.PYTHON], indirect=True)
    def test_retrieve_content_around_line(self, project: Project) -> None:
        """Test retrieve_content_around_line functionality with various scenarios."""
        file_path = os.path.join("test_repo", "models.py")

        # Scenario 1: Just a single line (User class definition)
        line_31 = project.retrieve_content_around_line(file_path, 31)
        assert len(line_31.lines) == 1
        assert "class User(BaseModel):" in line_31.lines[0].line_content
        assert line_31.lines[0].line_number == 31
        assert line_31.lines[0].match_type == LineType.MATCH

        # Scenario 2: Context above and below
        with_context_around_user = project.retrieve_content_around_line(file_path, 31, 2, 2)
        assert len(with_context_around_user.lines) == 5
        # Check line content
        assert "class User(BaseModel):" in with_context_around_user.matched_lines[0].line_content
        assert with_context_around_user.num_matched_lines == 1
        assert "    User model representing a system user." in with_context_around_user.lines[4].line_content
        # Check line numbers
        assert with_context_around_user.lines[0].line_number == 29
        assert with_context_around_user.lines[1].line_number == 30
        assert with_context_around_user.lines[2].line_number == 31
        assert with_context_around_user.lines[3].line_number == 32
        assert with_context_around_user.lines[4].line_number == 33
        # Check match types
        assert with_context_around_user.lines[0].match_type == LineType.BEFORE_MATCH
        assert with_context_around_user.lines[1].match_type == LineType.BEFORE_MATCH
        assert with_context_around_user.lines[2].match_type == LineType.MATCH
        assert with_context_around_user.lines[3].match_type == LineType.AFTER_MATCH
        assert with_context_around_user.lines[4].match_type == LineType.AFTER_MATCH

        # Scenario 3a: Only context above
        with_context_above = project.retrieve_content_around_line(file_path, 31, 3, 0)
        assert len(with_context_above.lines) == 4
        assert "return cls(id=id, name=name)" in with_context_above.lines[0].line_content
        assert "class User(BaseModel):" in with_context_above.matched_lines[0].line_content
        assert with_context_above.num_matched_lines == 1
        # Check line numbers
        assert with_context_above.lines[0].line_number == 28
        assert with_context_above.lines[1].line_number == 29
        assert with_context_above.lines[2].line_number == 30
        assert with_context_above.lines[3].line_number == 31
        # Check match types
        assert with_context_above.lines[0].match_type == LineType.BEFORE_MATCH
        assert with_context_above.lines[1].match_type == LineType.BEFORE_MATCH
        assert with_context_above.lines[2].match_type == LineType.BEFORE_MATCH
        assert with_context_above.lines[3].match_type == LineType.MATCH

        # Scenario 3b: Only context below
        with_context_below = project.retrieve_content_around_line(file_path, 31, 0, 3)
        assert len(with_context_below.lines) == 4
        assert "class User(BaseModel):" in with_context_below.matched_lines[0].line_content
        assert with_context_below.num_matched_lines == 1
        assert with_context_below.lines[0].line_number == 31
        assert with_context_below.lines[1].line_number == 32
        assert with_context_below.lines[2].line_number == 33
        assert with_context_below.lines[3].line_number == 34
        # Check match types
        assert with_context_below.lines[0].match_type == LineType.MATCH
        assert with_context_below.lines[1].match_type == LineType.AFTER_MATCH
        assert with_context_below.lines[2].match_type == LineType.AFTER_MATCH
        assert with_context_below.lines[3].match_type == LineType.AFTER_MATCH

        # Scenario 4a: Edge case - context above but line is at 0
        first_line_with_context_around = project.retrieve_content_around_line(file_path, 0, 2, 1)
        assert len(first_line_with_context_around.lines) <= 4  # Should have at most 4 lines (line 0 + 1 below + up to 2 above)
        assert first_line_with_context_around.lines[0].line_number <= 2  # First line should be at most line 2
        # Check match type for the target line
        for line in first_line_with_context_around.lines:
            if line.line_number == 0:
                assert line.match_type == LineType.MATCH
            elif line.line_number < 0:
                assert line.match_type == LineType.BEFORE_MATCH
            else:
                assert line.match_type == LineType.AFTER_MATCH

        # Scenario 4b: Edge case - context above but line is at 1
        second_line_with_context_above = project.retrieve_content_around_line(file_path, 1, 3, 1)
        assert len(second_line_with_context_above.lines) <= 5  # Should have at most 5 lines (line 1 + 1 below + up to 3 above)
        assert second_line_with_context_above.lines[0].line_number <= 1  # First line should be at most line 1
        # Check match type for the target line
        for line in second_line_with_context_above.lines:
            if line.line_number == 1:
                assert line.match_type == LineType.MATCH
            elif line.line_number < 1:
                assert line.match_type == LineType.BEFORE_MATCH
            else:
                assert line.match_type == LineType.AFTER_MATCH

        # Scenario 4c: Edge case - context below but line is at the end of file
        # First get the total number of lines in the file
        all_content = project.read_file(file_path)
        total_lines = len(all_content.split("\n"))

        last_line_with_context_around = project.retrieve_content_around_line(file_path, total_lines - 1, 1, 3)
        assert len(last_line_with_context_around.lines) <= 5  # Should have at most 5 lines (last line + 1 above + up to 3 below)
        assert last_line_with_context_around.lines[-1].line_number >= total_lines - 4  # Last line should be at least total_lines - 4
        # Check match type for the target line
        for line in last_line_with_context_around.lines:
            if line.line_number == total_lines - 1:
                assert line.match_type == LineType.MATCH
            elif line.line_number < total_lines - 1:
                assert line.match_type == LineType.BEFORE_MATCH
            else:
                assert line.match_type == LineType.AFTER_MATCH

    @pytest.mark.parametrize("project", [Language.PYTHON], indirect=True)
    def test_search_files_for_pattern(self, project: Project) -> None:
        """Test search_files_for_pattern with various patterns and glob filters."""
        # Test 1: Search for class definitions across all files
        class_pattern = r"class\s+\w+\s*(?:\([^{]*\)|:)"
        matches = project.search_source_files_for_pattern(class_pattern)
        assert len(matches) > 0
        # Should find multiple classes like User, Item, BaseModel, etc.
        assert len(matches) >= 5

        # Test 2: Search for specific class with include glob
        user_class_pattern = r"class\s+User\s*(?:\([^{]*\)|:)"
        matches = project.search_source_files_for_pattern(user_class_pattern, paths_include_glob="**/models.py")
        assert len(matches) == 1  # Should only find User class in models.py
        assert matches[0].source_file_path is not None
        assert "models.py" in matches[0].source_file_path

        # Test 3: Search for method definitions with exclude glob
        method_pattern = r"def\s+\w+\s*\([^)]*\):"
        matches = project.search_source_files_for_pattern(method_pattern, paths_exclude_glob="**/models.py")
        assert len(matches) > 0
        # Should find methods in services.py but not in models.py
        assert all(match.source_file_path is not None and "models.py" not in match.source_file_path for match in matches)

        # Test 4: Search for specific method with both include and exclude globs
        create_user_pattern = r"def\s+create_user\s*\([^)]*\)(?:\s*->[^:]+)?:"
        matches = project.search_source_files_for_pattern(
            create_user_pattern, paths_include_glob="**/*.py", paths_exclude_glob="**/models.py"
        )
        assert len(matches) == 1  # Should only find create_user in services.py
        assert matches[0].source_file_path is not None
        assert "services.py" in matches[0].source_file_path

        # Test 5: Search for a pattern that should appear in multiple files
        init_pattern = r"def\s+__init__\s*\([^)]*\):"
        matches = project.search_source_files_for_pattern(init_pattern)
        assert len(matches) > 1  # Should find __init__ in multiple classes
        # Should find __init__ in both models.py and services.py
        assert any(match.source_file_path is not None and "models.py" in match.source_file_path for match in matches)
        assert any(match.source_file_path is not None and "services.py" in match.source_file_path for match in matches)

        # Test 6: Search with a pattern that should have no matches
        no_match_pattern = r"def\s+this_method_does_not_exist\s*\([^)]*\):"
        matches = project.search_source_files_for_pattern(no_match_pattern)
        assert len(matches) == 0
