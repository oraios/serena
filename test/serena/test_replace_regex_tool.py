import logging
import os
import re
import tempfile

import pytest

from serena.agent import SerenaAgent
from serena.config.serena_config import ProjectConfig, RegisteredProject, SerenaConfig
from serena.project import Project
from serena.tools import SUCCESS_RESULT
from serena.tools.file_tools import ReplaceRegexTool
from solidlsp.ls_config import Language


@pytest.fixture
def serena_config():
    """Create an in-memory configuration for tests with a temporary directory."""
    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a Project instance for the temporary directory
        project_name = "test_repo_temp"
        project = Project(
            project_root=temp_dir,
            project_config=ProjectConfig(
                project_name=project_name,
                language=Language.PYTHON,  # Using Python as the language
                ignored_paths=[],
                excluded_tools=set(),
                read_only=False,
                ignore_all_files_in_gitignore=True,
                initial_prompt="",
                encoding="utf-8",
            ),
        )

        # Create SerenaConfig with the project
        config = SerenaConfig(gui_log_window_enabled=False, web_dashboard=False, log_level=logging.ERROR)
        config.projects = [RegisteredProject.from_project_instance(project)]

        yield config, temp_dir


@pytest.fixture
def serena_agent(serena_config):
    """Create a SerenaAgent instance for testing."""
    config, _ = serena_config
    return SerenaAgent(project="test_repo_temp", serena_config=config)


class TestReplaceRegexTool:
    @pytest.fixture
    def setup(self, serena_agent, serena_config):
        """Setup test files and return the tool for testing."""
        _, temp_dir = serena_config

        # Create a test file
        test_file_path = os.path.join(temp_dir, "test_file.py")
        with open(test_file_path, "w") as f:
            f.write("print(f'Some text')\n")
            f.write("print(f'Another line')\n")

        # Create the tool
        tool = serena_agent.get_tool(ReplaceRegexTool)

        yield temp_dir, "test_file.py", tool

    def test_replace_with_newline(self, setup):
        """Test replacing text with a string containing newline escape sequences."""
        temp_dir, test_file_path, tool = setup

        # Replace text with a string containing \n
        result = tool.apply(
            relative_path=test_file_path,
            regex=r"print\(f'Some text'\)",
            repl=r"print(f'\n    Confidence Calculation Breakdown:')",
        )

        assert result == SUCCESS_RESULT

        # Read the file and check the content
        with open(os.path.join(temp_dir, test_file_path)) as f:
            content = f.read()

        # The newline should be preserved as \n, not converted to a literal newline
        assert "print(f'\\n    Confidence Calculation Breakdown:')" in content
        assert "print(f'\n    Confidence" not in content

    def test_replace_with_tab(self, setup):
        """Test replacing text with a string containing tab escape sequences."""
        temp_dir, test_file_path, tool = setup

        # Replace text with a string containing \t
        result = tool.apply(
            relative_path=test_file_path,
            regex=r"print\(f'Some text'\)",
            repl=r"print(f'\t    Indented text')",
        )

        assert result == SUCCESS_RESULT

        # Read the file and check the content
        with open(os.path.join(temp_dir, test_file_path)) as f:
            content = f.read()

        # The tab should be preserved as \t, not converted to a literal tab
        assert "print(f'\\t    Indented text')" in content

    def test_replace_with_multiple_escapes(self, setup):
        """Test replacing text with a string containing multiple escape sequences."""
        temp_dir, test_file_path, tool = setup

        # Replace text with a string containing multiple escape sequences
        result = tool.apply(
            relative_path=test_file_path,
            regex=r"print\(f'Some text'\)",
            repl=r"print(f'\n\t\r    Multiple escapes')",
        )

        assert result == SUCCESS_RESULT

        # Read the file and check the content
        with open(os.path.join(temp_dir, test_file_path)) as f:
            content = f.read()

        # All escape sequences should be preserved
        assert "print(f'\\n\\t\\r    Multiple escapes')" in content

    def test_replace_with_backreferences(self, setup):
        """Test replacing text with backreferences."""
        temp_dir, test_file_path, tool = setup

        # Create a file with content to test backreferences
        backrefs_file = os.path.join(temp_dir, "backrefs.py")
        with open(backrefs_file, "w") as f:
            f.write("def function_name(arg1, arg2):\n")
            f.write("    return arg1 + arg2\n")

        # Replace using backreferences and newlines
        result = tool.apply(
            relative_path="backrefs.py",
            regex=r"def (\w+)\((.*?)\):",
            repl=r"def \1(\2):\n    # Function with arguments: \2\n    # Returns the sum",
        )

        assert result == SUCCESS_RESULT

        # Read the file and check the content
        with open(backrefs_file) as f:
            content = f.read()

        # Backreferences should work and newlines should be preserved
        assert "def function_name(arg1, arg2):" in content
        assert "    # Function with arguments: arg1, arg2" in content
        assert "    # Returns the sum" in content

    def test_simulated_api_call(self, setup):
        """Test that simulates how the tool is called through the API."""
        temp_dir, test_file_path, tool = setup

        # Create a test file with an f-string
        fstring_file = os.path.join(temp_dir, "fstring.py")
        with open(fstring_file, "w") as f:
            f.write("print(f'Some text')\n")

        # This is how the replacement string might look when it comes from JSON
        # The \n is already escaped once in the JSON string
        json_style_repl = "print(f'\\n    Confidence Calculation Breakdown:')"

        # Apply the replacement
        result = tool.apply(
            relative_path="fstring.py",
            regex=r"print\(f'Some text'\)",
            repl=json_style_repl,
        )

        assert result == SUCCESS_RESULT

        # Read the file and check the content
        with open(fstring_file) as f:
            content = f.read()

        # The newline should be preserved as \n, not converted to a literal newline
        assert "print(f'\\n    Confidence Calculation Breakdown:')" in content
        # This is what we don't want to see - a literal newline in the string
        assert "print(f'\n    Confidence" not in content

    def test_real_world_scenario(self, setup):
        """Test that simulates the real-world scenario where the issue occurs."""
        temp_dir, test_file_path, tool = setup

        # Create a test file with an indented f-string (similar to the issue description)
        fstring_file = os.path.join(temp_dir, "real_world.py")
        with open(fstring_file, "w") as f:
            f.write("                  print(f'Some text')\n")

        # This simulates how the replacement string might be processed in production
        # The issue description shows the newline being interpreted literally
        repl = "print(f'\n   Confidence Calculation Breakdown:')"

        # Apply the replacement directly using re.sub to simulate what might be happening
        # in production without the double-escaping
        with open(fstring_file) as f:
            content = f.read()

        # This is what might be happening in production - direct substitution without proper escaping
        broken_content = re.sub(r"print\(f'Some text'\)", repl, content, flags=re.DOTALL | re.MULTILINE)

        with open(fstring_file, "w") as f:
            f.write(broken_content)

        # Read the file and check if it contains the broken string (literal newline)
        with open(fstring_file) as f:
            content = f.read()

        # This should be true if the issue is reproduced - the string is broken across lines
        assert "print(f'\n   Confidence" in content

        # Now fix the file and try with our tool
        with open(fstring_file, "w") as f:
            f.write("                  print(f'Some text')\n")

        # Apply the replacement using our tool
        result = tool.apply(
            relative_path="real_world.py",
            regex=r"print\(f'Some text'\)",
            repl=r"print(f'\n   Confidence Calculation Breakdown:')",
        )

        assert result == SUCCESS_RESULT

        # Read the file and check the content
        with open(fstring_file) as f:
            content = f.read()

        # The newline should be preserved as \n, not converted to a literal newline
        assert "print(f'\\n   Confidence Calculation Breakdown:')" in content
        # This is what we don't want to see - a literal newline in the string
        assert "print(f'\n   Confidence" not in content

    def test_regex_replacement_variations(self, setup):
        """Test different variations of regex replacement with newlines."""
        temp_dir, test_file_path, tool = setup

        # Create a test file
        test_file = os.path.join(temp_dir, "regex_variations.py")
        original_text = "print(f'Some text')"
        with open(test_file, "w") as f:
            f.write(original_text + "\n")

        # Test 1: Using a replacement string with \n
        result1 = tool.apply(
            relative_path="regex_variations.py",
            regex=r"print\(f'Some text'\)",
            repl=r"print(f'\n    Some more detailed text')",
        )

        assert result1 == SUCCESS_RESULT

        with open(test_file) as f:
            content1 = f.read()

        # The newline should be preserved as \n, not converted to a literal newline
        assert "print(f'\\n    Some more detailed text')" in content1
        assert "print(f'\n    Some" not in content1

        # Reset the file
        with open(test_file, "w") as f:
            f.write(original_text + "\n")

        # Test 2: Using a replacement string with literal newline
        result2 = tool.apply(
            relative_path="regex_variations.py",
            regex=r"print\(f'Some text'\)",
            repl="print(f'\n    Some more detailed text')",
        )

        assert result2 == SUCCESS_RESULT

        with open(test_file) as f:
            content2 = f.read()

        # The newline should be preserved as \n, not converted to a literal newline
        assert "print(f'\n    Some more detailed text')" in content2
        # Literal newline case - no additional check needed

        # Reset the file
        with open(test_file, "w") as f:
            f.write(original_text + "\n")

        # Test 3: Using a replacement string with double backslash
        result3 = tool.apply(
            relative_path="regex_variations.py",
            regex=r"print\(f'Some text'\)",
            repl=r"print(f'\\n    Some more detailed text')",
        )

        assert result3 == SUCCESS_RESULT

        with open(test_file) as f:
            content3 = f.read()

        # The double backslash should be preserved
        assert "print(f'\\\\n    Some more detailed text')" in content3

    def test_edge_cases(self, setup):
        """Test various edge cases for the ReplaceRegexTool."""
        temp_dir, _, tool = setup

        # Define test cases
        test_cases = [
            {
                "name": "Test 1: Basic newline escape sequence",
                "content": "print('Hello')",
                "regex": r"print\('Hello'\)",
                "repl": r"print(f'\n    World')",
                "expected_contains": r"print(f'\n    World')",
                "expected_not_contains": None,  # Pattern check not needed
            },
            {
                "name": "Test 2: Already escaped newline",
                "content": "print('Hello')",
                "regex": r"print\('Hello'\)",
                "repl": r"print(f'\\n    World')",
                "expected_contains": r"print(f'\\n    World')",
                "expected_not_contains": None,  # Pattern check not needed
            },
            {
                "name": "Test 3: Double escaped newline",
                "content": "print('Hello')",
                "regex": r"print\('Hello'\)",
                "repl": r"print(f'\\\\n    World')",
                "expected_contains": r"print(f'\\\\n    World')",
                "expected_not_contains": None,  # Pattern check not needed
            },
            {
                "name": "Test 4: Mixed escape sequences",
                "content": "print('Hello')",
                "regex": r"print\('Hello'\)",
                "repl": r"print(f'\n\t    World\r\n')",
                "expected_contains": r"print(f'\n\t    World\r\n')",
                "expected_not_contains": None,  # Pattern check not needed
            },
            {
                "name": "Test 5: Newline in JSON string format",
                "content": "print('Hello')",
                "regex": r"print\('Hello'\)",
                "repl": "print(f'\\n    World')",
                "expected_contains": r"print(f'\n    World')",
                "expected_not_contains": None,  # Pattern check not needed
            },
            {
                "name": "Test 6: Literal newline in string",
                "content": "print('Hello')",
                "regex": r"print\('Hello'\)",
                "repl": "print(f'\n    World')",
                "expected_contains": "print(f'\n    World')",
                "expected_not_contains": None,  # Pattern check not needed
            },
            {
                "name": "Test 7: Multiple newlines in complex string",
                "content": "print('Hello')",
                "regex": r"print\('Hello'\)",
                "repl": "if (condition) {\n    print('Line 1');\n    print('Line 2');\n}",
                "expected_contains": "if (condition) {",
                "expected_not_contains": None,  # We expect literal newlines in this case
            },
            {
                "name": "Test 8: Newline in f-string with indentation",
                "content": "                  print(f'Some text')",
                "regex": r"print\(f'Some text'\)",
                "repl": r"print(f'\n   Confidence Calculation Breakdown:')",
                "expected_contains": r"print(f'\n   Confidence Calculation Breakdown:')",
                "expected_not_contains": None,  # Pattern check not needed
            },
            {
                "name": "Test 9: Exact scenario from issue description",
                "content": "    *this >> wTag;",
                "regex": r"\*this >> wTag;",
                "repl": """    // Get file position BEFORE reading
    long preReadPos = -1;
    if (m_pFile) {
        preReadPos = m_pFile->GetPosition();
    }
    *this >> wTag;
    fprintf(stderr, "DEBUG: ReadClass at file pos 0x%lX, read wTag=0x%04X\\n", preReadPos, wTag);""",
                "expected_contains": "DEBUG: ReadClass at file pos",
                "expected_not_contains": None,  # We expect literal newlines in this case
            },
            {
                "name": "Test 10: JSON-style string with newline escape sequence",
                "content": "                  print(f'Some text')",
                "regex": r"print\(f'Some text'\)",
                "repl": "print(f'\\n    Confidence Calculation Breakdown:')",
                "expected_contains": r"print(f'\n    Confidence Calculation Breakdown:')",
                "expected_not_contains": None,  # Pattern check not needed
            },
            {
                "name": "Test 11: Multi-line JSON object from issue description",
                "content": "                  print(f'Some text')",
                "regex": r"print\(f'Some text'\)",
                "repl": '    // Get file position BEFORE reading\n    long preReadPos = -1;\n    if (m_pFile) {\n        preReadPos = m_pFile->GetPosition();\n    }\n    \n    *this >> wTag;\n    \n    fprintf(stderr, "DEBUG: ReadClass at file pos 0x%lX, read wTag=0x%04X\\n", preReadPos, wTag);',
                "expected_contains": "DEBUG: ReadClass at file pos",
                "expected_not_contains": None,  # We expect literal newlines in this case
            },
        ]

        for i, test_case in enumerate(test_cases):
            # Create a test file
            test_file = os.path.join(temp_dir, f"test_file_{i}.txt")
            with open(test_file, "w") as f:
                f.write(test_case["content"])

            # Apply the replacement
            result = tool.apply(
                relative_path=f"test_file_{i}.txt",
                regex=test_case["regex"],
                repl=test_case["repl"],
            )

            assert result == SUCCESS_RESULT, f"Failed on test case: {test_case['name']}"

            # Read the file and check the content
            with open(test_file) as f:
                content = f.read()

            # Check if the content contains the expected string
            if test_case["expected_contains"]:
                assert test_case["expected_contains"] in content, f"Expected string not found in test case: {test_case['name']}"

            # Check if the content does not contain the unexpected string
            if test_case["expected_not_contains"]:
                assert test_case["expected_not_contains"] not in content, f"Unexpected string found in test case: {test_case['name']}"

            # For string tests, check if there's a literal newline in the string
            if "print(f'" in content and test_case["expected_not_contains"]:
                # Find the position of the opening quote
                start_pos = content.find("print(f'") + len("print(f'")
                # Find the position of the closing quote
                end_pos = content.find("')", start_pos)
                # Extract the string content
                string_content = content[start_pos:end_pos]

                # Check if there's a literal newline in the string
                assert "\n" not in string_content, f"String contains literal newline in test case: {test_case['name']}"
