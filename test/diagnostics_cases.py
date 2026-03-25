import os
import shutil
from dataclasses import dataclass
from typing import cast

import pytest

from solidlsp.ls_config import Language
from test.conftest import is_ci
from test.solidlsp import clojure as clj


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


DIAGNOSTIC_CASE_PARAMS = [
    pytest.param(
        Language.PYTHON,
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
        marks=pytest.mark.python,
    ),
    pytest.param(
        Language.PYTHON_TY,
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
        marks=pytest.mark.python,
    ),
    pytest.param(
        Language.GO,
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
        marks=pytest.mark.go,
    ),
    pytest.param(
        Language.JAVA,
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
        marks=pytest.mark.java,
    ),
    pytest.param(
        Language.KOTLIN,
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
        marks=[pytest.mark.kotlin] + ([pytest.mark.skip(reason="Kotlin LSP JVM crashes on restart in CI")] if is_ci else []),
    ),
    pytest.param(
        Language.RUST,
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
        marks=[
            pytest.mark.rust,
            pytest.mark.xfail(reason="rust-analyzer does not surface diagnostics for this fixture through Serena currently"),
        ],
    ),
    pytest.param(
        Language.PHP,
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
        marks=[pytest.mark.php, pytest.mark.xfail(reason="PHP LS integration does not expose document diagnostics in this environment")],
    ),
    pytest.param(
        Language.CLOJURE,
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
        marks=[
            pytest.mark.clojure,
            pytest.mark.skipif(not clj.is_clojure_cli_available(), reason="clojure CLI is not installed"),
        ],
    ),
    pytest.param(
        Language.CSHARP,
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
        marks=pytest.mark.csharp,
    ),
    pytest.param(
        Language.POWERSHELL,
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
        marks=[pytest.mark.powershell, pytest.mark.xfail(reason="PowerShell LS does not surface document diagnostics in this environment")],
    ),
    pytest.param(
        Language.CPP_CCLS,
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
        marks=[pytest.mark.cpp, pytest.mark.xfail(reason="ccls does not expose document diagnostics through this integration")],
    ),
    pytest.param(
        Language.LEAN4,
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
        marks=[
            pytest.mark.lean4,
            pytest.mark.skipif(shutil.which("lean") is None, reason="Lean is not installed"),
        ],
    ),
    pytest.param(
        Language.TYPESCRIPT,
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
        marks=[
            pytest.mark.typescript,
            pytest.mark.xfail(reason="TypeScript LS does not surface document diagnostics through this integration"),
        ],
    ),
    pytest.param(
        Language.FSHARP,
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
        marks=[pytest.mark.fsharp, pytest.mark.xfail(reason="F# LS does not expose document diagnostics through this integration")],
    ),
]


WORKING_DIAGNOSTIC_TOOL_CASE_PARAMS = [
    case_param
    for case_param in DIAGNOSTIC_CASE_PARAMS
    if cast(DiagnosticCase, case_param.values[1]).language
    in {Language.PYTHON, Language.PYTHON_TY, Language.GO, Language.JAVA, Language.KOTLIN, Language.CSHARP}
]
