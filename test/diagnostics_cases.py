import os
from dataclasses import dataclass
from typing import cast

import pytest
from _pytest.mark import Mark, MarkDecorator

from solidlsp.ls_config import Language
from test.conftest import get_pytest_markers


@dataclass(frozen=True)
class DiagnosticCase:
    language: Language
    relative_path: str
    primary_symbol_name_path: str
    primary_symbol_identifier: str
    reference_symbol_name_path: str
    reference_symbol_identifier: str
    primary_message_fragment: str
    reference_message_fragment: str


def diagnostic_case_param(
    case: DiagnosticCase,
    *marks: MarkDecorator | Mark,
    id: str,
):
    return pytest.param(case.language, case, marks=[*get_pytest_markers(case.language), *marks], id=id)


DIAGNOSTIC_CASE_PARAMS = [
    diagnostic_case_param(
        DiagnosticCase(
            language=Language.PYTHON,
            relative_path=os.path.join("test_repo", "diagnostics_sample.py"),
            primary_symbol_name_path="broken_factory",
            primary_symbol_identifier="broken_factory",
            reference_symbol_name_path="broken_consumer",
            reference_symbol_identifier="broken_consumer",
            primary_message_fragment="missing_user",
            reference_message_fragment="undefined_name",
        ),
        id="python_missing_user",
    ),
    diagnostic_case_param(
        DiagnosticCase(
            language=Language.PYTHON_TY,
            relative_path=os.path.join("test_repo", "diagnostics_sample.py"),
            primary_symbol_name_path="broken_factory",
            primary_symbol_identifier="broken_factory",
            reference_symbol_name_path="broken_consumer",
            reference_symbol_identifier="broken_consumer",
            primary_message_fragment="missing_user",
            reference_message_fragment="undefined_name",
        ),
        id="python_ty_missing_user",
    ),
    diagnostic_case_param(
        DiagnosticCase(
            language=Language.GO,
            relative_path="diagnostics_sample.go",
            primary_symbol_name_path="brokenFactory",
            primary_symbol_identifier="brokenFactory",
            reference_symbol_name_path="brokenConsumer",
            reference_symbol_identifier="brokenConsumer",
            primary_message_fragment="missingGreeting",
            reference_message_fragment="missingConsumerValue",
        ),
        id="go_missing_greeting",
    ),
    diagnostic_case_param(
        DiagnosticCase(
            language=Language.JAVA,
            relative_path=os.path.join("src", "main", "java", "test_repo", "DiagnosticsSample.java"),
            primary_symbol_name_path="DiagnosticsSample/brokenFactory",
            primary_symbol_identifier="brokenFactory",
            reference_symbol_name_path="DiagnosticsSample/brokenConsumer",
            reference_symbol_identifier="brokenConsumer",
            primary_message_fragment="missingGreeting",
            reference_message_fragment="missingConsumerValue",
        ),
        id="java_missing_greeting",
    ),
    diagnostic_case_param(
        DiagnosticCase(
            language=Language.KOTLIN,
            relative_path=os.path.join("src", "main", "kotlin", "test_repo", "DiagnosticsSample.kt"),
            primary_symbol_name_path="brokenFactory",
            primary_symbol_identifier="brokenFactory",
            reference_symbol_name_path="brokenConsumer",
            reference_symbol_identifier="brokenConsumer",
            primary_message_fragment="missingGreeting",
            reference_message_fragment="missingConsumerValue",
        ),
        id="kotlin_missing_greeting",
    ),
    diagnostic_case_param(
        DiagnosticCase(
            language=Language.RUST,
            relative_path=os.path.join("src", "diagnostics_sample.rs"),
            primary_symbol_name_path="broken_factory",
            primary_symbol_identifier="broken_factory",
            reference_symbol_name_path="broken_consumer",
            reference_symbol_identifier="broken_consumer",
            primary_message_fragment="missing_greeting",
            reference_message_fragment="missing_consumer_value",
        ),
        pytest.mark.xfail(reason="rust-analyzer does not surface diagnostics for this fixture through Serena currently"),
        id="rust_missing_greeting",
    ),
    diagnostic_case_param(
        DiagnosticCase(
            language=Language.PHP,
            relative_path="diagnostics_sample.php",
            primary_symbol_name_path="brokenFactory",
            primary_symbol_identifier="brokenFactory",
            reference_symbol_name_path="brokenConsumer",
            reference_symbol_identifier="brokenConsumer",
            primary_message_fragment="missingGreeting",
            reference_message_fragment="missingConsumerValue",
        ),
        pytest.mark.xfail(reason="PHP LS integration does not expose document diagnostics in this environment"),
        id="php_missing_greeting",
    ),
    diagnostic_case_param(
        DiagnosticCase(
            language=Language.CLOJURE,
            relative_path=os.path.join("src", "test_app", "diagnostics_sample.clj"),
            primary_symbol_name_path="broken-factory",
            primary_symbol_identifier="broken-factory",
            reference_symbol_name_path="broken-consumer",
            reference_symbol_identifier="broken-consumer",
            primary_message_fragment="missing-greeting",
            reference_message_fragment="missing-consumer-value",
        ),
        id="clojure_missing_greeting",
    ),
    diagnostic_case_param(
        DiagnosticCase(
            language=Language.CSHARP,
            relative_path="DiagnosticsSample.cs",
            primary_symbol_name_path="TestProject/DiagnosticsSample/BrokenFactory",
            primary_symbol_identifier="BrokenFactory",
            reference_symbol_name_path="TestProject/DiagnosticsSample/BrokenConsumer",
            reference_symbol_identifier="BrokenConsumer",
            primary_message_fragment="missingGreeting",
            reference_message_fragment="missingConsumerValue",
        ),
        id="csharp_missing_greeting",
    ),
    diagnostic_case_param(
        DiagnosticCase(
            language=Language.POWERSHELL,
            relative_path="diagnostics_sample.ps1",
            primary_symbol_name_path="function Invoke-BrokenFactory ()",
            primary_symbol_identifier="Invoke-BrokenFactory",
            reference_symbol_name_path="function Invoke-BrokenConsumer ()",
            reference_symbol_identifier="Invoke-BrokenConsumer",
            primary_message_fragment="MissingGreeting",
            reference_message_fragment="MissingConsumerValue",
        ),
        pytest.mark.xfail(reason="PowerShell LS does not surface document diagnostics in this environment"),
        id="powershell_missing_greeting",
    ),
    diagnostic_case_param(
        DiagnosticCase(
            language=Language.CPP_CCLS,
            relative_path="diagnostics_sample.cpp",
            primary_symbol_name_path="brokenFactory",
            primary_symbol_identifier="brokenFactory",
            reference_symbol_name_path="brokenConsumer",
            reference_symbol_identifier="brokenConsumer",
            primary_message_fragment="missingGreeting",
            reference_message_fragment="missingConsumerValue",
        ),
        pytest.mark.xfail(reason="ccls does not expose document diagnostics through this integration"),
        id="cpp_missing_greeting",
    ),
    diagnostic_case_param(
        DiagnosticCase(
            language=Language.LEAN4,
            relative_path="DiagnosticsSample.lean",
            primary_symbol_name_path="brokenFactory",
            primary_symbol_identifier="brokenFactory",
            reference_symbol_name_path="brokenConsumer",
            reference_symbol_identifier="brokenConsumer",
            primary_message_fragment="missingGreeting",
            reference_message_fragment="missingConsumerValue",
        ),
        pytest.mark.xfail(reason="Lean4 LS does not reliably surface diagnostics in CI"),
        id="lean_missing_greeting",
    ),
    diagnostic_case_param(
        DiagnosticCase(
            language=Language.TYPESCRIPT,
            relative_path="diagnostics_sample.ts",
            primary_symbol_name_path="brokenFactory",
            primary_symbol_identifier="brokenFactory",
            reference_symbol_name_path="brokenConsumer",
            reference_symbol_identifier="brokenConsumer",
            primary_message_fragment="missingGreeting",
            reference_message_fragment="missingConsumerValue",
        ),
        pytest.mark.typescript,
        pytest.mark.xfail(reason="TypeScript LS does not surface document diagnostics through this integration"),
        id="typescript_missing_greeting",
    ),
    diagnostic_case_param(
        DiagnosticCase(
            language=Language.FSHARP,
            relative_path="DiagnosticsSample.fs",
            primary_symbol_name_path="brokenFactory",
            primary_symbol_identifier="brokenFactory",
            reference_symbol_name_path="brokenConsumer",
            reference_symbol_identifier="brokenConsumer",
            primary_message_fragment="missingGreeting",
            reference_message_fragment="missingConsumerValue",
        ),
        pytest.mark.xfail(reason="F# LS does not expose document diagnostics through this integration"),
        id="fsharp_missing_greeting",
    ),
]

WORKING_DIAGNOSTIC_TOOL_CASE_PARAMS = [
    case_param
    for case_param in DIAGNOSTIC_CASE_PARAMS
    if cast(DiagnosticCase, case_param.values[1]).language
    in {Language.PYTHON, Language.PYTHON_TY, Language.GO, Language.JAVA, Language.KOTLIN, Language.CSHARP}
]
