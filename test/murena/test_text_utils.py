import re

import pytest

from murena.text_utils import LineType, search_files, search_text


class TestSearchText:
    def test_search_text_with_string_pattern(self):
        """Test searching with a simple string pattern."""
        content = """
        def hello_world():
            print("Hello, World!")
            return 42
        """

        # Search for a simple string pattern
        matches = search_text("print", content=content)

        assert len(matches) == 1
        assert matches[0].num_matched_lines == 1
        assert matches[0].start_line == 3
        assert matches[0].end_line == 3
        assert matches[0].lines[0].line_content.strip() == 'print("Hello, World!")'

    def test_search_text_with_regex_pattern(self):
        """Test searching with a regex pattern."""
        content = """
        class DataProcessor:
            def __init__(self, data):
                self.data = data

            def process(self):
                return [x * 2 for x in self.data if x > 0]

            def filter(self, predicate):
                return [x for x in self.data if predicate(x)]
        """

        # Search for a regex pattern matching method definitions
        pattern = r"def\s+\w+\s*\([^)]*\):"
        matches = search_text(pattern, content=content)

        assert len(matches) == 3
        assert matches[0].lines[0].match_type == LineType.MATCH
        assert "def __init__" in matches[0].lines[0].line_content
        assert "def process" in matches[1].lines[0].line_content
        assert "def filter" in matches[2].lines[0].line_content

    def test_search_text_with_compiled_regex(self):
        """Test searching with a pre-compiled regex pattern."""
        content = """
        import os
        import sys
        from pathlib import Path

        # Configuration variables
        DEBUG = True
        MAX_RETRIES = 3

        def configure_logging():
            log_level = "DEBUG" if DEBUG else "INFO"
            print(f"Setting log level to {log_level}")
        """

        # Search for variable assignments with a compiled regex
        pattern = re.compile(r"^\s*[A-Z_]+ = .+$")
        matches = search_text(pattern, content=content)

        assert len(matches) == 2
        assert "DEBUG = True" in matches[0].lines[0].line_content
        assert "MAX_RETRIES = 3" in matches[1].lines[0].line_content

    def test_search_text_with_context_lines(self):
        """Test searching with context lines before and after the match."""
        content = """
        def complex_function(a, b, c):
            # This is a complex function that does something.
            if a > b:
                return a * c
            elif b > a:
                return b * c
            else:
                return (a + b) * c
        """

        # Search with context lines
        matches = search_text("return", content=content, context_lines_before=1, context_lines_after=1)

        assert len(matches) == 3

        # Check the first match with context
        first_match = matches[0]
        assert len(first_match.lines) == 3
        assert first_match.lines[0].match_type == LineType.BEFORE_MATCH
        assert first_match.lines[1].match_type == LineType.MATCH
        assert first_match.lines[2].match_type == LineType.AFTER_MATCH

        # Verify the content of lines
        assert "if a > b:" in first_match.lines[0].line_content
        assert "return a * c" in first_match.lines[1].line_content
        assert "elif b > a:" in first_match.lines[2].line_content

    def test_search_text_with_multiline_match(self):
        """Test searching with multiline pattern matching."""
        content = """
        def factorial(n):
            if n <= 1:
                return 1
            else:
                return n * factorial(n-1)

        result = factorial(5)  # Should be 120
        """

        # Search for a pattern that spans multiple lines (if-else block)
        pattern = r"if.*?else.*?return"
        matches = search_text(pattern, content=content, allow_multiline_match=True)

        assert len(matches) == 1
        multiline_match = matches[0]
        assert multiline_match.num_matched_lines >= 3
        assert "if n <= 1:" in multiline_match.lines[0].line_content

        # All matched lines should have match_type == LineType.MATCH
        match_lines = [line for line in multiline_match.lines if line.match_type == LineType.MATCH]
        assert len(match_lines) >= 3

    def test_search_text_with_glob_pattern(self):
        """Test searching with glob-like patterns."""
        content = """
        class UserService:
            def get_user(self, user_id):
                return {"id": user_id, "name": "Test User"}

            def create_user(self, user_data):
                print(f"Creating user: {user_data}")
                return {"id": 123, **user_data}

            def update_user(self, user_id, user_data):
                print(f"Updating user {user_id} with {user_data}")
                return True
        """

        # Search with a glob pattern for all user methods
        matches = search_text("*_user*", content=content, is_glob=True)

        assert len(matches) == 3
        assert "get_user" in matches[0].lines[0].line_content
        assert "create_user" in matches[1].lines[0].line_content
        assert "update_user" in matches[2].lines[0].line_content

    def test_search_text_with_complex_glob_pattern(self):
        """Test searching with more complex glob patterns."""
        content = """
        def process_data(data):
            return [transform(item) for item in data]

        def transform(item):
            if isinstance(item, dict):
                return {k: v.upper() if isinstance(v, str) else v for k, v in item.items()}
            elif isinstance(item, list):
                return [x * 2 for x in item if isinstance(x, (int, float))]
            elif isinstance(item, str):
                return item.upper()
            else:
                return item
        """

        # Search with a simplified glob pattern to find all isinstance occurrences
        matches = search_text("*isinstance*", content=content, is_glob=True)

        # Should match lines with isinstance(item, dict) and isinstance(item, list)
        assert len(matches) >= 2
        instance_matches = [
            line.line_content
            for match in matches
            for line in match.lines
            if line.match_type == LineType.MATCH and "isinstance(item," in line.line_content
        ]
        assert len(instance_matches) >= 2
        assert any("isinstance(item, dict)" in line for line in instance_matches)
        assert any("isinstance(item, list)" in line for line in instance_matches)

    def test_search_text_glob_with_special_chars(self):
        """Glob patterns containing regex special characters should match literally."""
        content = """
        def func_square():
            print("value[42]")

        def func_curly():
            print("value{bar}")
        """

        matches_square = search_text(r"*\[42\]*", content=content, is_glob=True)
        assert len(matches_square) == 1
        assert "[42]" in matches_square[0].lines[0].line_content

        matches_curly = search_text("*{bar}*", content=content, is_glob=True)
        assert len(matches_curly) == 1
        assert "{bar}" in matches_curly[0].lines[0].line_content

    def test_search_text_no_matches(self):
        """Test searching with a pattern that doesn't match anything."""
        content = """
        def calculate_average(numbers):
            if not numbers:
                return 0
            return sum(numbers) / len(numbers)
        """

        # Search for a pattern that doesn't exist in the content
        matches = search_text("missing_function", content=content)

        assert len(matches) == 0


# Mock file reader that always returns matching content
def mock_reader_always_match(file_path: str) -> str:
    """Mock file reader that returns content guaranteed to match the simple pattern."""
    return "This line contains a match."


class TestSearchFiles:
    @pytest.mark.parametrize(
        "file_paths, pattern, paths_include_glob, paths_exclude_glob, expected_matched_files, description",
        [
            # Basic cases
            (["a.py", "b.txt"], "match", None, None, ["a.py", "b.txt"], "No filters"),
            (["a.py", "b.txt"], "match", "*.py", None, ["a.py"], "Include only .py files"),
            (["a.py", "b.txt"], "match", None, "*.txt", ["a.py"], "Exclude .txt files"),
            (["a.py", "b.txt", "c.py"], "match", "*.py", "c.*", ["a.py"], "Include .py, exclude c.*"),
            # Directory matching - Using pathspec patterns
            (["main.c", "test/main.c"], "match", "test/*", None, ["test/main.c"], "Include files in test/ subdir"),
            (["data/a.csv", "data/b.log"], "match", "data/*", "*.log", ["data/a.csv"], "Include data/*, exclude *.log"),
            (["src/a.py", "tests/b.py"], "match", "src/**", "tests/**", ["src/a.py"], "Include src/**, exclude tests/**"),
            (["src/mod/a.py", "tests/b.py"], "match", "**/*.py", "tests/**", ["src/mod/a.py"], "Include **/*.py, exclude tests/**"),
            (["file.py", "dir/file.py"], "match", "dir/*.py", None, ["dir/file.py"], "Include files directly in dir"),
            (["file.py", "dir/sub/file.py"], "match", "dir/**/*.py", None, ["dir/sub/file.py"], "Include files recursively in dir"),
            # Overlap and edge cases
            (["file.py", "dir/file.py"], "match", "*.py", "dir/*", ["file.py"], "Include *.py, exclude files directly in dir"),
            (["root.py", "adir/a.py", "bdir/b.py"], "match", "a*/*.py", None, ["adir/a.py"], "Include files in dirs starting with 'a'"),
            (["a.txt", "b.log"], "match", "*.py", None, [], "No files match include pattern"),
            (["a.py", "b.py"], "match", None, "*.py", [], "All files match exclude pattern"),
            (["a.py", "b.py"], "match", "a.*", "*.py", [], "Include a.* but exclude *.py -> empty"),
            (["a.py", "b.py"], "match", "*.py", "b.*", ["a.py"], "Include *.py but exclude b.* -> a.py"),
        ],
        ids=lambda x: x if isinstance(x, str) else "",  # Use description as test ID
    )
    def test_search_files_include_exclude(
        self, file_paths, pattern, paths_include_glob, paths_exclude_glob, expected_matched_files, description
    ):
        """
        Test the include/exclude glob filtering logic in search_files using PathSpec patterns.
        """
        results = search_files(
            relative_file_paths=file_paths,
            pattern=pattern,
            file_reader=mock_reader_always_match,
            paths_include_glob=paths_include_glob,
            paths_exclude_glob=paths_exclude_glob,
            context_lines_before=0,  # No context needed for this test focus
            context_lines_after=0,
        )

        # Extract the source file paths from the results
        actual_matched_files = sorted([result.source_file_path for result in results if result.source_file_path])

        # Assert that the matched files are exactly the ones expected
        assert actual_matched_files == sorted(expected_matched_files)

        # Basic check on results structure if files were expected
        if expected_matched_files:
            assert len(results) == len(expected_matched_files)
            for result in results:
                assert len(result.matched_lines) == 1  # Mock reader returns one matching line
                assert result.matched_lines[0].line_content == "This line contains a match."
                assert result.matched_lines[0].match_type == LineType.MATCH

    @pytest.mark.parametrize(
        "file_paths, pattern, paths_include_glob, paths_exclude_glob, expected_matched_files, description",
        [
            # Glob patterns that were problematic with gitignore syntax
            (
                ["src/murena/agent.py", "src/murena/process_isolated_agent.py", "test/agent.py"],
                "match",
                "src/**agent.py",
                None,
                ["src/murena/agent.py", "src/murena/process_isolated_agent.py"],
                "Glob: src/**agent.py should match files ending with agent.py under src/",
            ),
            (
                ["src/murena/agent.py", "src/murena/process_isolated_agent.py", "other/agent.py"],
                "match",
                "**agent.py",
                None,
                ["src/murena/agent.py", "src/murena/process_isolated_agent.py", "other/agent.py"],
                "Glob: **agent.py should match files ending with agent.py anywhere",
            ),
            (
                ["dir/subdir/file.py", "dir/other/file.py", "elsewhere/file.py"],
                "match",
                "dir/**file.py",
                None,
                ["dir/subdir/file.py", "dir/other/file.py"],
                "Glob: dir/**file.py should match files ending with file.py under dir/",
            ),
            (
                ["src/a/b/c/test.py", "src/x/test.py", "other/test.py"],
                "match",
                "src/**/test.py",
                None,
                ["src/a/b/c/test.py", "src/x/test.py"],
                "Glob: src/**/test.py should match test.py files under src/ at any depth",
            ),
            # Edge cases for ** patterns
            (
                ["agent.py", "src/agent.py", "src/murena/agent.py"],
                "match",
                "**agent.py",
                None,
                ["agent.py", "src/agent.py", "src/murena/agent.py"],
                "Glob: **agent.py should match at root and any depth",
            ),
            (["file.txt", "src/file.txt"], "match", "src/**", None, ["src/file.txt"], "Glob: src/** should match everything under src/"),
        ],
        ids=lambda x: x if isinstance(x, str) else "",  # Use description as test ID
    )
    def test_search_files_glob_patterns(
        self, file_paths, pattern, paths_include_glob, paths_exclude_glob, expected_matched_files, description
    ):
        """
        Test glob patterns that were problematic with the previous gitignore-based implementation.
        """
        results = search_files(
            relative_file_paths=file_paths,
            pattern=pattern,
            file_reader=mock_reader_always_match,
            paths_include_glob=paths_include_glob,
            paths_exclude_glob=paths_exclude_glob,
            context_lines_before=0,
            context_lines_after=0,
        )

        # Extract the source file paths from the results
        actual_matched_files = sorted([result.source_file_path for result in results if result.source_file_path])

        # Assert that the matched files are exactly the ones expected
        assert actual_matched_files == sorted(
            expected_matched_files
        ), f"Pattern '{paths_include_glob}' failed: expected {sorted(expected_matched_files)}, got {actual_matched_files}"

        # Basic check on results structure if files were expected
        if expected_matched_files:
            assert len(results) == len(expected_matched_files)
            for result in results:
                assert len(result.matched_lines) == 1  # Mock reader returns one matching line
                assert result.matched_lines[0].line_content == "This line contains a match."
                assert result.matched_lines[0].match_type == LineType.MATCH

    @pytest.mark.parametrize(
        "file_paths, pattern, paths_include_glob, paths_exclude_glob, expected_matched_files, description",
        [
            # Brace expansion in include glob
            (
                ["a.py", "b.js", "c.txt"],
                "match",
                "*.{py,js}",
                None,
                ["a.py", "b.js"],
                "Brace expansion in include glob",
            ),
            # Brace expansion in exclude glob
            (
                ["a.py", "b.log", "c.txt"],
                "match",
                "*.{py,log,txt}",
                "*.{log,txt}",
                ["a.py"],
                "Brace expansion in exclude glob",
            ),
            # Brace expansion in both include and exclude
            (
                ["src/a.ts", "src/b.js", "test/a.ts", "test/b.js"],
                "match",
                "**/*.{ts,js}",
                "test/**/*.{ts,js}",
                ["src/a.ts", "src/b.js"],
                "Brace expansion in both include and exclude",
            ),
            # No matching files with brace expansion
            (
                ["a.py", "b.js"],
                "match",
                "*.{c,h}",
                None,
                [],
                "Brace expansion with no matching files",
            ),
            # Multiple brace expansions
            (
                ["src/a/a.py", "src/b/b.py", "lib/a/a.py", "lib/b/b.py"],
                "match",
                "{src,lib}/{a,b}/*.py",
                "lib/b/*.py",
                ["src/a/a.py", "src/b/b.py", "lib/a/a.py"],
                "Multiple brace expansions in include/exclude",
            ),
        ],
        ids=lambda x: x if isinstance(x, str) else "",
    )
    def test_search_files_with_brace_expansion(
        self, file_paths, pattern, paths_include_glob, paths_exclude_glob, expected_matched_files, description
    ):
        """Test search_files with glob patterns containing brace expansions."""
        results = search_files(
            relative_file_paths=file_paths,
            pattern=pattern,
            file_reader=mock_reader_always_match,
            paths_include_glob=paths_include_glob,
            paths_exclude_glob=paths_exclude_glob,
        )

        actual_matched_files = sorted([result.source_file_path for result in results if result.source_file_path])
        assert actual_matched_files == sorted(expected_matched_files), f"Test failed: {description}"

    def test_search_files_no_pattern_match_in_content(self):
        """Test that no results are returned if the pattern doesn't match the file content, even if files pass filters."""
        file_paths = ["a.py", "b.txt"]
        pattern = "non_existent_pattern_in_mock_content"  # This won't match mock_reader_always_match content
        results = search_files(
            relative_file_paths=file_paths,
            pattern=pattern,
            file_reader=mock_reader_always_match,  # Content is "This line contains a match."
            paths_include_glob=None,  # Both files would pass filters
            paths_exclude_glob=None,
        )
        assert len(results) == 0, "Should not find matches if pattern doesn't match content"

    def test_search_files_regex_pattern_with_filters(self):
        """Test using a regex pattern works correctly along with include/exclude filters."""

        def specific_mock_reader(file_path: str) -> str:
            # Provide different content for different files to test regex matching
            if file_path == "a.py":  # noqa: SIM116
                return "File A: value=123\nFile A: value=456"
            elif file_path == "b.py":
                return "File B: value=789"
            elif file_path == "c.txt":
                return "File C: value=000"
            return "No values here."

        file_paths = ["a.py", "b.py", "c.txt"]
        pattern = r"value=(\d+)"

        results = search_files(
            relative_file_paths=file_paths,
            pattern=pattern,
            file_reader=specific_mock_reader,
            paths_include_glob="*.py",  # Only include .py files
            paths_exclude_glob="b.*",  # Exclude files starting with b
        )

        # Expected: a.py included, b.py excluded by glob, c.txt excluded by glob
        # a.py has two matches for the regex pattern
        assert len(results) == 2, "Expected 2 matches only from a.py"
        actual_matched_files = sorted([result.source_file_path for result in results if result.source_file_path])
        assert actual_matched_files == ["a.py", "a.py"], "Both matches should be from a.py"
        # Check the content of the matched lines
        assert results[0].matched_lines[0].line_content == "File A: value=123"
        assert results[1].matched_lines[0].line_content == "File A: value=456"

    def test_search_files_context_lines_with_filters(self):
        """Test context lines are included correctly when filters are active."""

        def context_mock_reader(file_path: str) -> str:
            if file_path == "include_me.txt":
                return "Line before 1\nLine before 2\nMATCH HERE\nLine after 1\nLine after 2"
            elif file_path == "exclude_me.log":
                return "Noise\nMATCH HERE\nNoise"
            return "No match"

        file_paths = ["include_me.txt", "exclude_me.log"]
        pattern = "MATCH HERE"

        results = search_files(
            relative_file_paths=file_paths,
            pattern=pattern,
            file_reader=context_mock_reader,
            paths_include_glob="*.txt",  # Only include .txt files
            paths_exclude_glob=None,
            context_lines_before=1,
            context_lines_after=1,
        )

        # Expected: Only include_me.txt should be processed and matched
        assert len(results) == 1, "Expected only one result from the included file"
        result = results[0]
        assert result.source_file_path == "include_me.txt"
        assert len(result.lines) == 3, "Expected 3 lines (1 before, 1 match, 1 after)"
        assert result.lines[0].line_content == "Line before 2", "Incorrect 'before' context line"
        assert result.lines[0].match_type == LineType.BEFORE_MATCH
        assert result.lines[1].line_content == "MATCH HERE", "Incorrect 'match' line"
        assert result.lines[1].match_type == LineType.MATCH
        assert result.lines[2].line_content == "Line after 1", "Incorrect 'after' context line"
        assert result.lines[2].match_type == LineType.AFTER_MATCH


class TestGlobMatch:
    """Test the glob_match function directly."""

    @pytest.mark.parametrize(
        "pattern, path, expected",
        [
            # Basic wildcard patterns
            ("*.py", "file.py", True),
            ("*.py", "file.txt", False),
            ("*agent.py", "agent.py", True),
            ("*agent.py", "process_isolated_agent.py", True),
            ("*agent.py", "agent_test.py", False),
            # Double asterisk patterns
            ("**agent.py", "agent.py", True),
            ("**agent.py", "src/agent.py", True),
            ("**agent.py", "src/murena/agent.py", True),
            ("**agent.py", "src/murena/process_isolated_agent.py", True),
            ("**agent.py", "agent_test.py", False),
            # Prefix with double asterisk
            ("src/**agent.py", "src/agent.py", True),
            ("src/**agent.py", "src/murena/agent.py", True),
            ("src/**agent.py", "src/murena/process_isolated_agent.py", True),
            ("src/**agent.py", "other/agent.py", False),
            ("src/**agent.py", "src/agent_test.py", False),
            # Directory patterns
            ("src/**", "src/file.py", True),
            ("src/**", "src/dir/file.py", True),
            ("src/**", "other/file.py", False),
            # Exact matches with double asterisk
            ("src/**/test.py", "src/test.py", True),
            ("src/**/test.py", "src/a/b/test.py", True),
            ("src/**/test.py", "src/test_file.py", False),
            # Simple patterns without asterisks
            ("src/file.py", "src/file.py", True),
            ("src/file.py", "src/other.py", False),
        ],
    )
    def test_glob_match(self, pattern, path, expected):
        """Test glob_match function with various patterns."""
        from src.murena.text_utils import glob_match

        assert glob_match(pattern, path) == expected


class TestExpandBraces:
    """Test the expand_braces function."""

    @pytest.mark.parametrize(
        "pattern, expected",
        [
            # Basic case
            ("src/*.{js,ts}", ["src/*.js", "src/*.ts"]),
            # No braces
            ("src/*.py", ["src/*.py"]),
            # Multiple brace sets
            ("src/{a,b}/{c,d}.py", ["src/a/c.py", "src/a/d.py", "src/b/c.py", "src/b/d.py"]),
            # Empty string
            ("", [""]),
            # Braces with empty elements
            ("src/{a,,b}.py", ["src/a.py", "src/.py", "src/b.py"]),
            # No commas
            ("src/{a}.py", ["src/a.py"]),
        ],
    )
    def test_expand_braces(self, pattern, expected):
        """Test brace expansion for glob patterns."""
        from murena.text_utils import expand_braces

        assert sorted(expand_braces(pattern)) == sorted(expected)
