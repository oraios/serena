import json
import logging
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from copy import copy
from dataclasses import dataclass
from typing import Literal, cast

import pytest
from _pytest.mark import Mark, MarkDecorator, ParameterSet

from serena.agent import SerenaAgent
from serena.config.serena_config import ProjectConfig, RegisteredProject, SerenaConfig
from serena.project import Project
from serena.tools import (
    SUCCESS_RESULT,
    ActivateProjectTool,
    EditingToolWithDiagnostics,
    FindDeclarationTool,
    FindImplementationsTool,
    FindReferencingSymbolsTool,
    FindSymbolTool,
    GetDiagnosticsForFileTool,
    InitialInstructionsTool,
    ReplaceContentTool,
    ReplaceSymbolBodyTool,
    SafeDeleteSymbol,
    Tool,
)
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind
from test.conftest import (
    find_identifier_pos,
    get_pytest_markers,
    get_repo_path,
    is_ci,
    language_tests_enabled,
)


@dataclass
class BaseCase:
    language: Language
    id: str

    def to_pytest_param(self, *marks: MarkDecorator | Mark) -> ParameterSet:
        return pytest.param(self.language, self, marks=[*get_pytest_markers(self.language), *marks], id=self.id)  # type: ignore


@dataclass
class FindSymbolCase(BaseCase):
    symbol_name: str
    expected_kind: str
    expected_file: str


@dataclass
class FindReferenceCase(BaseCase):
    symbol_name: str
    definition_file: str
    reference_file: str


@dataclass
class FindDefiningSymbolCase(BaseCase):
    relative_path: str
    identifier: str
    occurrence_index: int
    column_offset: int
    expected_name: str
    expected_definition_file: str


@dataclass
class RegexDefiningSymbolCase(BaseCase):
    relative_path: str
    regex: str
    containing_symbol_name_path: str
    expected_name: str
    expected_definition_file: str


@dataclass
class RegexDefiningSymbolErrorCase(BaseCase):
    relative_path: str
    regex: str
    containing_symbol_name_path: str
    error_fragment: str


@dataclass
class FindImplementationCase(BaseCase):
    symbol_name: str
    definition_file: str
    implementation_file: str
    expected_symbol_name: str


@dataclass
class FindSymbolNamePathCase(BaseCase):
    name_path: str
    substring_matching: bool
    expected_symbol_name: str
    expected_kind: str
    expected_file: str


@dataclass
class FindSymbolNoMatchCase(BaseCase):
    name_path: str


@dataclass
class FindSymbolOverloadedCase(BaseCase):
    name_path: str
    num_expected: int


@dataclass
class NonUniqueSymbolReferenceCase(BaseCase):
    name_path: str
    relative_path: str
    expected_error_fragment: str = "multiple"


@dataclass
class SafeDeleteCase(BaseCase):
    name_path: str
    relative_path: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "relative_path", self.relative_path.replace("\\", "/"))


@dataclass
class DiagnosticCase(BaseCase):
    language: Language
    relative_path: str
    name_path1: str
    name_path2: str | None
    message_fragment1: str
    message_fragment2: str | None

    @property
    def symbol1_id_str(self) -> str:
        return self.name_path1.split("/")[-1]

    @property
    def symbol2_id_str(self) -> str | None:
        if self.name_path2 is None:
            return None
        return self.name_path2.split("/")[-1]

    def without_second_symbol(self) -> "DiagnosticCase":
        result = copy(self)
        result.name_path2 = None
        result.message_fragment2 = None
        return result

    def assert_matches(self, tool_output: dict) -> None:
        """

        :param tool_output: Output of diagnostics tool, representing the mapping `relative_path -> severity -> name_path -> diagnostics_results`.
        :return:
        """
        assert self.relative_path in tool_output, (
            f"Missing diagnostics for relative path {self.relative_path} in tool output keys: {list(tool_output.keys())}"
        )
        severity_group = tool_output[self.relative_path]
        assert "Error" in severity_group, severity_group
        name_path_group = severity_group["Error"]

        for expected_name_path in [self.name_path1, self.name_path2]:
            if expected_name_path is not None:
                assert expected_name_path in name_path_group, name_path_group

        diagnostic_messages = [
            diagnostic["message"] for diagnostics_for_name_path in name_path_group.values() for diagnostic in diagnostics_for_name_path
        ]
        for expected_fragment in [self.message_fragment1, self.message_fragment2]:
            if expected_fragment is not None:
                assert any(expected_fragment in message for message in diagnostic_messages), diagnostic_messages


DIAGNOSTIC_CASES = [
    DiagnosticCase(
        language=Language.PYTHON,
        id=f"{Language.PYTHON.value}_missing_user",
        relative_path=os.path.join("test_repo", "diagnostics_sample.py"),
        name_path1="broken_factory",
        name_path2="broken_consumer",
        message_fragment1="missing_user",
        message_fragment2="undefined_name",
    ).to_pytest_param(),
    DiagnosticCase(
        language=Language.CLOJURE,
        id=f"{Language.CLOJURE.value}_missing-greeting",
        relative_path=os.path.join("src", "test_app", "diagnostics_sample.clj"),
        name_path1="broken-factory",
        name_path2="broken-consumer",
        message_fragment1="missing-greeting",
        message_fragment2="missing-consumer-value",
    ).to_pytest_param(),
    DiagnosticCase(
        language=Language.GO,
        id=f"{Language.GO.value}_missingGreeting",
        relative_path="diagnostics_sample.go",
        name_path1="brokenFactory",
        name_path2="brokenConsumer",
        message_fragment1="missingGreeting",
        message_fragment2="missingConsumerValue",
    ).to_pytest_param(),
    DiagnosticCase(
        language=Language.TYPESCRIPT,
        id=f"{Language.TYPESCRIPT.value}_missingGreeting",
        relative_path="diagnostics_sample.ts",
        name_path1="brokenFactory",
        name_path2="brokenConsumer",
        message_fragment1="missingGreeting",
        message_fragment2="missingConsumerValue",
    ).to_pytest_param(),
]


FIND_DEFINING_SYMBOL_CASES = [
    FindDefiningSymbolCase(
        language=Language.PYTHON,
        id="python_user_in_services",
        relative_path=os.path.join("test_repo", "services.py"),
        identifier="User",
        occurrence_index=1,
        column_offset=1,
        expected_name="User",
        expected_definition_file="models.py",
    ).to_pytest_param(),
    FindDefiningSymbolCase(
        language=Language.PYTHON_TY,
        id="python_ty_user_in_services",
        relative_path=os.path.join("test_repo", "services.py"),
        identifier="User",
        occurrence_index=1,
        column_offset=1,
        expected_name="User",
        expected_definition_file="models.py",
    ).to_pytest_param(),
    FindDefiningSymbolCase(
        language=Language.GO,
        id="go_helper_in_main",
        relative_path="main.go",
        identifier="Helper",
        occurrence_index=0,
        column_offset=1,
        expected_name="Helper",
        expected_definition_file="main.go",
    ).to_pytest_param(),
    FindDefiningSymbolCase(
        language=Language.JAVA,
        id="java_model_in_main",
        relative_path=os.path.join("src", "main", "java", "test_repo", "Main.java"),
        identifier="Model",
        occurrence_index=0,
        column_offset=1,
        expected_name="Model",
        expected_definition_file="Model.java",
    ).to_pytest_param(),
    FindDefiningSymbolCase(
        language=Language.KOTLIN,
        id="kotlin_model_in_main",
        relative_path=os.path.join("src", "main", "kotlin", "test_repo", "Main.kt"),
        identifier="Model",
        occurrence_index=0,
        column_offset=1,
        expected_name="Model",
        expected_definition_file="Model.kt",
    ).to_pytest_param(),
    FindDefiningSymbolCase(
        language=Language.RUST,
        id="rust_format_greeting",
        relative_path=os.path.join("src", "main.rs"),
        identifier="format_greeting",
        occurrence_index=0,
        column_offset=1,
        expected_name="format_greeting",
        expected_definition_file="lib.rs",
    ).to_pytest_param(),
    FindDefiningSymbolCase(
        language=Language.PHP,
        id="php_helper_function",
        relative_path="index.php",
        identifier="helperFunction",
        occurrence_index=0,
        column_offset=5,
        expected_name="helperFunction",
        expected_definition_file="helper.php",
    ).to_pytest_param(),
    FindDefiningSymbolCase(
        language=Language.CLOJURE,
        id="clojure_multiply_in_utils",
        relative_path=os.path.join("src", "test_app", "utils.clj"),
        identifier="multiply",
        occurrence_index=0,
        column_offset=1,
        expected_name="multiply",
        expected_definition_file=os.path.join("src", "test_app", "core.clj"),
    ).to_pytest_param(),
    FindDefiningSymbolCase(
        language=Language.CSHARP,
        id="csharp_add_in_program",
        relative_path="Program.cs",
        identifier="Add",
        occurrence_index=0,
        column_offset=1,
        expected_name="Add",
        expected_definition_file="Program.cs",
    ).to_pytest_param(),
    FindDefiningSymbolCase(
        language=Language.POWERSHELL,
        id="powershell_convert_to_uppercase",
        relative_path="main.ps1",
        identifier="Convert-ToUpperCase",
        occurrence_index=0,
        column_offset=1,
        expected_name="function Convert-ToUpperCase ()",
        expected_definition_file="utils.ps1",
    ).to_pytest_param(),
    FindDefiningSymbolCase(
        language=Language.CPP,
        id="cpp_add_in_a",
        relative_path="a.cpp",
        identifier="add",
        occurrence_index=0,
        column_offset=1,
        expected_name="add",
        expected_definition_file="b.cpp",
    ).to_pytest_param(),
    FindDefiningSymbolCase(
        language=Language.LEAN4,
        id="lean_add_in_main",
        relative_path="Main.lean",
        identifier="add",
        occurrence_index=1,
        column_offset=1,
        expected_name="add",
        expected_definition_file="Helper.lean",
    ).to_pytest_param(),
    FindDefiningSymbolCase(
        language=Language.TYPESCRIPT,
        id="typescript_helper_function",
        relative_path="index.ts",
        identifier="helperFunction",
        occurrence_index=1,
        column_offset=1,
        expected_name="helperFunction",
        expected_definition_file="index.ts",
    ).to_pytest_param(),
    FindDefiningSymbolCase(
        language=Language.FSHARP,
        id="fsharp_add_in_program",
        relative_path="Program.fs",
        identifier="add",
        occurrence_index=0,
        column_offset=1,
        expected_name="add",
        expected_definition_file="Calculator.fs",
    ).to_pytest_param(
        pytest.mark.xfail(reason="F# language server cannot reliably resolve defining symbols"),
    ),
]

FIND_DEFINING_SYMBOL_REGEX_CASES = [
    RegexDefiningSymbolCase(
        language=Language.PYTHON,
        id="python_import_user",
        relative_path=os.path.join("test_repo", "services.py"),
        regex=r"from \.models import Item, (User)",
        containing_symbol_name_path="",
        expected_name="User",
        expected_definition_file="models.py",
    ).to_pytest_param(),
    RegexDefiningSymbolCase(
        language=Language.PYTHON,
        id="python_create_user_call",
        relative_path=os.path.join("test_repo", "services.py"),
        regex=r"=\s+(User)\(",
        containing_symbol_name_path="UserService/create_user",
        expected_name="User",
        expected_definition_file="models.py",
    ).to_pytest_param(),
    RegexDefiningSymbolCase(
        language=Language.PYTHON_TY,
        id="python_ty_create_user_call",
        relative_path=os.path.join("test_repo", "services.py"),
        regex=r"=\s+(User)\(",
        containing_symbol_name_path="UserService/create_user",
        expected_name="User",
        expected_definition_file="models.py",
    ).to_pytest_param(),
    RegexDefiningSymbolCase(
        language=Language.GO,
        id="go_greeter_var",
        relative_path="main.go",
        regex=r"var greeter (Greeter) =",
        containing_symbol_name_path="main",
        expected_name="Greeter",
        expected_definition_file="main.go",
    ).to_pytest_param(),
]

FIND_IMPLEMENTATION_CASES = [
    FindImplementationCase(
        language=Language.CSHARP,
        id="csharp_greeter_format",
        symbol_name="IGreeter/FormatGreeting",
        definition_file=os.path.join("Services", "IGreeter.cs"),
        implementation_file=os.path.join("Services", "ConsoleGreeter.cs"),
        expected_symbol_name="FormatGreeting",
    ).to_pytest_param(),
    FindImplementationCase(
        language=Language.GO,
        id="go_greeter_format",
        symbol_name="Greeter/FormatGreeting",
        definition_file="main.go",
        implementation_file="main.go",
        expected_symbol_name="FormatGreeting",
    ).to_pytest_param(),
    FindImplementationCase(
        language=Language.JAVA,
        id="java_greeter_format",
        symbol_name="Greeter/formatGreeting",
        definition_file=os.path.join("src", "main", "java", "test_repo", "Greeter.java"),
        implementation_file=os.path.join("src", "main", "java", "test_repo", "ConsoleGreeter.java"),
        expected_symbol_name="formatGreeting",
    ).to_pytest_param(),
    FindImplementationCase(
        language=Language.RUST,
        id="rust_greeter_format",
        symbol_name="Greeter/format_greeting",
        definition_file=os.path.join("src", "lib.rs"),
        implementation_file=os.path.join("src", "lib.rs"),
        expected_symbol_name="format_greeting",
    ).to_pytest_param(),
    FindImplementationCase(
        language=Language.TYPESCRIPT,
        id="typescript_greeter_format",
        symbol_name="Greeter/formatGreeting",
        definition_file="formatters.ts",
        implementation_file="formatters.ts",
        expected_symbol_name="formatGreeting",
    ).to_pytest_param(),
]


FIND_SYMBOL_REFERENCES_CASES = [
    FindSymbolCase(
        language=Language.PYTHON, id="python_user_class", symbol_name="User", expected_kind="Class", expected_file="models.py"
    ).to_pytest_param(),
    FindSymbolCase(
        language=Language.GO, id="go_helper_function", symbol_name="Helper", expected_kind="Function", expected_file="main.go"
    ).to_pytest_param(),
    FindSymbolCase(
        language=Language.JAVA, id="java_model_class", symbol_name="Model", expected_kind="Class", expected_file="Model.java"
    ).to_pytest_param(),
    FindSymbolCase(
        language=Language.KOTLIN, id="kotlin_model_struct", symbol_name="Model", expected_kind="Struct", expected_file="Model.kt"
    ).to_pytest_param(),
    FindSymbolCase(
        language=Language.TYPESCRIPT,
        id="typescript_demo_class",
        symbol_name="DemoClass",
        expected_kind="Class",
        expected_file="index.ts",
    ).to_pytest_param(),
    FindSymbolCase(
        language=Language.PHP,
        id="php_helper_function",
        symbol_name="helperFunction",
        expected_kind="Function",
        expected_file="helper.php",
    ).to_pytest_param(),
    FindSymbolCase(
        language=Language.CLOJURE,
        id="clojure_greet_function",
        symbol_name="greet",
        expected_kind="Function",
        expected_file=os.path.join("src", "test_app", "core.clj"),
    ).to_pytest_param(),
    FindSymbolCase(
        language=Language.CSHARP,
        id="csharp_calculator_class",
        symbol_name="Calculator",
        expected_kind="Class",
        expected_file="Program.cs",
    ).to_pytest_param(),
    FindSymbolCase(
        language=Language.POWERSHELL,
        id="powershell_greet_user",
        symbol_name="Greet-User",
        expected_kind="Function",
        expected_file="main.ps1",
    ).to_pytest_param(),
    FindSymbolCase(
        language=Language.CPP, id="cpp_add_function", symbol_name="add", expected_kind="Function", expected_file="b.cpp"
    ).to_pytest_param(),
    FindSymbolCase(
        language=Language.LEAN4, id="lean_add_method", symbol_name="add", expected_kind="Method", expected_file="Helper.lean"
    ).to_pytest_param(),
    FindSymbolCase(
        language=Language.FSHARP,
        id="fsharp_calculator_module",
        symbol_name="Calculator",
        expected_kind="Module",
        expected_file="Calculator.fs",
    ).to_pytest_param(pytest.mark.xfail(reason="F# language server is unreliable")),
    FindSymbolCase(
        language=Language.RUST, id="rust_add_function", symbol_name="add", expected_kind="Function", expected_file="lib.rs"
    ).to_pytest_param(),
]

FIND_REFERENCE_CASES = [
    FindReferenceCase(
        language=Language.PYTHON,
        id="python_user_refs",
        symbol_name="User",
        definition_file=os.path.join("test_repo", "models.py"),
        reference_file=os.path.join("test_repo", "services.py"),
    ).to_pytest_param(),
    FindReferenceCase(
        language=Language.GO, id="go_helper_refs", symbol_name="Helper", definition_file="main.go", reference_file="main.go"
    ).to_pytest_param(),
    FindReferenceCase(
        language=Language.JAVA,
        id="java_model_refs",
        symbol_name="Model",
        definition_file=os.path.join("src", "main", "java", "test_repo", "Model.java"),
        reference_file=os.path.join("src", "main", "java", "test_repo", "Main.java"),
    ).to_pytest_param(),
    FindReferenceCase(
        language=Language.KOTLIN,
        id="kotlin_model_refs",
        symbol_name="Model",
        definition_file=os.path.join("src", "main", "kotlin", "test_repo", "Model.kt"),
        reference_file=os.path.join("src", "main", "kotlin", "test_repo", "Main.kt"),
    ).to_pytest_param(),
    FindReferenceCase(
        language=Language.RUST,
        id="rust_add_refs",
        symbol_name="add",
        definition_file=os.path.join("src", "lib.rs"),
        reference_file=os.path.join("src", "main.rs"),
    ).to_pytest_param(),
    FindReferenceCase(
        language=Language.PHP,
        id="php_helper_refs",
        symbol_name="helperFunction",
        definition_file="helper.php",
        reference_file="index.php",
    ).to_pytest_param(),
    FindReferenceCase(
        language=Language.CLOJURE,
        id="clojure_multiply_refs",
        symbol_name="multiply",
        definition_file=os.path.join("src", "test_app", "core.clj"),
        reference_file=os.path.join("src", "test_app", "utils.clj"),
    ).to_pytest_param(),
    FindReferenceCase(
        language=Language.CSHARP,
        id="csharp_calculator_refs",
        symbol_name="Calculator",
        definition_file="Program.cs",
        reference_file="Program.cs",
    ).to_pytest_param(),
    FindReferenceCase(
        language=Language.POWERSHELL,
        id="powershell_greet_user_refs",
        symbol_name="Greet-User",
        definition_file="main.ps1",
        reference_file="main.ps1",
    ).to_pytest_param(),
    FindReferenceCase(
        language=Language.CPP, id="cpp_add_refs", symbol_name="add", definition_file="b.cpp", reference_file="a.cpp"
    ).to_pytest_param(),
    FindReferenceCase(
        language=Language.LEAN4, id="lean_add_refs", symbol_name="add", definition_file="Helper.lean", reference_file="Main.lean"
    ).to_pytest_param(),
    FindReferenceCase(
        language=Language.TYPESCRIPT,
        id="typescript_helper_refs",
        symbol_name="helperFunction",
        definition_file="index.ts",
        reference_file="use_helper.ts",
    ).to_pytest_param(pytest.mark.xfail(False, reason="TypeScript language server is unreliable")),
    FindReferenceCase(
        language=Language.FSHARP, id="fsharp_add_refs", symbol_name="add", definition_file="Calculator.fs", reference_file="Program.fs"
    ).to_pytest_param(
        pytest.mark.xfail(reason="F# language server is unreliable"),  # See issue #1040
    ),
]

FIND_DEFINING_SYMBOL_REGEX_ERROR_CASES = [
    RegexDefiningSymbolErrorCase(
        language=Language.PYTHON,
        id="python_regex_multiple_matches",
        relative_path=os.path.join("test_repo", "services.py"),
        regex=r"(User)",
        containing_symbol_name_path="",
        error_fragment="Match must be unique",
    ).to_pytest_param(),
    RegexDefiningSymbolErrorCase(
        language=Language.PYTHON,
        id="python_regex_missing_group",
        relative_path=os.path.join("test_repo", "services.py"),
        regex=r"self.users.get\(id\)",
        containing_symbol_name_path="UserService/get_user",
        error_fragment="Regex must contain exactly one group",
    ).to_pytest_param(),
]

FIND_SYMBOL_NAME_PATH_CASES = [
    FindSymbolNamePathCase(
        language=Language.PYTHON,
        id="nested_class_exact",
        name_path="OuterClass/NestedClass",
        substring_matching=False,
        expected_symbol_name="NestedClass",
        expected_kind="Class",
        expected_file=os.path.join("test_repo", "nested.py"),
    ).to_pytest_param(),
    FindSymbolNamePathCase(
        language=Language.PYTHON,
        id="nested_method_exact",
        name_path="OuterClass/NestedClass/find_me",
        substring_matching=False,
        expected_symbol_name="find_me",
        expected_kind="Method",
        expected_file=os.path.join("test_repo", "nested.py"),
    ).to_pytest_param(),
    FindSymbolNamePathCase(
        language=Language.PYTHON,
        id="nested_class_substring",
        name_path="OuterClass/NestedCl",
        substring_matching=True,
        expected_symbol_name="NestedClass",
        expected_kind="Class",
        expected_file=os.path.join("test_repo", "nested.py"),
    ).to_pytest_param(),
    FindSymbolNamePathCase(
        language=Language.PYTHON,
        id="nested_method_substring",
        name_path="OuterClass/NestedClass/find_m",
        substring_matching=True,
        expected_symbol_name="find_me",
        expected_kind="Method",
        expected_file=os.path.join("test_repo", "nested.py"),
    ).to_pytest_param(),
    FindSymbolNamePathCase(
        language=Language.PYTHON,
        id="outer_class_absolute",
        name_path="/OuterClass",
        substring_matching=False,
        expected_symbol_name="OuterClass",
        expected_kind="Class",
        expected_file=os.path.join("test_repo", "nested.py"),
    ).to_pytest_param(),
    FindSymbolNamePathCase(
        language=Language.PYTHON,
        id="nested_method_absolute_substring",
        name_path="/OuterClass/NestedClass/find_m",
        substring_matching=True,
        expected_symbol_name="find_me",
        expected_kind="Method",
        expected_file=os.path.join("test_repo", "nested.py"),
    ).to_pytest_param(),
]

FIND_SYMBOL_NAME_PATH_NO_MATCH_CASES = [
    FindSymbolNoMatchCase(language=Language.PYTHON, id="nested_class_not_top_level", name_path="/NestedClass").to_pytest_param(),
    FindSymbolNoMatchCase(
        language=Language.PYTHON, id="nested_class_missing_parent", name_path="/NoSuchParent/NestedClass"
    ).to_pytest_param(),
]

FIND_SYMBOL_OVERLOADED_FUNCTION_CASES = [
    FindSymbolOverloadedCase(
        language=Language.JAVA, id="java_overloaded_get_name", name_path="Model/getName", num_expected=2
    ).to_pytest_param(),
]

NON_UNIQUE_SYMBOL_REFERENCE_ERROR_CASES = [
    NonUniqueSymbolReferenceCase(
        language=Language.JAVA,
        id="java_overloaded_get_name",
        name_path="Model/getName",
        relative_path=os.path.join("src", "main", "java", "test_repo", "Model.java"),
    ).to_pytest_param(),
]

SAFE_DELETE_BLOCKED_CASES = [
    SafeDeleteCase(
        language=Language.PYTHON,
        id="python_user",
        name_path="User",
        relative_path=os.path.join("test_repo", "models.py"),
    ).to_pytest_param(),
    SafeDeleteCase(
        language=Language.JAVA,
        id="java_model",
        name_path="Model",
        relative_path=os.path.join("src", "main", "java", "test_repo", "Model.java"),
    ).to_pytest_param(),
    SafeDeleteCase(
        language=Language.KOTLIN,
        id="kotlin_model",
        name_path="Model",
        relative_path=os.path.join("src", "main", "kotlin", "test_repo", "Model.kt"),
    ).to_pytest_param(
        *([pytest.mark.skip(reason="Kotlin LSP JVM crashes on restart in CI")] if is_ci else []),
    ),
    SafeDeleteCase(
        language=Language.TYPESCRIPT,
        id="typescript_helper_function",
        name_path="helperFunction",
        relative_path="index.ts",
    ).to_pytest_param(),
]

SAFE_DELETE_SUCCEEDS_CASES = [
    SafeDeleteCase(
        language=Language.PYTHON,
        id="python_timer",
        name_path="Timer",
        relative_path=os.path.join("test_repo", "utils.py"),
    ).to_pytest_param(),
    SafeDeleteCase(
        language=Language.JAVA,
        id="java_model_user",
        name_path="ModelUser",
        relative_path=os.path.join("src", "main", "java", "test_repo", "ModelUser.java"),
    ).to_pytest_param(),
    SafeDeleteCase(
        language=Language.KOTLIN,
        id="kotlin_model_user",
        name_path="ModelUser",
        relative_path=os.path.join("src", "main", "kotlin", "test_repo", "ModelUser.kt"),
    ).to_pytest_param(
        *([pytest.mark.skip(reason="Kotlin LSP JVM crashes on restart in CI")] if is_ci else []),
    ),
    SafeDeleteCase(
        language=Language.TYPESCRIPT,
        id="typescript_unused_standalone_function",
        name_path="unusedStandaloneFunction",
        relative_path="index.ts",
    ).to_pytest_param(),
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
        Language.CPP,
        Language.HAXE,
        Language.LEAN4,
        Language.MSL,
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
    assert EditingToolWithDiagnostics.DIAGNOSTICS_KEY in result
    d = json.loads(result)
    return d[EditingToolWithDiagnostics.DIAGNOSTICS_KEY]


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
    agent.on_shutdown(timeout=5)


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
        return (
            symbol.get("name") == expected_name
            or symbol.get("name_path", "").split("/")[-1] == expected_name
            or expected_name in symbol.get("info", "")
        )

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

    @pytest.mark.parametrize("serena_agent,case", FIND_SYMBOL_REFERENCES_CASES, indirect=["serena_agent"])
    def test_find_symbol(self, serena_agent: SerenaAgent, case: FindSymbolCase) -> None:
        agent = serena_agent
        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply(name_path_pattern=case.symbol_name, include_info=True)
        symbols = json.loads(result)
        assert any(
            case.symbol_name in s["name_path"]
            and case.expected_kind.lower() in s["kind"].lower()
            and case.expected_file in s["relative_path"]
            for s in symbols
        ), (
            f"Expected to find {case.symbol_name} ({case.expected_kind}) in {case.expected_file}. Found name paths: {[s['name_path'] for s in symbols]}"
        )
        for symbol in symbols:
            self._assert_symbol_info_present(serena_agent, symbol, case.symbol_name)

    @pytest.mark.parametrize("serena_agent,case", FIND_REFERENCE_CASES, indirect=["serena_agent"])
    def test_find_symbol_references(self, serena_agent: SerenaAgent, case: FindReferenceCase) -> None:
        # Find the symbol location first
        find_symbol_tool = serena_agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply(name_path_pattern=case.symbol_name, relative_path=case.definition_file)

        time.sleep(1)
        symbols = json.loads(result)
        # Find the definition
        def_symbol = symbols[0]

        # Now find references
        find_refs_tool = serena_agent.get_tool(FindReferencingSymbolsTool)
        result = find_refs_tool.apply(name_path=def_symbol["name_path"], relative_path=def_symbol["relative_path"])

        def contains_ref_with_relative_path(refs, relative_path):
            """
            Checks for reference to relative path, regardless of output format (grouped or ungrouped)
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

    @pytest.mark.parametrize("serena_agent,case", FIND_DEFINING_SYMBOL_REGEX_CASES, indirect=["serena_agent"])
    def test_find_declaration(self, serena_agent: SerenaAgent, case: RegexDefiningSymbolCase) -> None:
        tool = serena_agent.get_tool(FindDeclarationTool)
        result = tool.apply(
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

    @pytest.mark.parametrize("serena_agent,case", FIND_DEFINING_SYMBOL_REGEX_ERROR_CASES, indirect=["serena_agent"])
    def test_find_declaration_error(
        self,
        serena_agent: SerenaAgent,
        case: RegexDefiningSymbolErrorCase,
    ) -> None:
        tool = serena_agent.get_tool(FindDeclarationTool)
        with pytest.raises(ValueError, match=case.error_fragment):
            tool.apply(
                regex=case.regex,
                relative_path=case.relative_path,
                containing_symbol_name_path=case.containing_symbol_name_path,
            )

    @pytest.mark.parametrize("serena_agent,diagnostic_case", DIAGNOSTIC_CASES, indirect=["serena_agent"])
    def test_get_diagnostics_for_file(self, serena_agent: SerenaAgent, diagnostic_case: DiagnosticCase) -> None:
        diagnostics_tool = serena_agent.get_tool(GetDiagnosticsForFileTool)
        result = diagnostics_tool.apply(
            relative_path=diagnostic_case.relative_path,
            min_severity=1,
        )
        full_file_diagnostics = json.loads(result)
        diagnostic_case.assert_matches(full_file_diagnostics)

        # testing diagnostics in range by removing second symbol
        project_root = get_repo_path(diagnostic_case.language)
        pos1 = find_identifier_pos(project_root / diagnostic_case.relative_path, diagnostic_case.symbol1_id_str)
        pos2 = find_identifier_pos(project_root / diagnostic_case.relative_path, cast(str, diagnostic_case.symbol2_id_str))
        assert pos1 is not None
        assert pos2 is not None
        result = diagnostics_tool.apply(
            relative_path=diagnostic_case.relative_path,
            min_severity=1,
            start_line=pos1[0],
            end_line=pos2[0] - 1,
        )
        diagnostics_in_range = json.loads(result)
        diagnostic_case.without_second_symbol().assert_matches(diagnostics_in_range)

    @pytest.mark.parametrize("serena_agent,case", FIND_IMPLEMENTATION_CASES, indirect=["serena_agent"])
    def test_find_symbol_implementations(self, serena_agent: SerenaAgent, case: FindImplementationCase) -> None:
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
                repl='catch(error) {console.log("Never mind"); }',
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
        try:
            replace_content_tool.ENABLE_DIAGNOSTICS = True

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
        finally:
            replace_content_tool.ENABLE_DIAGNOSTICS = False

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
        try:
            replace_symbol_body_tool.ENABLE_DIAGNOSTICS = True

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
        finally:
            replace_symbol_body_tool.ENABLE_DIAGNOSTICS = False

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
                repl='catch(error) {console.log("Never mind"); }',
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


class TestPromptProvision:
    class MockContext:
        def __init__(self, session_id: str):
            self.session = session_id

    @classmethod
    def _call_tool(cls, agent: SerenaAgent, tool_class: type[Tool], session_id: str = "global", **kwargs) -> str:
        result = agent.get_tool(tool_class).apply_ex(mcp_ctx=cls.MockContext(session_id), **kwargs)  # type: ignore
        return result

    @staticmethod
    def _assert_activation_message(result: str, project_name: str, present: bool) -> None:
        regex = r"^The project with name '" + project_name + r"'.*?is activated.$"
        match = re.search(regex, result, re.MULTILINE)
        if present:
            assert match is not None, f"Expected project activation message in result:\n{result}"
        else:
            assert match is None, f"Expected no project activation message in result:\n{result}"

    @pytest.mark.parametrize("serena_agent", [Language.PYTHON], indirect=True)
    def test_initial_instructions_provide_project_activation_message_once_per_session(self, serena_agent: SerenaAgent) -> None:
        """
        Tests that the project activation message is provided on the first call to InitialInstructionsTool for a session,
        but not on subsequent calls within the same session. #1372
        """
        project_name = "test_repo_python"
        session1 = "session1"
        session2 = "session2"

        result1 = self._call_tool(serena_agent, InitialInstructionsTool, session_id=session1)
        self._assert_activation_message(result1, project_name, present=True)

        result2 = self._call_tool(serena_agent, InitialInstructionsTool, session_id=session2)
        self._assert_activation_message(result2, project_name, present=True)

        result3 = self._call_tool(serena_agent, InitialInstructionsTool, session_id=session1)
        self._assert_activation_message(result3, project_name, present=False)

    @pytest.mark.parametrize("serena_agent", [Language.PYTHON], indirect=True)
    def test_dynamically_activated_mode_is_provided_once_per_session(self, serena_agent: SerenaAgent) -> None:
        """
        Tests that when a new project is activated within a session that has a different mode configuration (e.g. no-onboarding),
        the new mode's prompts are provided at project activation but not in subsequent initial instructions calls within the same
        session, while they are provided in the initial instructions of a new session.
        """
        project_name1 = "test_repo_python"
        project_name2 = "test_repo_java"
        session1 = "session1"
        session2 = "session2"

        # the initial instructions must contain the project activation message for the first project
        result1 = self._call_tool(serena_agent, InitialInstructionsTool, session_id=session1)
        self._assert_activation_message(result1, project_name1, present=True)

        # now activate another project which dynamically enables a new mode (no-onboarding)
        reg_project = serena_agent.serena_config.get_registered_project(project_name2)
        reg_project.project_config.default_modes = ["no-onboarding"]
        expected_new_mode_message = "The onboarding process is not applied."
        result2 = self._call_tool(serena_agent, ActivateProjectTool, project=project_name2, session_id=session1)

        # the new mode's prompt must be included in the activation message
        self._assert_activation_message(result2, project_name2, present=True)
        assert expected_new_mode_message in result2, (
            f"Expected new mode message '{expected_new_mode_message}' not found in result:\n{result2}"
        )

        # the mode prompt must not be included in subsequent calls to the initial instructions tool within the same session
        result3 = self._call_tool(serena_agent, InitialInstructionsTool, session_id=session1)
        assert expected_new_mode_message not in result3, (
            f"Expected new mode message '{expected_new_mode_message}' to not be included in subsequent calls, but it was found in result:\n{result3}"
        )

        # the mode prompt must be included in the initial instructions of a new session
        result4 = self._call_tool(serena_agent, InitialInstructionsTool, session_id=session2)
        assert expected_new_mode_message in result4, (
            f"Expected new mode message '{expected_new_mode_message}' to be included in new session, but it was not found in result:\n{result4}"
        )

        # the initial instructions for the new session must also include the activation message for the project
        self._assert_activation_message(result4, project_name2, present=True)

    @pytest.mark.parametrize("serena_agent", [Language.PYTHON], indirect=True)
    def test_activate_project_tool_always_returns_activation_message(self, serena_agent: SerenaAgent) -> None:
        project_name = "test_repo_python"
        session = "session1"

        result1 = self._call_tool(serena_agent, ActivateProjectTool, project=project_name, session_id=session)
        self._assert_activation_message(result1, project_name, present=True)

        result2 = self._call_tool(serena_agent, ActivateProjectTool, project=project_name, session_id=session)
        self._assert_activation_message(result2, project_name, present=True)
