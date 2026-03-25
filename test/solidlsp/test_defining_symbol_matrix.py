import os
import shutil
from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.conftest import find_identifier_occurrence_position, is_ci
from test.solidlsp import clojure as clj


@pytest.mark.parametrize(
    "language_server,relative_path,identifier,occurrence_index,column_offset,expected_name,expected_definition_file",
    [
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
                pytest.mark.xfail(reason="Lean4 LS does not reliably resolve cross-file defining symbols in CI"),
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
    ],
    indirect=["language_server"],
)
def test_request_defining_symbol_matrix(
    language_server: SolidLanguageServer,
    relative_path: str,
    identifier: str,
    occurrence_index: int,
    column_offset: int,
    expected_name: str,
    expected_definition_file: str,
) -> None:
    repo_root = Path(language_server.repository_root_path)
    position = find_identifier_occurrence_position(repo_root / relative_path, identifier, occurrence_index, column_offset)
    assert position is not None, f"Could not find occurrence {occurrence_index} of {identifier!r} in {relative_path}"

    defining_symbol = language_server.request_defining_symbol(relative_path, *position)
    assert defining_symbol is not None, f"Expected a defining symbol for {identifier!r} in {relative_path}"
    assert defining_symbol.get("name") == expected_name, f"Expected defining symbol name {expected_name!r}, got: {defining_symbol}"
    assert expected_definition_file in defining_symbol["location"].get("relativePath", ""), (
        f"Expected defining symbol in {expected_definition_file!r}, got: {defining_symbol}"
    )
