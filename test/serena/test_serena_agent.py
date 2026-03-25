import json
import logging
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

import pytest
from _pytest.mark import Mark, MarkDecorator

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
    SafeDeleteSymbol,
)
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind
from test.conftest import (
    find_identifier_occurrence_position,
    get_pytest_markers,
    get_repo_path,
    is_ci,
    language_has_verified_implementation_support,
    language_tests_enabled,
)
from test.diagnostics_cases import WORKING_DIAGNOSTIC_TOOL_CASE_PARAMS, DiagnosticCase
from test.solidlsp import clojure as clj


@dataclass(frozen=True)
class BaseCase:
    language: Language

    def to_pytest_param(self, *marks: MarkDecorator | Mark, id: str) -> object:
        return pytest.param(self.language, self, marks=[*get_pytest_markers(self.language), *marks], id=id)


@dataclass(frozen=True)
class FindSymbolCase(BaseCase):
    symbol_name: str
    expected_kind: str
    expected_file: str


@dataclass(frozen=True)
class FindReferenceCase(BaseCase):
    symbol_name: str
    definition_file: str
    reference_file: str


@dataclass(frozen=True)
class FindDefiningSymbolCase(BaseCase):
    relative_path: str
    identifier: str
    occurrence_index: int
    column_offset: int
    expected_name: str
    expected_definition_file: str


@dataclass(frozen=True)
class RegexDefiningSymbolCase(BaseCase):
    relative_path: str
    regex: str
    containing_symbol_name_path: str
    expected_name: str
    expected_definition_file: str


@dataclass(frozen=True)
class RegexDefiningSymbolErrorCase(BaseCase):
    relative_path: str
    regex: str
    containing_symbol_name_path: str
    error_fragment: str


@dataclass(frozen=True)
class FindImplementationCase(BaseCase):
    symbol_name: str
    definition_file: str
    implementation_file: str
    expected_symbol_name: str


@dataclass(frozen=True)
class FindSymbolNamePathCase(BaseCase):
    name_path: str
    substring_matching: bool
    expected_symbol_name: str
    expected_kind: str
    expected_file: str


@dataclass(frozen=True)
class FindSymbolNoMatchCase(BaseCase):
    name_path: str


@dataclass(frozen=True)
class FindSymbolOverloadedCase(BaseCase):
    name_path: str
    num_expected: int


@dataclass(frozen=True)
class NonUniqueSymbolReferenceCase(BaseCase):
    name_path: str
    relative_path: str
    expected_error_fragment: str = "multiple"


@dataclass(frozen=True)
class SafeDeleteCase(BaseCase):
    name_path: str
    relative_path: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "relative_path", self.relative_path.replace("\\", "/"))


FIND_DEFINING_SYMBOL_CASES = [
    FindDefiningSymbolCase(
        language=Language.PYTHON,
        relative_path=os.path.join("test_repo", "services.py"),
        identifier="User",
        occurrence_index=1,
        column_offset=1,
        expected_name="User",
        expected_definition_file="models.py",
    ).to_pytest_param(id="python_user_in_services"),
    FindDefiningSymbolCase(
        language=Language.PYTHON_TY,
        relative_path=os.path.join("test_repo", "services.py"),
        identifier="User",
        occurrence_index=1,
        column_offset=1,
        expected_name="User",
        expected_definition_file="models.py",
    ).to_pytest_param(id="python_ty_user_in_services"),
    FindDefiningSymbolCase(
        language=Language.GO,
        relative_path="main.go",
        identifier="Helper",
        occurrence_index=0,
        column_offset=1,
        expected_name="Helper",
        expected_definition_file="main.go",
    ).to_pytest_param(id="go_helper_in_main"),
    FindDefiningSymbolCase(
        language=Language.JAVA,
        relative_path=os.path.join("src", "main", "java", "test_repo", "Main.java"),
        identifier="Model",
        occurrence_index=0,
        column_offset=1,
        expected_name="Model",
        expected_definition_file="Model.java",
    ).to_pytest_param(id="java_model_in_main"),
    FindDefiningSymbolCase(
        language=Language.KOTLIN,
        relative_path=os.path.join("src", "main", "kotlin", "test_repo", "Main.kt"),
        identifier="Model",
        occurrence_index=0,
        column_offset=1,
        expected_name="Model",
        expected_definition_file="Model.kt",
    ).to_pytest_param(id="kotlin_model_in_main"),
    FindDefiningSymbolCase(
        language=Language.RUST,
        relative_path=os.path.join("src", "main.rs"),
        identifier="format_greeting",
        occurrence_index=0,
        column_offset=1,
        expected_name="format_greeting",
        expected_definition_file="lib.rs",
    ).to_pytest_param(id="rust_format_greeting"),
    FindDefiningSymbolCase(
        language=Language.PHP,
        relative_path="index.php",
        identifier="helperFunction",
        occurrence_index=0,
        column_offset=5,
        expected_name="helperFunction",
        expected_definition_file="helper.php",
    ).to_pytest_param(id="php_helper_function"),
    FindDefiningSymbolCase(
        language=Language.CLOJURE,
        relative_path=clj.UTILS_PATH,
        identifier="multiply",
        occurrence_index=0,
        column_offset=1,
        expected_name="multiply",
        expected_definition_file=clj.CORE_PATH,
    ).to_pytest_param(id="clojure_multiply_in_utils"),
    FindDefiningSymbolCase(
        language=Language.CSHARP,
        relative_path="Program.cs",
        identifier="Add",
        occurrence_index=0,
        column_offset=1,
        expected_name="Add",
        expected_definition_file="Program.cs",
    ).to_pytest_param(id="csharp_add_in_program"),
    FindDefiningSymbolCase(
        language=Language.POWERSHELL,
        relative_path="main.ps1",
        identifier="Convert-ToUpperCase",
        occurrence_index=0,
        column_offset=1,
        expected_name="function Convert-ToUpperCase ()",
        expected_definition_file="utils.ps1",
    ).to_pytest_param(id="powershell_convert_to_uppercase"),
    FindDefiningSymbolCase(
        language=Language.CPP_CCLS,
        relative_path="a.cpp",
        identifier="add",
        occurrence_index=0,
        column_offset=1,
        expected_name="add",
        expected_definition_file="b.cpp",
    ).to_pytest_param(id="cpp_add_in_a"),
    FindDefiningSymbolCase(
        language=Language.LEAN4,
        relative_path="Main.lean",
        identifier="add",
        occurrence_index=1,
        column_offset=1,
        expected_name="add",
        expected_definition_file="Helper.lean",
    ).to_pytest_param(id="lean_add_in_main"),
    FindDefiningSymbolCase(
        language=Language.TYPESCRIPT,
        relative_path="index.ts",
        identifier="helperFunction",
        occurrence_index=1,
        column_offset=1,
        expected_name="helperFunction",
        expected_definition_file="index.ts",
    ).to_pytest_param(id="typescript_helper_function"),
    FindDefiningSymbolCase(
        language=Language.FSHARP,
        relative_path="Program.fs",
        identifier="add",
        occurrence_index=0,
        column_offset=1,
        expected_name="add",
        expected_definition_file="Calculator.fs",
    ).to_pytest_param(
        pytest.mark.xfail(reason="F# language server cannot reliably resolve defining symbols"),
        id="fsharp_add_in_program",
    ),
]

FIND_DEFINING_SYMBOL_REGEX_CASES = [
    RegexDefiningSymbolCase(
        language=Language.PYTHON,
        relative_path=os.path.join("test_repo", "services.py"),
        regex=r"from \.models import Item, (User)",
        containing_symbol_name_path="",
        expected_name="User",
        expected_definition_file="models.py",
    ).to_pytest_param(id="python_import_user"),
    RegexDefiningSymbolCase(
        language=Language.PYTHON,
        relative_path=os.path.join("test_repo", "services.py"),
        regex=r"=\s+(User)\(",
        containing_symbol_name_path="UserService/create_user",
        expected_name="User",
        expected_definition_file="models.py",
    ).to_pytest_param(id="python_create_user_call"),
    RegexDefiningSymbolCase(
        language=Language.PYTHON_TY,
        relative_path=os.path.join("test_repo", "services.py"),
        regex=r"=\s+(User)\(",
        containing_symbol_name_path="UserService/create_user",
        expected_name="User",
        expected_definition_file="models.py",
    ).to_pytest_param(id="python_ty_create_user_call"),
    RegexDefiningSymbolCase(
        language=Language.GO,
        relative_path="main.go",
        regex=r"var greeter (Greeter) =",
        containing_symbol_name_path="main",
        expected_name="Greeter",
        expected_definition_file="main.go",
    ).to_pytest_param(id="go_greeter_var"),
]

_FIND_IMPLEMENTATION_CASE_DEFINITIONS = [
    FindImplementationCase(
        language=Language.CSHARP,
        symbol_name="IGreeter/FormatGreeting",
        definition_file=os.path.join("Services", "IGreeter.cs"),
        implementation_file=os.path.join("Services", "ConsoleGreeter.cs"),
        expected_symbol_name="FormatGreeting",
    ),
    FindImplementationCase(
        language=Language.GO,
        symbol_name="Greeter/FormatGreeting",
        definition_file="main.go",
        implementation_file="main.go",
        expected_symbol_name="(ConsoleGreeter).FormatGreeting",
    ),
    FindImplementationCase(
        language=Language.JAVA,
        symbol_name="Greeter/formatGreeting",
        definition_file=os.path.join("src", "main", "java", "test_repo", "Greeter.java"),
        implementation_file=os.path.join("src", "main", "java", "test_repo", "ConsoleGreeter.java"),
        expected_symbol_name="formatGreeting",
    ),
    FindImplementationCase(
        language=Language.RUST,
        symbol_name="Greeter/format_greeting",
        definition_file=os.path.join("src", "lib.rs"),
        implementation_file=os.path.join("src", "lib.rs"),
        expected_symbol_name="format_greeting",
    ),
    FindImplementationCase(
        language=Language.TYPESCRIPT,
        symbol_name="Greeter/formatGreeting",
        definition_file="formatters.ts",
        implementation_file="formatters.ts",
        expected_symbol_name="formatGreeting",
    ),
]
FIND_IMPLEMENTATION_CASES = [
    case.to_pytest_param(
        id={
            Language.CSHARP: "csharp_greeter_format",
            Language.GO: "go_greeter_format",
            Language.JAVA: "java_greeter_format",
            Language.RUST: "rust_greeter_format",
            Language.TYPESCRIPT: "typescript_greeter_format",
        }[case.language]
    )
    for case in _FIND_IMPLEMENTATION_CASE_DEFINITIONS
    if language_has_verified_implementation_support(case.language)
]

FIND_SYMBOL_STABLE_CASES = [
    FindSymbolCase(language=Language.PYTHON, symbol_name="User", expected_kind="Class", expected_file="models.py").to_pytest_param(
        id="python_user_class"
    ),
    FindSymbolCase(language=Language.GO, symbol_name="Helper", expected_kind="Function", expected_file="main.go").to_pytest_param(
        id="go_helper_function"
    ),
    FindSymbolCase(language=Language.JAVA, symbol_name="Model", expected_kind="Class", expected_file="Model.java").to_pytest_param(
        id="java_model_class"
    ),
    FindSymbolCase(language=Language.KOTLIN, symbol_name="Model", expected_kind="Struct", expected_file="Model.kt").to_pytest_param(
        id="kotlin_model_struct"
    ),
    FindSymbolCase(
        language=Language.TYPESCRIPT,
        symbol_name="DemoClass",
        expected_kind="Class",
        expected_file="index.ts",
    ).to_pytest_param(id="typescript_demo_class"),
    FindSymbolCase(
        language=Language.PHP,
        symbol_name="helperFunction",
        expected_kind="Function",
        expected_file="helper.php",
    ).to_pytest_param(id="php_helper_function"),
    FindSymbolCase(
        language=Language.CLOJURE,
        symbol_name="greet",
        expected_kind="Function",
        expected_file=clj.CORE_PATH,
    ).to_pytest_param(id="clojure_greet_function"),
    FindSymbolCase(
        language=Language.CSHARP,
        symbol_name="Calculator",
        expected_kind="Class",
        expected_file="Program.cs",
    ).to_pytest_param(id="csharp_calculator_class"),
    FindSymbolCase(
        language=Language.POWERSHELL,
        symbol_name="function Greet-User ()",
        expected_kind="Function",
        expected_file="main.ps1",
    ).to_pytest_param(id="powershell_greet_user"),
    FindSymbolCase(language=Language.CPP_CCLS, symbol_name="add", expected_kind="Function", expected_file="b.cpp").to_pytest_param(
        id="cpp_add_function"
    ),
    FindSymbolCase(language=Language.LEAN4, symbol_name="add", expected_kind="Method", expected_file="Helper.lean").to_pytest_param(
        id="lean_add_method"
    ),
]
FIND_SYMBOL_FSHARP_CASES = [
    FindSymbolCase(
        language=Language.FSHARP,
        symbol_name="Calculator",
        expected_kind="Module",
        expected_file="Calculator.fs",
    ).to_pytest_param(id="fsharp_calculator_module"),
]
FIND_SYMBOL_RUST_CASES = [
    FindSymbolCase(language=Language.RUST, symbol_name="add", expected_kind="Function", expected_file="lib.rs").to_pytest_param(
        id="rust_add_function"
    ),
]

FIND_REFERENCE_STABLE_CASES = [
    FindReferenceCase(
        language=Language.PYTHON,
        symbol_name="User",
        definition_file=os.path.join("test_repo", "models.py"),
        reference_file=os.path.join("test_repo", "services.py"),
    ).to_pytest_param(id="python_user_refs"),
    FindReferenceCase(language=Language.GO, symbol_name="Helper", definition_file="main.go", reference_file="main.go").to_pytest_param(
        id="go_helper_refs"
    ),
    FindReferenceCase(
        language=Language.JAVA,
        symbol_name="Model",
        definition_file=os.path.join("src", "main", "java", "test_repo", "Model.java"),
        reference_file=os.path.join("src", "main", "java", "test_repo", "Main.java"),
    ).to_pytest_param(id="java_model_refs"),
    FindReferenceCase(
        language=Language.KOTLIN,
        symbol_name="Model",
        definition_file=os.path.join("src", "main", "kotlin", "test_repo", "Model.kt"),
        reference_file=os.path.join("src", "main", "kotlin", "test_repo", "Main.kt"),
    ).to_pytest_param(id="kotlin_model_refs"),
    FindReferenceCase(
        language=Language.RUST,
        symbol_name="add",
        definition_file=os.path.join("src", "lib.rs"),
        reference_file=os.path.join("src", "main.rs"),
    ).to_pytest_param(id="rust_add_refs"),
    FindReferenceCase(
        language=Language.PHP,
        symbol_name="helperFunction",
        definition_file="helper.php",
        reference_file="index.php",
    ).to_pytest_param(id="php_helper_refs"),
    FindReferenceCase(
        language=Language.CLOJURE,
        symbol_name="multiply",
        definition_file=clj.CORE_PATH,
        reference_file=clj.UTILS_PATH,
    ).to_pytest_param(id="clojure_multiply_refs"),
    FindReferenceCase(
        language=Language.CSHARP,
        symbol_name="Calculator",
        definition_file="Program.cs",
        reference_file="Program.cs",
    ).to_pytest_param(id="csharp_calculator_refs"),
    FindReferenceCase(
        language=Language.POWERSHELL,
        symbol_name="function Greet-User ()",
        definition_file="main.ps1",
        reference_file="main.ps1",
    ).to_pytest_param(id="powershell_greet_user_refs"),
    FindReferenceCase(language=Language.CPP_CCLS, symbol_name="add", definition_file="b.cpp", reference_file="a.cpp").to_pytest_param(
        id="cpp_add_refs"
    ),
    FindReferenceCase(
        language=Language.LEAN4, symbol_name="add", definition_file="Helper.lean", reference_file="Main.lean"
    ).to_pytest_param(id="lean_add_refs"),
]
FIND_REFERENCE_TYPESCRIPT_CASES = [
    FindReferenceCase(
        language=Language.TYPESCRIPT,
        symbol_name="helperFunction",
        definition_file="index.ts",
        reference_file="use_helper.ts",
    ).to_pytest_param(id="typescript_helper_refs"),
]
FIND_REFERENCE_FSHARP_CASES = [
    FindReferenceCase(
        language=Language.FSHARP, symbol_name="add", definition_file="Calculator.fs", reference_file="Program.fs"
    ).to_pytest_param(id="fsharp_add_refs"),
]

FIND_DEFINING_SYMBOL_REGEX_ERROR_CASES = [
    RegexDefiningSymbolErrorCase(
        language=Language.PYTHON,
        relative_path=os.path.join("test_repo", "services.py"),
        regex=r"(User)",
        containing_symbol_name_path="",
        error_fragment="Expected exactly one regex match",
    ).to_pytest_param(id="python_regex_multiple_matches"),
    RegexDefiningSymbolErrorCase(
        language=Language.PYTHON,
        relative_path=os.path.join("test_repo", "services.py"),
        regex=r"User",
        containing_symbol_name_path="UserService/create_user",
        error_fragment="must contain exactly one capturing group",
    ).to_pytest_param(id="python_regex_missing_group"),
]

FIND_SYMBOL_NAME_PATH_CASES = [
    FindSymbolNamePathCase(
        language=Language.PYTHON,
        name_path="OuterClass/NestedClass",
        substring_matching=False,
        expected_symbol_name="NestedClass",
        expected_kind="Class",
        expected_file=os.path.join("test_repo", "nested.py"),
    ).to_pytest_param(id="nested_class_exact"),
    FindSymbolNamePathCase(
        language=Language.PYTHON,
        name_path="OuterClass/NestedClass/find_me",
        substring_matching=False,
        expected_symbol_name="find_me",
        expected_kind="Method",
        expected_file=os.path.join("test_repo", "nested.py"),
    ).to_pytest_param(id="nested_method_exact"),
    FindSymbolNamePathCase(
        language=Language.PYTHON,
        name_path="OuterClass/NestedCl",
        substring_matching=True,
        expected_symbol_name="NestedClass",
        expected_kind="Class",
        expected_file=os.path.join("test_repo", "nested.py"),
    ).to_pytest_param(id="nested_class_substring"),
    FindSymbolNamePathCase(
        language=Language.PYTHON,
        name_path="OuterClass/NestedClass/find_m",
        substring_matching=True,
        expected_symbol_name="find_me",
        expected_kind="Method",
        expected_file=os.path.join("test_repo", "nested.py"),
    ).to_pytest_param(id="nested_method_substring"),
    FindSymbolNamePathCase(
        language=Language.PYTHON,
        name_path="/OuterClass",
        substring_matching=False,
        expected_symbol_name="OuterClass",
        expected_kind="Class",
        expected_file=os.path.join("test_repo", "nested.py"),
    ).to_pytest_param(id="outer_class_absolute"),
    FindSymbolNamePathCase(
        language=Language.PYTHON,
        name_path="/OuterClass/NestedClass/find_m",
        substring_matching=True,
        expected_symbol_name="find_me",
        expected_kind="Method",
        expected_file=os.path.join("test_repo", "nested.py"),
    ).to_pytest_param(id="nested_method_absolute_substring"),
]

FIND_SYMBOL_NAME_PATH_NO_MATCH_CASES = [
    FindSymbolNoMatchCase(language=Language.PYTHON, name_path="/NestedClass").to_pytest_param(id="nested_class_not_top_level"),
    FindSymbolNoMatchCase(language=Language.PYTHON, name_path="/NoSuchParent/NestedClass").to_pytest_param(
        id="nested_class_missing_parent"
    ),
]

FIND_SYMBOL_OVERLOADED_FUNCTION_CASES = [
    FindSymbolOverloadedCase(language=Language.JAVA, name_path="Model/getName", num_expected=2).to_pytest_param(
        id="java_overloaded_get_name"
    ),
]

NON_UNIQUE_SYMBOL_REFERENCE_ERROR_CASES = [
    NonUniqueSymbolReferenceCase(
        language=Language.JAVA,
        name_path="Model/getName",
        relative_path=os.path.join("src", "main", "java", "test_repo", "Model.java"),
    ).to_pytest_param(id="java_overloaded_get_name"),
]

SAFE_DELETE_BLOCKED_CASES = [
    SafeDeleteCase(
        language=Language.PYTHON,
        name_path="User",
        relative_path=os.path.join("test_repo", "models.py"),
    ).to_pytest_param(id="python_user"),
    SafeDeleteCase(
        language=Language.JAVA,
        name_path="Model",
        relative_path=os.path.join("src", "main", "java", "test_repo", "Model.java"),
    ).to_pytest_param(id="java_model"),
    SafeDeleteCase(
        language=Language.KOTLIN,
        name_path="Model",
        relative_path=os.path.join("src", "main", "kotlin", "test_repo", "Model.kt"),
    ).to_pytest_param(
        *([pytest.mark.skip(reason="Kotlin LSP JVM crashes on restart in CI")] if is_ci else []),
        id="kotlin_model",
    ),
    SafeDeleteCase(
        language=Language.TYPESCRIPT,
        name_path="helperFunction",
        relative_path="index.ts",
    ).to_pytest_param(id="typescript_helper_function"),
]

SAFE_DELETE_SUCCEEDS_CASES = [
    SafeDeleteCase(
        language=Language.PYTHON,
        name_path="Timer",
        relative_path=os.path.join("test_repo", "utils.py"),
    ).to_pytest_param(id="python_timer"),
    SafeDeleteCase(
        language=Language.JAVA,
        name_path="ModelUser",
        relative_path=os.path.join("src", "main", "java", "test_repo", "ModelUser.java"),
    ).to_pytest_param(id="java_model_user"),
    SafeDeleteCase(
        language=Language.KOTLIN,
        name_path="ModelUser",
        relative_path=os.path.join("src", "main", "kotlin", "test_repo", "ModelUser.kt"),
    ).to_pytest_param(
        *([pytest.mark.skip(reason="Kotlin LSP JVM crashes on restart in CI")] if is_ci else []),
        id="kotlin_model_user",
    ),
    SafeDeleteCase(
        language=Language.TYPESCRIPT,
        name_path="unusedStandaloneFunction",
        relative_path="index.ts",
    ).to_pytest_param(id="typescript_unused_standalone_function"),
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
    @pytest.mark.parametrize(
        "project",
        [None, str(get_repo_path(Language.PYTHON)), "non_existent_path"],
        ids=["no_project", "python_project_path", "invalid_project_path"],
    )
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

    def _symbol_matches_expected_name(self, symbol: dict, expected_name: str) -> bool:
        return symbol.get("name") == expected_name or symbol.get("name_path") == expected_name or expected_name in symbol.get("info", "")

    def _assert_symbol_info_present(
        self,
        serena_agent: SerenaAgent,
        symbol: dict,
        expected_name: str | None = None,
    ) -> None:
        if serena_agent.get_active_lsp_languages() == [Language.KOTLIN]:
            # kotlin LS doesn't seem to provide hover info right now, at least for the struct we test this on
            return

        if symbol["kind"] in (SymbolKind.File.name, SymbolKind.Module.name):
            # we ignore file and module symbols for the info test
            return

        symbol_info = symbol.get("info")
        assert symbol_info, f"Expected symbol info to be present for symbol: {symbol}"

        if expected_name is not None:
            assert expected_name in symbol_info, (
                f"[{serena_agent.get_active_lsp_languages()[0]}] Expected symbol info to contain symbol name "
                f"{expected_name}. Info: {symbol_info}"
            )

        # special additional test for Java, since Eclipse returns hover in a complex format and we want to make sure to get it right
        if symbol["kind"] == SymbolKind.Class.name and serena_agent.get_active_lsp_languages() == [Language.JAVA]:
            assert "A simple model class" in symbol_info, f"Java class docstring not found in symbol info: {symbol}"

    def _assert_find_symbol(self, serena_agent: SerenaAgent, case: FindSymbolCase) -> None:
        agent = serena_agent
        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply(name_path_pattern=case.symbol_name, include_info=True)

        symbols = json.loads(result)
        assert any(
            case.symbol_name in s["name_path"]
            and case.expected_kind.lower() in s["kind"].lower()
            and case.expected_file in s["relative_path"]
            for s in symbols
        ), f"Expected to find {case.symbol_name} ({case.expected_kind}) in {case.expected_file}"

        for symbol in symbols:
            self._assert_symbol_info_present(serena_agent, symbol, case.symbol_name)

    @pytest.mark.parametrize(
        "serena_agent",
        [pytest.param(Language.PHP, marks=get_pytest_markers(Language.PHP), id="php_sample_file")],
        indirect=True,
    )
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

    @pytest.mark.parametrize("serena_agent,case", FIND_SYMBOL_STABLE_CASES, indirect=["serena_agent"])
    def test_find_symbol_stable(self, serena_agent: SerenaAgent, case: FindSymbolCase) -> None:
        self._assert_find_symbol(serena_agent, case)

    @pytest.mark.parametrize("serena_agent,case", FIND_SYMBOL_FSHARP_CASES, indirect=["serena_agent"])
    @pytest.mark.xfail(reason="F# language server is unreliable")  # See issue #1040
    def test_find_symbol_fsharp(self, serena_agent: SerenaAgent, case: FindSymbolCase) -> None:
        self._assert_find_symbol(serena_agent, case)

    @pytest.mark.parametrize("serena_agent,case", FIND_SYMBOL_RUST_CASES, indirect=["serena_agent"])
    @pytest.mark.xfail(reason="Rust language server is unreliable")  # See issue #1040
    def test_find_symbol_rust(self, serena_agent: SerenaAgent, case: FindSymbolCase) -> None:
        self._assert_find_symbol(serena_agent, case)

    def _assert_find_symbol_references(self, serena_agent: SerenaAgent, case: FindReferenceCase) -> None:
        agent = serena_agent

        # Find the symbol location first
        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply(name_path_pattern=case.symbol_name, relative_path=case.definition_file)

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
        assert contains_ref_with_relative_path(refs, case.reference_file), (
            f"Expected to find reference to {case.symbol_name} in {case.reference_file}. refs={refs}"
        )

    def _assert_find_symbol_implementations(self, serena_agent: SerenaAgent, case: FindImplementationCase) -> None:
        agent = serena_agent

        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply(name_path_pattern=case.symbol_name, relative_path=case.definition_file)
        symbols = json.loads(result)
        assert symbols, f"Expected to find symbol {case.symbol_name} in {case.definition_file}"

        def_symbol = symbols[0]
        find_impl_tool = agent.get_tool(FindImplementationsTool)
        result = find_impl_tool.apply(name_path=def_symbol["name_path"], relative_path=def_symbol["relative_path"], include_info=True)
        implementations = json.loads(result)

        assert any(
            case.implementation_file in implementation["relative_path"]
            and self._symbol_matches_expected_name(implementation, case.expected_symbol_name)
            for implementation in implementations
        ), f"Expected to find implementation of {case.symbol_name} in {case.implementation_file}. implementations={implementations}"

        for implementation in implementations:
            self._assert_symbol_info_present(serena_agent, implementation)

    def _assert_find_defining_symbol(self, serena_agent: SerenaAgent, case: FindDefiningSymbolCase) -> None:
        project_root = get_repo_path(case.language)
        position = find_identifier_occurrence_position(
            project_root / case.relative_path,
            case.identifier,
            case.occurrence_index,
            case.column_offset,
        )
        assert position is not None, f"Could not find occurrence {case.occurrence_index} of {case.identifier!r} in {case.relative_path}"

        find_defining_symbol_tool = serena_agent.get_tool(FindDefiningSymbolAtLocationTool)
        result = find_defining_symbol_tool.apply(
            relative_path=case.relative_path,
            line=position[0],
            column=position[1],
            include_info=True,
        )
        defining_symbol = json.loads(result)

        assert defining_symbol is not None, f"Expected defining symbol for {case.identifier!r} in {case.relative_path}"
        assert defining_symbol.get("relative_path") is not None
        assert case.expected_definition_file in defining_symbol["relative_path"], (
            f"Expected defining symbol in {case.expected_definition_file!r}, got: {defining_symbol}"
        )
        assert self._symbol_matches_expected_name(defining_symbol, case.expected_name), (
            f"Expected defining symbol name {case.expected_name!r}, got: {defining_symbol}"
        )

        self._assert_symbol_info_present(serena_agent, defining_symbol)

    def _assert_find_defining_symbol_by_regex(self, serena_agent: SerenaAgent, case: RegexDefiningSymbolCase) -> None:
        find_defining_symbol_tool = serena_agent.get_tool(FindDefiningSymbolTool)
        result = find_defining_symbol_tool.apply(
            regex=case.regex,
            relative_path=case.relative_path,
            containing_symbol_name_path=case.containing_symbol_name_path,
            include_info=True,
        )
        defining_symbol = json.loads(result)

        assert defining_symbol is not None, f"Expected defining symbol for regex {case.regex!r} in {case.relative_path}"
        assert defining_symbol.get("relative_path") is not None
        assert case.expected_definition_file in defining_symbol["relative_path"], (
            f"Expected defining symbol in {case.expected_definition_file!r}, got: {defining_symbol}"
        )
        assert self._symbol_matches_expected_name(defining_symbol, case.expected_name), (
            f"Expected defining symbol name {case.expected_name!r}, got: {defining_symbol}"
        )

        self._assert_symbol_info_present(serena_agent, defining_symbol)

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

    @pytest.mark.parametrize("serena_agent,case", FIND_REFERENCE_STABLE_CASES, indirect=["serena_agent"])
    def test_find_symbol_references_stable(self, serena_agent: SerenaAgent, case: FindReferenceCase) -> None:
        self._assert_find_symbol_references(serena_agent, case)

    @pytest.mark.parametrize("serena_agent,case", FIND_REFERENCE_TYPESCRIPT_CASES, indirect=["serena_agent"])
    @pytest.mark.xfail(False, reason="TypeScript language server is unreliable")  # NOTE: Testing; may be resolved by #1120; See issue #1040
    def test_find_symbol_references_typescript(self, serena_agent: SerenaAgent, case: FindReferenceCase) -> None:
        self._assert_find_symbol_references(serena_agent, case)

    @pytest.mark.parametrize("serena_agent,case", FIND_REFERENCE_FSHARP_CASES, indirect=["serena_agent"])
    @pytest.mark.xfail(reason="F# language server is unreliable")  # See issue #1040
    def test_find_symbol_references_fsharp(self, serena_agent: SerenaAgent, case: FindReferenceCase) -> None:
        self._assert_find_symbol_references(serena_agent, case)

    @pytest.mark.parametrize("serena_agent,case", FIND_DEFINING_SYMBOL_CASES, indirect=["serena_agent"])
    def test_find_defining_symbol(self, serena_agent: SerenaAgent, case: FindDefiningSymbolCase) -> None:
        self._assert_find_defining_symbol(serena_agent, case)

    @pytest.mark.parametrize("serena_agent,case", FIND_DEFINING_SYMBOL_REGEX_CASES, indirect=["serena_agent"])
    def test_find_defining_symbol_by_regex(self, serena_agent: SerenaAgent, case: RegexDefiningSymbolCase) -> None:
        self._assert_find_defining_symbol_by_regex(serena_agent, case)

    @pytest.mark.parametrize("serena_agent,case", FIND_DEFINING_SYMBOL_REGEX_ERROR_CASES, indirect=["serena_agent"])
    def test_find_defining_symbol_by_regex_error(
        self,
        serena_agent: SerenaAgent,
        case: RegexDefiningSymbolErrorCase,
    ) -> None:
        find_defining_symbol_tool = serena_agent.get_tool(FindDefiningSymbolTool)
        result = find_defining_symbol_tool.apply(
            regex=case.regex,
            relative_path=case.relative_path,
            containing_symbol_name_path=case.containing_symbol_name_path,
        )
        assert result.startswith("Error: "), result
        assert case.error_fragment in result, result

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

    if FIND_IMPLEMENTATION_CASES:

        @pytest.mark.parametrize("serena_agent,case", FIND_IMPLEMENTATION_CASES, indirect=["serena_agent"])
        def test_find_symbol_implementations(self, serena_agent: SerenaAgent, case: FindImplementationCase) -> None:
            self._assert_find_symbol_implementations(serena_agent, case)

    @pytest.mark.parametrize("serena_agent,case", FIND_SYMBOL_NAME_PATH_CASES, indirect=["serena_agent"])
    def test_find_symbol_name_path(self, serena_agent: SerenaAgent, case: FindSymbolNamePathCase) -> None:
        agent = serena_agent

        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply_ex(
            name_path_pattern=case.name_path,
            depth=0,
            relative_path=None,
            include_body=False,
            include_kinds=None,
            exclude_kinds=None,
            substring_matching=case.substring_matching,
        )

        symbols = json.loads(result)
        assert any(
            case.expected_symbol_name == s["name_path"].split("/")[-1]
            and case.expected_kind.lower() in s["kind"].lower()
            and case.expected_file in s["relative_path"]
            for s in symbols
        ), f"Expected to find {case.name_path} ({case.expected_kind}) in {case.expected_file}. Symbols: {symbols}"

    @pytest.mark.parametrize("serena_agent,case", FIND_SYMBOL_NAME_PATH_NO_MATCH_CASES, indirect=["serena_agent"])
    def test_find_symbol_name_path_no_match(self, serena_agent: SerenaAgent, case: FindSymbolNoMatchCase) -> None:
        agent = serena_agent

        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply_ex(
            name_path_pattern=case.name_path,
            depth=0,
            substring_matching=True,
        )

        symbols = json.loads(result)
        assert not symbols, f"Expected to find no symbols for {case.name_path}. Symbols found: {symbols}"

    @pytest.mark.parametrize("serena_agent,case", FIND_SYMBOL_OVERLOADED_FUNCTION_CASES, indirect=["serena_agent"])
    def test_find_symbol_overloaded_function(self, serena_agent: SerenaAgent, case: FindSymbolOverloadedCase) -> None:
        """
        Tests whether the FindSymbolTool can find all overloads of a function/method
        (provided that the overload id remains unspecified in the name path)
        """
        agent = serena_agent

        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply_ex(
            name_path_pattern=case.name_path,
            depth=0,
            substring_matching=False,
        )

        symbols = json.loads(result)
        assert len(symbols) == case.num_expected, (
            f"Expected to find {case.num_expected} symbols for overloaded function {case.name_path}. Symbols found: {symbols}"
        )

    @pytest.mark.parametrize("serena_agent,case", NON_UNIQUE_SYMBOL_REFERENCE_ERROR_CASES, indirect=["serena_agent"])
    def test_non_unique_symbol_reference_error(
        self,
        serena_agent: SerenaAgent,
        case: NonUniqueSymbolReferenceCase,
    ) -> None:
        """
        Tests whether the tools operating on a well-defined symbol raises an error when the symbol reference is non-unique.
        We exemplarily test a retrieval tool (FindReferencingSymbolsTool) and an editing tool (ReplaceSymbolBodyTool).
        """
        find_refs_tool = serena_agent.get_tool(FindReferencingSymbolsTool)
        with pytest.raises(ValueError, match=case.expected_error_fragment):
            find_refs_tool.apply(name_path=case.name_path, relative_path=case.relative_path)

        replace_symbol_body_tool = serena_agent.get_tool(ReplaceSymbolBodyTool)
        with pytest.raises(ValueError, match=case.expected_error_fragment):
            replace_symbol_body_tool.apply(name_path=case.name_path, relative_path=case.relative_path, body="")

    @pytest.mark.parametrize(
        "serena_agent",
        [
            pytest.param(Language.TYPESCRIPT, marks=get_pytest_markers(Language.TYPESCRIPT), id="typescript_unique_regex"),
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
            pytest.param(Language.TYPESCRIPT, marks=get_pytest_markers(Language.TYPESCRIPT), id="typescript_backslashes"),
        ],
        indirect=["serena_agent"],
    )
    @pytest.mark.parametrize("mode", ["literal", "regex"], ids=["literal_mode", "regex_mode"])
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
            pytest.param(Language.PYTHON, marks=get_pytest_markers(Language.PYTHON), id="python_services"),
            pytest.param(Language.PYTHON_TY, marks=get_pytest_markers(Language.PYTHON_TY), id="python_ty_services"),
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
            pytest.param(Language.PYTHON, marks=get_pytest_markers(Language.PYTHON), id="python_container_body"),
            pytest.param(Language.PYTHON_TY, marks=get_pytest_markers(Language.PYTHON_TY), id="python_ty_container_body"),
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
            pytest.param(Language.TYPESCRIPT, marks=get_pytest_markers(Language.TYPESCRIPT), id="typescript_ambiguous_regex"),
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

    @pytest.mark.parametrize("serena_agent,case", SAFE_DELETE_BLOCKED_CASES, indirect=["serena_agent"])
    def test_safe_delete_symbol_blocked_by_references(self, serena_agent: SerenaAgent, case: SafeDeleteCase):
        """
        Tests that SafeDeleteSymbol refuses to delete a symbol that is referenced elsewhere
        and returns a message listing the referencing files.
        """
        # wrap in modification context as a safety net: if the tool has a bug and deletes anyway,
        # the file will be restored, preventing corruption of test resources
        with project_file_modification_context(serena_agent, case.relative_path):
            safe_delete_tool = serena_agent.get_tool(SafeDeleteSymbol)
            result = safe_delete_tool.apply(name_path_pattern=case.name_path, relative_path=case.relative_path)
            assert "Cannot delete" in result, f"Expected deletion to be blocked due to existing references, but got: {result}"
            assert "referenced in" in result, f"Expected reference information in result, but got: {result}"

    @pytest.mark.parametrize("serena_agent,case", SAFE_DELETE_SUCCEEDS_CASES, indirect=["serena_agent"])
    def test_safe_delete_symbol_succeeds_when_no_references(self, serena_agent: SerenaAgent, case: SafeDeleteCase):
        """
        Tests that SafeDeleteSymbol successfully deletes a symbol that has no references
        and that the symbol is actually removed from the file.
        """
        with project_file_modification_context(serena_agent, case.relative_path):
            safe_delete_tool = serena_agent.get_tool(SafeDeleteSymbol)
            result = safe_delete_tool.apply(name_path_pattern=case.name_path, relative_path=case.relative_path)
            assert result == SUCCESS_RESULT, f"Expected successful deletion, but got: {result}"

            # verify the symbol was actually removed from the file
            file_content = read_project_file(serena_agent.get_active_project(), case.relative_path)
            assert case.name_path not in file_content, (
                f"Expected symbol {case.name_path} to be removed from {case.relative_path}, but it still appears in the file content"
            )
