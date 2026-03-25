import json
import logging
import os
import re
import shutil
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
    FindDefiningSymbolAtLocationTool,
    FindDefiningSymbolTool,
    FindImplementationsTool,
    FindReferencingSymbolsTool,
    FindSymbolTool,
    GetDiagnosticsForFileTool,
    GetDiagnosticsForSymbolTool,
    ReplaceContentTool,
    ReplaceSymbolBodyTool,
)
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind
from test.conftest import (
    find_identifier_occurrence_position,
    get_repo_path,
    is_ci,
    language_has_verified_implementation_support,
    language_tests_enabled,
)
from test.diagnostics_cases import WORKING_DIAGNOSTIC_TOOL_CASE_PARAMS, DiagnosticCase
from test.solidlsp import clojure as clj

DEFINING_SYMBOL_TOOL_TEST_CASES = [
    pytest.param(
        Language.PYTHON,
        os.path.join("test_repo", "services.py"),
        "User",
        1,
        1,
        "User",
        "models.py",
        marks=pytest.mark.python,
    ),
    pytest.param(
        Language.PYTHON_TY,
        os.path.join("test_repo", "services.py"),
        "User",
        1,
        1,
        "User",
        "models.py",
        marks=pytest.mark.python,
    ),
    pytest.param(Language.GO, "main.go", "Helper", 0, 1, "Helper", "main.go", marks=pytest.mark.go),
    pytest.param(
        Language.JAVA,
        os.path.join("src", "main", "java", "test_repo", "Main.java"),
        "Model",
        0,
        1,
        "Model",
        "Model.java",
        marks=pytest.mark.java,
    ),
    pytest.param(
        Language.KOTLIN,
        os.path.join("src", "main", "kotlin", "test_repo", "Main.kt"),
        "Model",
        0,
        1,
        "Model",
        "Model.kt",
        marks=[pytest.mark.kotlin] + ([pytest.mark.skip(reason="Kotlin LSP JVM crashes on restart in CI")] if is_ci else []),
    ),
    pytest.param(
        Language.RUST,
        os.path.join("src", "main.rs"),
        "format_greeting",
        0,
        1,
        "format_greeting",
        "lib.rs",
        marks=pytest.mark.rust,
    ),
    pytest.param(Language.PHP, "index.php", "helperFunction", 0, 5, "helperFunction", "helper.php", marks=pytest.mark.php),
    pytest.param(
        Language.CLOJURE,
        clj.UTILS_PATH,
        "multiply",
        0,
        1,
        "multiply",
        clj.CORE_PATH,
        marks=[
            pytest.mark.clojure,
            pytest.mark.skipif(not clj.is_clojure_cli_available(), reason="clojure CLI is not installed"),
        ],
    ),
    pytest.param(Language.CSHARP, "Program.cs", "Add", 0, 1, "Add", "Program.cs", marks=pytest.mark.csharp),
    pytest.param(
        Language.POWERSHELL,
        "main.ps1",
        "Convert-ToUpperCase",
        0,
        1,
        "function Convert-ToUpperCase ()",
        "utils.ps1",
        marks=pytest.mark.powershell,
    ),
    pytest.param(Language.CPP_CCLS, "a.cpp", "add", 0, 1, "add", "b.cpp", marks=pytest.mark.cpp),
    pytest.param(
        Language.LEAN4,
        "Main.lean",
        "add",
        0,
        1,
        "add",
        "Helper.lean",
        marks=[
            pytest.mark.lean4,
            pytest.mark.skipif(shutil.which("lean") is None, reason="Lean is not installed"),
        ],
    ),
    pytest.param(Language.TYPESCRIPT, "index.ts", "helperFunction", 1, 1, "helperFunction", "index.ts", marks=pytest.mark.typescript),
    pytest.param(
        Language.FSHARP,
        "Program.fs",
        "add",
        0,
        1,
        "add",
        "Calculator.fs",
        marks=[pytest.mark.fsharp, pytest.mark.xfail(reason="F# language server cannot reliably resolve defining symbols")],
    ),
]

REGEX_DEFINING_SYMBOL_TOOL_TEST_CASES = [
    pytest.param(
        Language.PYTHON,
        os.path.join("test_repo", "services.py"),
        r"from \.models import Item, (User)",
        "",
        "User",
        "models.py",
        marks=pytest.mark.python,
    ),
    pytest.param(
        Language.PYTHON,
        os.path.join("test_repo", "services.py"),
        r"=\s+(User)\(",
        "UserService/create_user",
        "User",
        "models.py",
        marks=pytest.mark.python,
    ),
    pytest.param(
        Language.PYTHON_TY,
        os.path.join("test_repo", "services.py"),
        r"=\s+(User)\(",
        "UserService/create_user",
        "User",
        "models.py",
        marks=pytest.mark.python,
    ),
    pytest.param(
        Language.GO,
        "main.go",
        r"var greeter (Greeter) =",
        "main",
        "Greeter",
        "main.go",
        marks=pytest.mark.go,
    ),
]

IMPLEMENTATION_TOOL_TEST_CASE_DATA = [
    (
        Language.CSHARP,
        "IGreeter/FormatGreeting",
        os.path.join("Services", "IGreeter.cs"),
        os.path.join("Services", "ConsoleGreeter.cs"),
        "FormatGreeting",
        pytest.mark.csharp,
    ),
    (
        Language.GO,
        "Greeter/FormatGreeting",
        "main.go",
        "main.go",
        "(ConsoleGreeter).FormatGreeting",
        pytest.mark.go,
    ),
    (
        Language.JAVA,
        "Greeter/formatGreeting",
        os.path.join("src", "main", "java", "test_repo", "Greeter.java"),
        os.path.join("src", "main", "java", "test_repo", "ConsoleGreeter.java"),
        "formatGreeting",
        pytest.mark.java,
    ),
    (
        Language.RUST,
        "Greeter/format_greeting",
        os.path.join("src", "lib.rs"),
        os.path.join("src", "lib.rs"),
        "format_greeting",
        pytest.mark.rust,
    ),
    (
        Language.TYPESCRIPT,
        "Greeter/formatGreeting",
        "formatters.ts",
        "formatters.ts",
        "formatGreeting",
        pytest.mark.typescript,
    ),
]

IMPLEMENTATION_TOOL_TEST_CASES = [
    pytest.param(language, symbol_name, def_file, impl_file, expected_symbol_name, marks=mark)
    for language, symbol_name, def_file, impl_file, expected_symbol_name, mark in IMPLEMENTATION_TOOL_TEST_CASE_DATA
    if language_has_verified_implementation_support(language)
]


@pytest.fixture
def serena_config():
    config = SerenaConfig(gui_log_window=False, web_dashboard=False, log_level=logging.ERROR)

    # Create test projects for all supported languages
    test_projects = []
    for language in [
        Language.PYTHON,
        Language.PYTHON_TY,
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
        Language.CPP_CCLS,
        Language.LEAN4,
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
                    excluded_tools=[],
                    read_only=False,
                    ignore_all_files_in_gitignore=True,
                    initial_prompt="",
                    encoding="utf-8",
                ),
                serena_config=config,
            )
            test_projects.append(RegisteredProject.from_project_instance(project))

    config.projects = test_projects
    return config


def read_project_file(project: Project, relative_path: str) -> str:
    """Utility function to read a file from the project."""
    file_path = os.path.join(project.project_root, relative_path)
    with open(file_path, encoding=project.project_config.encoding) as f:
        return f.read()


def parse_edit_diagnostics_result(result: str) -> dict:
    """Utility function to parse the diagnostic payload returned by edit tools."""
    prefix = "Edit introduced new warning-or-higher diagnostics: "
    assert result.startswith(prefix), result
    return json.loads(result[len(prefix) :])


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
    @pytest.mark.parametrize("project", [None, str(get_repo_path(Language.PYTHON)), "non_existent_path"])
    def test_agent_instantiation(self, project: str | None):
        """
        Tests agent instantiation for cases where
          * no project is specified at startup
          * a valid project path is specified at startup
          * an invalid project path is specified at startup
        All cases must not raise an exception.
        """
        serena_config = SerenaConfig(gui_log_window=False, web_dashboard=False)
        SerenaAgent(project=project, serena_config=serena_config)

    def _assert_find_symbol(self, serena_agent: SerenaAgent, symbol_name: str, expected_kind: str, expected_file: str) -> None:
        agent = serena_agent
        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply(name_path_pattern=symbol_name, include_info=True)

        symbols = json.loads(result)
        assert any(
            symbol_name in s["name_path"] and expected_kind.lower() in s["kind"].lower() and expected_file in s["relative_path"]
            for s in symbols
        ), f"Expected to find {symbol_name} ({expected_kind}) in {expected_file}"
        # testing retrieval of symbol info
        if serena_agent.get_active_lsp_languages() == [Language.KOTLIN]:
            # kotlin LS doesn't seem to provide hover info right now, at least for the struct we test this on
            return
        for s in symbols:
            if s["kind"] in (SymbolKind.File.name, SymbolKind.Module.name):
                # we ignore file and module symbols for the info test
                continue
            symbol_info = s.get("info")
            assert symbol_info, f"Expected symbol info to be present for symbol: {s}"
            assert symbol_name in s["info"], (
                f"[{serena_agent.get_active_lsp_languages()[0]}] Expected symbol info to contain symbol name {symbol_name}. Info: {s['info']}"
            )
            # special additional test for Java, since Eclipse returns hover in a complex format and we want to make sure to get it right
            if s["kind"] == SymbolKind.Class.name and serena_agent.get_active_lsp_languages() == [Language.JAVA]:
                assert "A simple model class" in symbol_info, f"Java class docstring not found in symbol info: {s}"

    @pytest.mark.php
    @pytest.mark.parametrize("serena_agent", [Language.PHP], indirect=True)
    def test_find_symbol_within_php_file(self, serena_agent: SerenaAgent) -> None:
        """Verify find_symbol with a PHP file path routes to the PHP language server.

        This validates the fix in symbol.py (LanguageServerSymbolRetriever.find_symbols):
        when within_relative_path points to a PHP file, the retriever must use
        get_language_server() rather than iterating all language servers. Without this
        fix, non-PHP servers reject the PHP file and no symbols are returned.
        """
        find_symbol_tool = serena_agent.get_tool(FindSymbolTool)
        sample_php = "sample.php"

        result = find_symbol_tool.apply(name_path_pattern="Dog/greet", relative_path=sample_php)
        symbols = json.loads(result)

        assert len(symbols) > 0, (
            f"Expected to find Dog/greet in {sample_php} but got empty result. "
            "This may indicate that find_symbol is not routing to the PHP language server for PHP files."
        )
        assert any("greet" in s["name_path"] and sample_php in s["relative_path"] for s in symbols), (
            f"Dog/greet not found in {sample_php}. Symbols: {symbols}"
        )

    @pytest.mark.parametrize(
        "serena_agent,symbol_name,expected_kind,expected_file",
        [
            pytest.param(Language.PYTHON, "User", "Class", "models.py", marks=pytest.mark.python),
            pytest.param(Language.GO, "Helper", "Function", "main.go", marks=pytest.mark.go),
            pytest.param(Language.JAVA, "Model", "Class", "Model.java", marks=pytest.mark.java),
            pytest.param(
                Language.KOTLIN,
                "Model",
                "Struct",
                "Model.kt",
                marks=[pytest.mark.kotlin] + ([pytest.mark.skip(reason="Kotlin LSP JVM crashes on restart in CI")] if is_ci else []),
            ),
            pytest.param(Language.TYPESCRIPT, "DemoClass", "Class", "index.ts", marks=pytest.mark.typescript),
            pytest.param(Language.PHP, "helperFunction", "Function", "helper.php", marks=pytest.mark.php),
            pytest.param(Language.CLOJURE, "greet", "Function", clj.CORE_PATH, marks=pytest.mark.clojure),
            pytest.param(Language.CSHARP, "Calculator", "Class", "Program.cs", marks=pytest.mark.csharp),
            pytest.param(Language.POWERSHELL, "function Greet-User ()", "Function", "main.ps1", marks=pytest.mark.powershell),
            pytest.param(Language.CPP_CCLS, "add", "Function", "b.cpp", marks=pytest.mark.cpp),
            pytest.param(Language.LEAN4, "add", "Method", "Helper.lean", marks=pytest.mark.lean4),
        ],
        indirect=["serena_agent"],
    )
    def test_find_symbol_stable(self, serena_agent: SerenaAgent, symbol_name: str, expected_kind: str, expected_file: str) -> None:
        self._assert_find_symbol(serena_agent, symbol_name, expected_kind, expected_file)

    @pytest.mark.parametrize(
        "serena_agent,symbol_name,expected_kind,expected_file",
        [
            pytest.param(Language.FSHARP, "Calculator", "Module", "Calculator.fs", marks=pytest.mark.fsharp),
        ],
        indirect=["serena_agent"],
    )
    @pytest.mark.xfail(reason="F# language server is unreliable")  # See issue #1040
    def test_find_symbol_fsharp(self, serena_agent: SerenaAgent, symbol_name: str, expected_kind: str, expected_file: str) -> None:
        self._assert_find_symbol(serena_agent, symbol_name, expected_kind, expected_file)

    @pytest.mark.parametrize(
        "serena_agent,symbol_name,expected_kind,expected_file",
        [
            pytest.param(Language.RUST, "add", "Function", "lib.rs", marks=pytest.mark.rust),
        ],
        indirect=["serena_agent"],
    )
    @pytest.mark.xfail(reason="Rust language server is unreliable")  # See issue #1040
    def test_find_symbol_rust(self, serena_agent: SerenaAgent, symbol_name: str, expected_kind: str, expected_file: str) -> None:
        self._assert_find_symbol(serena_agent, symbol_name, expected_kind, expected_file)

    def _assert_find_symbol_references(self, serena_agent: SerenaAgent, symbol_name: str, def_file: str, ref_file: str) -> None:
        agent = serena_agent

        # Find the symbol location first
        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply(name_path_pattern=symbol_name, relative_path=def_file)

        time.sleep(1)
        symbols = json.loads(result)
        # Find the definition
        def_symbol = symbols[0]

        # Now find references
        find_refs_tool = agent.get_tool(FindReferencingSymbolsTool)
        result = find_refs_tool.apply(name_path=def_symbol["name_path"], relative_path=def_symbol["relative_path"])

        def contains_ref_with_relative_path(refs, relative_path):
            """
            Checks for reference to relative path, regardless of output format (grouped an ungrouped)
            """
            if isinstance(refs, list):
                for ref in refs:
                    if contains_ref_with_relative_path(ref, relative_path):
                        return True
            elif isinstance(refs, dict):
                if relative_path in refs:
                    return True
                for value in refs.values():
                    if contains_ref_with_relative_path(value, relative_path):
                        return True
            return False

        refs = json.loads(result)
        assert contains_ref_with_relative_path(refs, ref_file), f"Expected to find reference to {symbol_name} in {ref_file}. refs={refs}"

    def _assert_find_symbol_implementations(
        self,
        serena_agent: SerenaAgent,
        symbol_name: str,
        def_file: str,
        impl_file: str,
        expected_symbol_name: str,
    ) -> None:
        agent = serena_agent

        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply(name_path_pattern=symbol_name, relative_path=def_file)
        symbols = json.loads(result)
        assert symbols, f"Expected to find symbol {symbol_name} in {def_file}"

        def_symbol = symbols[0]
        find_impl_tool = agent.get_tool(FindImplementationsTool)
        result = find_impl_tool.apply(name_path=def_symbol["name_path"], relative_path=def_symbol["relative_path"], include_info=True)
        implementations = json.loads(result)

        assert any(
            impl_file in implementation["relative_path"]
            and (
                implementation.get("name") == expected_symbol_name
                or implementation.get("name_path") == expected_symbol_name
                or expected_symbol_name in implementation.get("info", "")
            )
            for implementation in implementations
        ), f"Expected to find implementation of {symbol_name} in {impl_file}. implementations={implementations}"

        for implementation in implementations:
            if implementation["kind"] in (SymbolKind.File.name, SymbolKind.Module.name):
                continue
            symbol_info = implementation.get("info")
            assert symbol_info, f"Expected symbol info to be present for implementation: {implementation}"

    def _assert_find_defining_symbol(
        self,
        serena_agent: SerenaAgent,
        relative_path: str,
        identifier: str,
        occurrence_index: int,
        column_offset: int,
        expected_name: str,
        expected_definition_file: str,
    ) -> None:
        project_root = get_repo_path(serena_agent.get_active_lsp_languages()[0])
        position = find_identifier_occurrence_position(project_root / relative_path, identifier, occurrence_index, column_offset)
        assert position is not None, f"Could not find occurrence {occurrence_index} of {identifier!r} in {relative_path}"

        find_defining_symbol_tool = serena_agent.get_tool(FindDefiningSymbolAtLocationTool)
        result = find_defining_symbol_tool.apply(relative_path=relative_path, line=position[0], column=position[1], include_info=True)
        defining_symbol = json.loads(result)

        assert defining_symbol is not None, f"Expected defining symbol for {identifier!r} in {relative_path}"
        assert defining_symbol.get("relative_path") is not None
        assert expected_definition_file in defining_symbol["relative_path"], (
            f"Expected defining symbol in {expected_definition_file!r}, got: {defining_symbol}"
        )
        assert (
            defining_symbol.get("name") == expected_name
            or defining_symbol.get("name_path") == expected_name
            or expected_name in defining_symbol.get("info", "")
        ), f"Expected defining symbol name {expected_name!r}, got: {defining_symbol}"

        if serena_agent.get_active_lsp_languages() == [Language.KOTLIN]:
            return
        if defining_symbol["kind"] not in (SymbolKind.File.name, SymbolKind.Module.name):
            assert defining_symbol.get("info"), f"Expected defining symbol info to be present: {defining_symbol}"

    def _assert_find_defining_symbol_by_regex(
        self,
        serena_agent: SerenaAgent,
        relative_path: str,
        regex: str,
        containing_symbol_name_path: str,
        expected_name: str,
        expected_definition_file: str,
    ) -> None:
        find_defining_symbol_tool = serena_agent.get_tool(FindDefiningSymbolTool)
        result = find_defining_symbol_tool.apply(
            regex=regex,
            relative_path=relative_path,
            containing_symbol_name_path=containing_symbol_name_path,
            include_info=True,
        )
        defining_symbol = json.loads(result)

        assert defining_symbol is not None, f"Expected defining symbol for regex {regex!r} in {relative_path}"
        assert defining_symbol.get("relative_path") is not None
        assert expected_definition_file in defining_symbol["relative_path"], (
            f"Expected defining symbol in {expected_definition_file!r}, got: {defining_symbol}"
        )
        assert (
            defining_symbol.get("name") == expected_name
            or defining_symbol.get("name_path") == expected_name
            or expected_name in defining_symbol.get("info", "")
        ), f"Expected defining symbol name {expected_name!r}, got: {defining_symbol}"

        if serena_agent.get_active_lsp_languages() == [Language.KOTLIN]:
            return
        if defining_symbol["kind"] not in (SymbolKind.File.name, SymbolKind.Module.name):
            assert defining_symbol.get("info"), f"Expected defining symbol info to be present: {defining_symbol}"

    def _assert_diagnostics_for_file(
        self,
        serena_agent: SerenaAgent,
        diagnostic_case: DiagnosticCase,
        start_line: int = 0,
        end_line: int = -1,
    ) -> None:
        diagnostics_tool = serena_agent.get_tool(GetDiagnosticsForFileTool)
        result = diagnostics_tool.apply(
            relative_path=diagnostic_case.relative_path,
            start_line=start_line,
            end_line=end_line,
            min_severity=1,
        )
        grouped_diagnostics = json.loads(result)

        assert diagnostic_case.relative_path in grouped_diagnostics, grouped_diagnostics
        severity_group = grouped_diagnostics[diagnostic_case.relative_path]
        assert "Error" in severity_group, severity_group
        name_path_group = severity_group["Error"]

        for expected_name_path in [diagnostic_case.primary_symbol_name_path, diagnostic_case.reference_symbol_name_path]:
            assert expected_name_path in name_path_group, name_path_group

        diagnostic_messages = [
            diagnostic["message"] for diagnostics_for_name_path in name_path_group.values() for diagnostic in diagnostics_for_name_path
        ]
        for expected_fragment in [diagnostic_case.primary_message_fragment, diagnostic_case.reference_message_fragment]:
            assert any(expected_fragment in message for message in diagnostic_messages), diagnostic_messages

    def _assert_diagnostics_for_symbol(
        self,
        serena_agent: SerenaAgent,
        diagnostic_case: DiagnosticCase,
        check_symbol_references: bool,
    ) -> None:
        diagnostics_tool = serena_agent.get_tool(GetDiagnosticsForSymbolTool)
        result = diagnostics_tool.apply(
            name_path=diagnostic_case.primary_symbol_name_path,
            reference_file=diagnostic_case.relative_path,
            check_symbol_references=check_symbol_references,
            min_severity=1,
        )
        grouped_diagnostics = json.loads(result)
        diagnostics_file = diagnostic_case.relative_path

        assert diagnostics_file in grouped_diagnostics, grouped_diagnostics
        severity_group = grouped_diagnostics[diagnostics_file]
        assert "Error" in severity_group, severity_group
        name_path_group = severity_group["Error"]

        expected_name_paths = [diagnostic_case.primary_symbol_name_path]
        expected_message_fragments = [diagnostic_case.primary_message_fragment]
        if check_symbol_references:
            expected_name_paths.append(diagnostic_case.reference_symbol_name_path)
            expected_message_fragments.append(diagnostic_case.reference_message_fragment)

        assert set(expected_name_paths).issubset(name_path_group.keys()), name_path_group
        diagnostic_messages = [
            diagnostic["message"] for diagnostics_for_name_path in name_path_group.values() for diagnostic in diagnostics_for_name_path
        ]
        for expected_fragment in expected_message_fragments:
            assert any(expected_fragment in message for message in diagnostic_messages), diagnostic_messages

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
                marks=[pytest.mark.kotlin] + ([pytest.mark.skip(reason="Kotlin LSP JVM crashes on restart in CI")] if is_ci else []),
            ),
            pytest.param(Language.RUST, "add", os.path.join("src", "lib.rs"), os.path.join("src", "main.rs"), marks=pytest.mark.rust),
            pytest.param(Language.PHP, "helperFunction", "helper.php", "index.php", marks=pytest.mark.php),
            pytest.param(
                Language.CLOJURE,
                "multiply",
                clj.CORE_PATH,
                clj.UTILS_PATH,
                marks=pytest.mark.clojure,
            ),
            pytest.param(Language.CSHARP, "Calculator", "Program.cs", "Program.cs", marks=pytest.mark.csharp),
            pytest.param(Language.POWERSHELL, "function Greet-User ()", "main.ps1", "main.ps1", marks=pytest.mark.powershell),
            pytest.param(Language.CPP_CCLS, "add", "b.cpp", "a.cpp", marks=pytest.mark.cpp),
            pytest.param(Language.LEAN4, "add", "Helper.lean", "Main.lean", marks=pytest.mark.lean4),
        ],
        indirect=["serena_agent"],
    )
    def test_find_symbol_references_stable(self, serena_agent: SerenaAgent, symbol_name: str, def_file: str, ref_file: str) -> None:
        self._assert_find_symbol_references(serena_agent, symbol_name, def_file, ref_file)

    @pytest.mark.parametrize(
        "serena_agent,symbol_name,def_file,ref_file",
        [
            pytest.param(Language.TYPESCRIPT, "helperFunction", "index.ts", "use_helper.ts", marks=pytest.mark.typescript),
        ],
        indirect=["serena_agent"],
    )
    @pytest.mark.xfail(False, reason="TypeScript language server is unreliable")  # NOTE: Testing; may be resolved by #1120; See issue #1040
    def test_find_symbol_references_typescript(self, serena_agent: SerenaAgent, symbol_name: str, def_file: str, ref_file: str) -> None:
        self._assert_find_symbol_references(serena_agent, symbol_name, def_file, ref_file)

    @pytest.mark.parametrize(
        "serena_agent,symbol_name,def_file,ref_file",
        [
            pytest.param(Language.FSHARP, "add", "Calculator.fs", "Program.fs", marks=pytest.mark.fsharp),
        ],
        indirect=["serena_agent"],
    )
    @pytest.mark.xfail(reason="F# language server is unreliable")  # See issue #1040
    def test_find_symbol_references_fsharp(self, serena_agent: SerenaAgent, symbol_name: str, def_file: str, ref_file: str) -> None:
        self._assert_find_symbol_references(serena_agent, symbol_name, def_file, ref_file)

    @pytest.mark.parametrize(
        "serena_agent,relative_path,identifier,occurrence_index,column_offset,expected_name,expected_definition_file",
        DEFINING_SYMBOL_TOOL_TEST_CASES,
        indirect=["serena_agent"],
    )
    def test_find_defining_symbol(
        self,
        serena_agent: SerenaAgent,
        relative_path: str,
        identifier: str,
        occurrence_index: int,
        column_offset: int,
        expected_name: str,
        expected_definition_file: str,
    ) -> None:
        self._assert_find_defining_symbol(
            serena_agent,
            relative_path,
            identifier,
            occurrence_index,
            column_offset,
            expected_name,
            expected_definition_file,
        )

    @pytest.mark.parametrize(
        "serena_agent,relative_path,regex,containing_symbol_name_path,expected_name,expected_definition_file",
        REGEX_DEFINING_SYMBOL_TOOL_TEST_CASES,
        indirect=["serena_agent"],
    )
    def test_find_defining_symbol_by_regex(
        self,
        serena_agent: SerenaAgent,
        relative_path: str,
        regex: str,
        containing_symbol_name_path: str,
        expected_name: str,
        expected_definition_file: str,
    ) -> None:
        self._assert_find_defining_symbol_by_regex(
            serena_agent,
            relative_path,
            regex,
            containing_symbol_name_path,
            expected_name,
            expected_definition_file,
        )

    @pytest.mark.parametrize(
        "serena_agent,relative_path,regex,containing_symbol_name_path,error_fragment",
        [
            pytest.param(
                Language.PYTHON,
                os.path.join("test_repo", "services.py"),
                r"(User)",
                "",
                "Expected exactly one regex match",
                marks=pytest.mark.python,
            ),
            pytest.param(
                Language.PYTHON,
                os.path.join("test_repo", "services.py"),
                r"User",
                "UserService/create_user",
                "must contain exactly one capturing group",
                marks=pytest.mark.python,
            ),
        ],
        indirect=["serena_agent"],
    )
    def test_find_defining_symbol_by_regex_error(
        self,
        serena_agent: SerenaAgent,
        relative_path: str,
        regex: str,
        containing_symbol_name_path: str,
        error_fragment: str,
    ) -> None:
        find_defining_symbol_tool = serena_agent.get_tool(FindDefiningSymbolTool)
        result = find_defining_symbol_tool.apply(
            regex=regex,
            relative_path=relative_path,
            containing_symbol_name_path=containing_symbol_name_path,
        )
        assert result.startswith("Error: "), result
        assert error_fragment in result, result

    @pytest.mark.parametrize("serena_agent,diagnostic_case", WORKING_DIAGNOSTIC_TOOL_CASE_PARAMS, indirect=["serena_agent"])
    def test_get_diagnostics_for_file(self, serena_agent: SerenaAgent, diagnostic_case: DiagnosticCase) -> None:
        self._assert_diagnostics_for_file(
            serena_agent,
            diagnostic_case=diagnostic_case,
        )

    @pytest.mark.parametrize("serena_agent,diagnostic_case", WORKING_DIAGNOSTIC_TOOL_CASE_PARAMS, indirect=["serena_agent"])
    def test_get_diagnostics_for_file_in_range(self, serena_agent: SerenaAgent, diagnostic_case: DiagnosticCase) -> None:
        project_root = get_repo_path(diagnostic_case.language)
        primary_position = find_identifier_occurrence_position(
            project_root / diagnostic_case.relative_path, diagnostic_case.primary_symbol_identifier
        )
        reference_position = find_identifier_occurrence_position(
            project_root / diagnostic_case.relative_path, diagnostic_case.reference_symbol_identifier
        )
        assert primary_position is not None
        assert reference_position is not None

        self._assert_diagnostics_for_file(
            serena_agent,
            diagnostic_case=DiagnosticCase(
                language=diagnostic_case.language,
                relative_path=diagnostic_case.relative_path,
                primary_symbol_name_path=diagnostic_case.primary_symbol_name_path,
                primary_symbol_identifier=diagnostic_case.primary_symbol_identifier,
                reference_symbol_name_path=diagnostic_case.primary_symbol_name_path,
                reference_symbol_identifier=diagnostic_case.reference_symbol_identifier,
                primary_message_fragment=diagnostic_case.primary_message_fragment,
                reference_message_fragment=diagnostic_case.primary_message_fragment,
            ),
            start_line=primary_position[0],
            end_line=reference_position[0] - 1,
        )

    @pytest.mark.parametrize("serena_agent,diagnostic_case", WORKING_DIAGNOSTIC_TOOL_CASE_PARAMS, indirect=["serena_agent"])
    def test_get_diagnostics_for_symbol(self, serena_agent: SerenaAgent, diagnostic_case: DiagnosticCase) -> None:
        self._assert_diagnostics_for_symbol(
            serena_agent,
            diagnostic_case=diagnostic_case,
            check_symbol_references=False,
        )

    @pytest.mark.parametrize("serena_agent,diagnostic_case", WORKING_DIAGNOSTIC_TOOL_CASE_PARAMS, indirect=["serena_agent"])
    def test_get_diagnostics_for_symbol_with_references(self, serena_agent: SerenaAgent, diagnostic_case: DiagnosticCase) -> None:
        self._assert_diagnostics_for_symbol(
            serena_agent,
            diagnostic_case=diagnostic_case,
            check_symbol_references=True,
        )

    if IMPLEMENTATION_TOOL_TEST_CASES:

        @pytest.mark.parametrize(
            "serena_agent,symbol_name,def_file,impl_file,expected_symbol_name",
            IMPLEMENTATION_TOOL_TEST_CASES,
            indirect=["serena_agent"],
        )
        def test_find_symbol_implementations(
            self,
            serena_agent: SerenaAgent,
            symbol_name: str,
            def_file: str,
            impl_file: str,
            expected_symbol_name: str,
        ) -> None:
            self._assert_find_symbol_implementations(serena_agent, symbol_name, def_file, impl_file, expected_symbol_name)

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
        assert len(symbols) == num_expected, (
            f"Expected to find {num_expected} symbols for overloaded function {name_path}. Symbols found: {symbols}"
        )

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
            pytest.param(Language.PYTHON, marks=pytest.mark.python),
            pytest.param(Language.PYTHON_TY, marks=pytest.mark.python),
        ],
        indirect=["serena_agent"],
    )
    def test_replace_content_reports_new_diagnostics(self, serena_agent: SerenaAgent):
        """Tests that file-level edits report newly introduced diagnostics."""
        relative_path = os.path.join("test_repo", "services.py")
        replace_content_tool = serena_agent.get_tool(ReplaceContentTool)

        with project_file_modification_context(serena_agent, relative_path):
            result = replace_content_tool.apply(
                relative_path=relative_path,
                needle="return container",
                repl="return missing_container",
                mode="literal",
            )

        diagnostics = parse_edit_diagnostics_result(result)
        relative_path_result = diagnostics[relative_path]
        diagnostic_messages = json.dumps(relative_path_result)
        assert "missing_container" in diagnostic_messages
        assert "create_service_container" in diagnostic_messages

    @pytest.mark.parametrize(
        "serena_agent",
        [
            pytest.param(Language.PYTHON, marks=pytest.mark.python),
            pytest.param(Language.PYTHON_TY, marks=pytest.mark.python),
        ],
        indirect=["serena_agent"],
    )
    def test_replace_symbol_body_reports_new_diagnostics(self, serena_agent: SerenaAgent):
        """Tests that symbol-level edits report newly introduced diagnostics."""
        relative_path = os.path.join("test_repo", "services.py")
        replace_symbol_body_tool = serena_agent.get_tool(ReplaceSymbolBodyTool)

        with project_file_modification_context(serena_agent, relative_path):
            result = replace_symbol_body_tool.apply(
                name_path="create_service_container",
                relative_path=relative_path,
                body="""
def create_service_container() -> dict[str, Any]:
    return missing_container
""",
            )

        diagnostics = parse_edit_diagnostics_result(result)
        relative_path_result = diagnostics[relative_path]
        diagnostic_messages = json.dumps(relative_path_result)
        assert "missing_container" in diagnostic_messages
        assert "create_service_container" in diagnostic_messages

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
