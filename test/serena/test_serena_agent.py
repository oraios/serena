import json
import logging
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

import pytest

from serena.agent import SerenaAgent
from serena.config.serena_config import ProjectConfig, RegisteredProject, SerenaConfig
from serena.project import Project
from serena.tools import (
    SUCCESS_RESULT,
    FindReferencingSymbolsTool,
    FindSymbolTool,
    GetDiagnosticsTool,
    ReplaceContentTool,
    ReplaceSymbolBodyTool,
)
from solidlsp.ls_config import Language
from test.conftest import get_repo_path, language_tests_enabled
from test.solidlsp import clojure as clj


@pytest.fixture
def serena_config():
    """Create an in-memory configuration for tests with test repositories pre-registered."""
    # Create test projects for all supported languages
    test_projects = []
    for language in [
        Language.PYTHON,
        Language.GO,
        Language.JAVA,
        Language.KOTLIN,
        Language.RUST,
        Language.TYPESCRIPT,
        Language.PHP,
        Language.CSHARP,
        Language.CLOJURE,
        Language.FSHARP,
        Language.POWERSHELL,
    ]:
        repo_path = get_repo_path(language)
        if repo_path.exists():
            project_name = f"test_repo_{language}"
            project = Project(
                project_root=str(repo_path),
                project_config=ProjectConfig(
                    project_name=project_name,
                    languages=[language],
                    ignored_paths=[],
                    excluded_tools=set(),
                    read_only=False,
                    ignore_all_files_in_gitignore=True,
                    initial_prompt="",
                    encoding="utf-8",
                ),
            )
            test_projects.append(RegisteredProject.from_project_instance(project))

    config = SerenaConfig(gui_log_window_enabled=False, web_dashboard=False, log_level=logging.ERROR)
    config.projects = test_projects
    return config


def read_project_file(project: Project, relative_path: str) -> str:
    """Utility function to read a file from the project."""
    file_path = os.path.join(project.project_root, relative_path)
    with open(file_path, encoding=project.project_config.encoding) as f:
        return f.read()


@contextmanager
def project_file_modification_context(serena_agent: SerenaAgent, relative_path: str) -> Iterator[None]:
    """Context manager to modify a project file and revert the changes after use."""
    project = serena_agent.get_active_project()
    file_path = os.path.join(project.project_root, relative_path)

    # Read the original content
    original_content = read_project_file(project, relative_path)

    try:
        yield
    finally:
        # Revert to the original content
        with open(file_path, "w", encoding=project.project_config.encoding) as f:
            f.write(original_content)


@pytest.fixture
def serena_agent(request: pytest.FixtureRequest, serena_config) -> Iterator[SerenaAgent]:
    language = Language(request.param)
    if not language_tests_enabled(language):
        pytest.skip(f"Tests for language {language} are not enabled.")

    project_name = f"test_repo_{language}"

    agent = SerenaAgent(project=project_name, serena_config=serena_config)

    # wait for agent to be ready
    agent.execute_task(lambda: None)

    yield agent

    # explicitly shut down to free resources
    agent.shutdown(timeout=5)


class TestSerenaAgent:
    @pytest.mark.parametrize(
        "serena_agent,symbol_name,expected_kind,expected_file",
        [
            pytest.param(Language.PYTHON, "User", "Class", "models.py", marks=pytest.mark.python),
            pytest.param(Language.GO, "Helper", "Function", "main.go", marks=pytest.mark.go),
            pytest.param(Language.JAVA, "Model", "Class", "Model.java", marks=pytest.mark.java),
            pytest.param(Language.KOTLIN, "Model", "Struct", "Model.kt", marks=pytest.mark.kotlin),
            pytest.param(Language.RUST, "add", "Function", "lib.rs", marks=pytest.mark.rust),
            pytest.param(Language.TYPESCRIPT, "DemoClass", "Class", "index.ts", marks=pytest.mark.typescript),
            pytest.param(Language.PHP, "helperFunction", "Function", "helper.php", marks=pytest.mark.php),
            pytest.param(Language.CLOJURE, "greet", "Function", clj.CORE_PATH, marks=pytest.mark.clojure),
            pytest.param(Language.CSHARP, "Calculator", "Class", "Program.cs", marks=pytest.mark.csharp),
            pytest.param(Language.FSHARP, "Calculator", "Module", "Calculator.fs", marks=pytest.mark.fsharp),
            pytest.param(Language.POWERSHELL, "function Greet-User ()", "Function", "main.ps1", marks=pytest.mark.powershell),
        ],
        indirect=["serena_agent"],
    )
    def test_find_symbol(self, serena_agent, symbol_name: str, expected_kind: str, expected_file: str):
        agent = serena_agent
        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply_ex(name_path_pattern=symbol_name)

        symbols = json.loads(result)
        assert any(
            symbol_name in s["name_path"] and expected_kind.lower() in s["kind"].lower() and expected_file in s["relative_path"]
            for s in symbols
        ), f"Expected to find {symbol_name} ({expected_kind}) in {expected_file}"

    @pytest.mark.parametrize(
        "serena_agent,symbol_name,def_file,ref_file",
        [
            pytest.param(
                Language.PYTHON,
                "User",
                os.path.join("test_repo", "models.py"),
                os.path.join("test_repo", "services.py"),
                marks=pytest.mark.python,
            ),
            pytest.param(Language.GO, "Helper", "main.go", "main.go", marks=pytest.mark.go),
            pytest.param(
                Language.JAVA,
                "Model",
                os.path.join("src", "main", "java", "test_repo", "Model.java"),
                os.path.join("src", "main", "java", "test_repo", "Main.java"),
                marks=pytest.mark.java,
            ),
            pytest.param(
                Language.KOTLIN,
                "Model",
                os.path.join("src", "main", "kotlin", "test_repo", "Model.kt"),
                os.path.join("src", "main", "kotlin", "test_repo", "Main.kt"),
                marks=pytest.mark.kotlin,
            ),
            pytest.param(Language.RUST, "add", os.path.join("src", "lib.rs"), os.path.join("src", "main.rs"), marks=pytest.mark.rust),
            pytest.param(Language.TYPESCRIPT, "helperFunction", "index.ts", "use_helper.ts", marks=pytest.mark.typescript),
            pytest.param(Language.PHP, "helperFunction", "helper.php", "index.php", marks=pytest.mark.php),
            pytest.param(
                Language.CLOJURE,
                "multiply",
                clj.CORE_PATH,
                clj.UTILS_PATH,
                marks=pytest.mark.clojure,
            ),
            pytest.param(Language.CSHARP, "Calculator", "Program.cs", "Program.cs", marks=pytest.mark.csharp),
            pytest.param(Language.FSHARP, "add", "Calculator.fs", "Program.fs", marks=pytest.mark.fsharp),
            pytest.param(Language.POWERSHELL, "function Greet-User ()", "main.ps1", "main.ps1", marks=pytest.mark.powershell),
        ],
        indirect=["serena_agent"],
    )
    def test_find_symbol_references(self, serena_agent, symbol_name: str, def_file: str, ref_file: str) -> None:
        agent = serena_agent

        # Find the symbol location first
        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply_ex(name_path_pattern=symbol_name, relative_path=def_file)

        time.sleep(1)
        symbols = json.loads(result)
        # Find the definition
        def_symbol = symbols[0]

        # Now find references
        find_refs_tool = agent.get_tool(FindReferencingSymbolsTool)
        result = find_refs_tool.apply_ex(name_path=def_symbol["name_path"], relative_path=def_symbol["relative_path"])

        refs = json.loads(result)
        assert any(
            ref["relative_path"] == ref_file for ref in refs
        ), f"Expected to find reference to {symbol_name} in {ref_file}. refs={refs}"

    @pytest.mark.parametrize(
        "serena_agent,name_path,substring_matching,expected_symbol_name,expected_kind,expected_file",
        [
            pytest.param(
                Language.PYTHON,
                "OuterClass/NestedClass",
                False,
                "NestedClass",
                "Class",
                os.path.join("test_repo", "nested.py"),
                id="exact_qualname_class",
                marks=pytest.mark.python,
            ),
            pytest.param(
                Language.PYTHON,
                "OuterClass/NestedClass/find_me",
                False,
                "find_me",
                "Method",
                os.path.join("test_repo", "nested.py"),
                id="exact_qualname_method",
                marks=pytest.mark.python,
            ),
            pytest.param(
                Language.PYTHON,
                "OuterClass/NestedCl",  # Substring for NestedClass
                True,
                "NestedClass",
                "Class",
                os.path.join("test_repo", "nested.py"),
                id="substring_qualname_class",
                marks=pytest.mark.python,
            ),
            pytest.param(
                Language.PYTHON,
                "OuterClass/NestedClass/find_m",  # Substring for find_me
                True,
                "find_me",
                "Method",
                os.path.join("test_repo", "nested.py"),
                id="substring_qualname_method",
                marks=pytest.mark.python,
            ),
            pytest.param(
                Language.PYTHON,
                "/OuterClass",  # Absolute path
                False,
                "OuterClass",
                "Class",
                os.path.join("test_repo", "nested.py"),
                id="absolute_qualname_class",
                marks=pytest.mark.python,
            ),
            pytest.param(
                Language.PYTHON,
                "/OuterClass/NestedClass/find_m",  # Absolute path with substring
                True,
                "find_me",
                "Method",
                os.path.join("test_repo", "nested.py"),
                id="absolute_substring_qualname_method",
                marks=pytest.mark.python,
            ),
        ],
        indirect=["serena_agent"],
    )
    def test_find_symbol_name_path(
        self,
        serena_agent,
        name_path: str,
        substring_matching: bool,
        expected_symbol_name: str,
        expected_kind: str,
        expected_file: str,
    ):
        agent = serena_agent

        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply_ex(
            name_path_pattern=name_path,
            depth=0,
            relative_path=None,
            include_body=False,
            include_kinds=None,
            exclude_kinds=None,
            substring_matching=substring_matching,
        )

        symbols = json.loads(result)
        assert any(
            expected_symbol_name == s["name_path"].split("/")[-1]
            and expected_kind.lower() in s["kind"].lower()
            and expected_file in s["relative_path"]
            for s in symbols
        ), f"Expected to find {name_path} ({expected_kind}) in {expected_file}. Symbols: {symbols}"

    @pytest.mark.parametrize(
        "serena_agent,name_path",
        [
            pytest.param(
                Language.PYTHON,
                "/NestedClass",  # Absolute path, NestedClass is not top-level
                id="absolute_path_non_top_level_no_match",
                marks=pytest.mark.python,
            ),
            pytest.param(
                Language.PYTHON,
                "/NoSuchParent/NestedClass",  # Absolute path with non-existent parent
                id="absolute_path_non_existent_parent_no_match",
                marks=pytest.mark.python,
            ),
        ],
        indirect=["serena_agent"],
    )
    def test_find_symbol_name_path_no_match(
        self,
        serena_agent,
        name_path: str,
    ):
        agent = serena_agent

        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply_ex(
            name_path_pattern=name_path,
            depth=0,
            substring_matching=True,
        )

        symbols = json.loads(result)
        assert not symbols, f"Expected to find no symbols for {name_path}. Symbols found: {symbols}"

    @pytest.mark.parametrize(
        "serena_agent,name_path,num_expected",
        [
            pytest.param(
                Language.JAVA,
                "Model/getName",
                2,
                id="overloaded_java_method",
                marks=pytest.mark.java,
            ),
        ],
        indirect=["serena_agent"],
    )
    def test_find_symbol_overloaded_function(self, serena_agent: SerenaAgent, name_path: str, num_expected: int):
        """
        Tests whether the FindSymbolTool can find all overloads of a function/method
        (provided that the overload id remains unspecified in the name path)
        """
        agent = serena_agent

        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply_ex(
            name_path_pattern=name_path,
            depth=0,
            substring_matching=False,
        )

        symbols = json.loads(result)
        assert (
            len(symbols) == num_expected
        ), f"Expected to find {num_expected} symbols for overloaded function {name_path}. Symbols found: {symbols}"

    @pytest.mark.parametrize(
        "serena_agent,name_path,relative_path",
        [
            pytest.param(
                Language.JAVA,
                "Model/getName",
                os.path.join("src", "main", "java", "test_repo", "Model.java"),
                id="overloaded_java_method",
                marks=pytest.mark.java,
            ),
        ],
        indirect=["serena_agent"],
    )
    def test_non_unique_symbol_reference_error(self, serena_agent: SerenaAgent, name_path: str, relative_path: str):
        """
        Tests whether the tools operating on a well-defined symbol raises an error when the symbol reference is non-unique.
        We exemplarily test a retrieval tool (FindReferencingSymbolsTool) and an editing tool (ReplaceSymbolBodyTool).
        """
        match_text = "multiple"

        find_refs_tool = serena_agent.get_tool(FindReferencingSymbolsTool)
        with pytest.raises(ValueError, match=match_text):
            find_refs_tool.apply(name_path=name_path, relative_path=relative_path)

        replace_symbol_body_tool = serena_agent.get_tool(ReplaceSymbolBodyTool)
        with pytest.raises(ValueError, match=match_text):
            replace_symbol_body_tool.apply(name_path=name_path, relative_path=relative_path, body="")

    @pytest.mark.parametrize(
        "serena_agent",
        [
            pytest.param(
                Language.TYPESCRIPT,
                marks=pytest.mark.typescript,
            ),
        ],
        indirect=["serena_agent"],
    )
    def test_replace_content_regex_with_wildcard_ok(self, serena_agent: SerenaAgent):
        """
        Tests a regex-based content replacement that has a unique match
        """
        relative_path = "ws_manager.js"
        with project_file_modification_context(serena_agent, relative_path):
            replace_content_tool = serena_agent.get_tool(ReplaceContentTool)
            result = replace_content_tool.apply(
                needle=r'catch \(error\) \{\s*console.error\("Failed to connect.*?\}',
                repl='catch(error) { console.log("Never mind"); }',
                relative_path=relative_path,
                mode="regex",
            )
            assert result == SUCCESS_RESULT

    @pytest.mark.parametrize(
        "serena_agent",
        [
            pytest.param(
                Language.TYPESCRIPT,
                marks=pytest.mark.typescript,
            ),
        ],
        indirect=["serena_agent"],
    )
    @pytest.mark.parametrize("mode", ["literal", "regex"])
    def test_replace_content_with_backslashes(self, serena_agent: SerenaAgent, mode: Literal["literal", "regex"]):
        """
        Tests a content replacement where the needle and replacement strings contain backslashes.
        This is a regression test for escaping issues.
        """
        relative_path = "ws_manager.js"
        needle = r'console.log("WebSocketManager initializing\nStatus OK");'
        repl = r'console.log("WebSocketManager initialized\nAll systems go!");'
        replace_content_tool = serena_agent.get_tool(ReplaceContentTool)
        mode: Literal["literal", "regex"]
        with project_file_modification_context(serena_agent, relative_path):
            result = replace_content_tool.apply(
                needle=re.escape(needle) if mode == "regex" else needle,
                repl=repl,
                relative_path=relative_path,
                mode=mode,
            )
            assert result == SUCCESS_RESULT
            new_content = read_project_file(serena_agent.get_active_project(), relative_path)
            assert repl in new_content

    @pytest.mark.parametrize(
        "serena_agent",
        [
            pytest.param(
                Language.TYPESCRIPT,
                marks=pytest.mark.typescript,
            ),
        ],
        indirect=["serena_agent"],
    )
    def test_replace_content_regex_with_wildcard_ambiguous(self, serena_agent: SerenaAgent):
        """
        Tests that an ambiguous replacement where there is a larger match that internally contains
        a smaller match triggers an exception
        """
        replace_content_tool = serena_agent.get_tool(ReplaceContentTool)
        with pytest.raises(ValueError, match="ambiguous"):
            replace_content_tool.apply(
                needle=r'catch \(error\) \{.*?this\.updateConnectionStatus\("Connection failed", false\);.*?\}',
                repl='catch(error) { console.log("Never mind"); }',
                relative_path="ws_manager.js",
                mode="regex",
            )

    @pytest.mark.parametrize(
        "serena_agent,error_content,file_ext",
        [
            pytest.param(Language.PYTHON, "def foo(\n", ".py", marks=pytest.mark.python),
            pytest.param(Language.TYPESCRIPT, "function foo( {\n", ".ts", marks=pytest.mark.typescript),
            pytest.param(Language.RUST, "fn foo( {\n", ".rs", marks=pytest.mark.rust),
        ],
        indirect=["serena_agent"],
    )
    def test_get_diagnostics(self, serena_agent: SerenaAgent, error_content: str, file_ext: str):
        """Test GetDiagnosticsTool returns diagnostics for files with errors."""
        project = serena_agent.get_active_project()

        # Create a temporary file with a syntax error
        error_file = os.path.join(project.project_root, f"temp_error_file{file_ext}")
        try:
            with open(error_file, "w") as f:
                f.write(error_content)

            get_diagnostics_tool = serena_agent.get_tool(GetDiagnosticsTool)
            result = get_diagnostics_tool.apply_ex(relative_path=f"temp_error_file{file_ext}")

            diagnostics = json.loads(result)
            assert "diagnostics" in diagnostics
            assert "total" in diagnostics
            assert diagnostics["total"] >= 1
            # Verify diagnostic structure and content
            first_diagnostic = diagnostics["diagnostics"][0]
            assert "file" in first_diagnostic
            assert "line" in first_diagnostic
            assert "severity" in first_diagnostic
            assert "message" in first_diagnostic
            assert first_diagnostic["file"] == f"temp_error_file{file_ext}"
            assert first_diagnostic["severity"] == "Error"
        finally:
            if os.path.exists(error_file):
                os.remove(error_file)

    @pytest.mark.parametrize(
        "serena_agent",
        [pytest.param(Language.PYTHON, marks=pytest.mark.python)],
        indirect=["serena_agent"],
    )
    def test_get_diagnostics_all_files(self, serena_agent: SerenaAgent):
        """Test GetDiagnosticsTool returns diagnostics for all files when path is empty."""
        project = serena_agent.get_active_project()

        error_file = os.path.join(project.project_root, "temp_all_files_test.py")
        try:
            with open(error_file, "w") as f:
                f.write("def foo(\n")

            get_diagnostics_tool = serena_agent.get_tool(GetDiagnosticsTool)
            # First open the file to trigger diagnostics collection
            get_diagnostics_tool.apply_ex(relative_path="temp_all_files_test.py")
            # Now get all diagnostics
            result = get_diagnostics_tool.apply_ex(relative_path="")

            diagnostics = json.loads(result)
            assert "diagnostics" in diagnostics
            assert "total" in diagnostics
            # Should include diagnostics from the error file
            files_with_diagnostics = {d["file"] for d in diagnostics["diagnostics"]}
            assert "temp_all_files_test.py" in files_with_diagnostics
        finally:
            if os.path.exists(error_file):
                os.remove(error_file)

    @pytest.mark.parametrize(
        "serena_agent",
        [pytest.param(Language.PYTHON, marks=pytest.mark.python)],
        indirect=["serena_agent"],
    )
    def test_get_diagnostics_min_severity(self, serena_agent: SerenaAgent):
        """Test GetDiagnosticsTool filters by min_severity."""
        project = serena_agent.get_active_project()

        error_file = os.path.join(project.project_root, "temp_severity_test.py")
        try:
            with open(error_file, "w") as f:
                f.write("def foo(\n")

            get_diagnostics_tool = serena_agent.get_tool(GetDiagnosticsTool)
            # min_severity=1 means only errors (severity 1 in LSP)
            result = get_diagnostics_tool.apply_ex(relative_path="temp_severity_test.py", min_severity=1)

            diagnostics = json.loads(result)
            assert "diagnostics" in diagnostics
            # All returned diagnostics should be errors
            for diagnostic in diagnostics["diagnostics"]:
                assert diagnostic["severity"] == "Error"
        finally:
            if os.path.exists(error_file):
                os.remove(error_file)
