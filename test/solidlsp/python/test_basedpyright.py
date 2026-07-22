from collections.abc import Iterator
from pathlib import Path
from textwrap import dedent

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.conftest import start_ls_context
from test.solidlsp.conftest import document_symbol_names

pytestmark = pytest.mark.python


@pytest.fixture(scope="module")
def basedpyright_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    project_root = tmp_path_factory.mktemp("basedpyright-project")
    files = {
        "pyproject.toml": """
            [tool.basedpyright]
            typeCheckingMode = "basic"
            reportExplicitAny = "error"
        """,
        "models.py": """
            class Greeter:
                def greet(self, name: str) -> str:
                    return f"Hello, {name}"
        """,
        "service.py": """
            from models import Greeter


            def build_message(name: str) -> str:
                greeter = Greeter()
                return greeter.greet(name)
        """,
        "consumer.py": """
            from service import build_message


            MESSAGE = build_message("Ada")
        """,
        "diagnostics.py": """
            from typing import Any


            def echo(value: Any) -> Any:
                return value
        """,
    }
    for relative_path, content in files.items():
        (project_root / relative_path).write_text(dedent(content).lstrip(), encoding="utf-8")
    return project_root


@pytest.fixture(scope="module")
def basedpyright_language_server(basedpyright_project: Path) -> Iterator[SolidLanguageServer]:
    with start_ls_context(
        ls_id=LanguageServerId.PYTHON_BASEDPYRIGHT,
        repo_path=str(basedpyright_project),
    ) as language_server:
        yield language_server


def test_basedpyright_starts(
    basedpyright_language_server: SolidLanguageServer,
    basedpyright_project: Path,
) -> None:
    assert basedpyright_language_server.ls_id == LanguageServerId.PYTHON_BASEDPYRIGHT
    assert basedpyright_language_server.is_running()
    assert Path(basedpyright_language_server.language_server.repository_root_path).resolve() == basedpyright_project.resolve()


def test_basedpyright_document_symbols(basedpyright_language_server: SolidLanguageServer) -> None:
    assert "build_message" in document_symbol_names(basedpyright_language_server, "service.py")


def test_basedpyright_definitions_and_references(basedpyright_language_server: SolidLanguageServer) -> None:
    defining_symbol = basedpyright_language_server.request_defining_symbol("service.py", 4, 15)
    assert defining_symbol is not None
    assert defining_symbol["name"] == "Greeter"
    assert defining_symbol["location"]["relativePath"] == "models.py"

    symbols = basedpyright_language_server.request_document_symbols("models.py").get_all_symbols_and_roots()
    greeter_symbol = next(symbol for symbol in symbols[0] if symbol.get("name") == "Greeter")
    selection_start = greeter_symbol["selectionRange"]["start"]
    references = basedpyright_language_server.request_references(
        "models.py",
        selection_start["line"],
        selection_start["character"],
    )
    assert any(reference["uri"].endswith("/service.py") for reference in references), references


def test_basedpyright_specific_diagnostics(basedpyright_language_server: SolidLanguageServer) -> None:
    diagnostics = basedpyright_language_server.request_text_document_diagnostics("diagnostics.py", min_severity=1)
    messages = [diagnostic["message"] for diagnostic in diagnostics]
    assert any("Any" in message for message in messages), messages
