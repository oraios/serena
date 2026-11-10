"""
Tests for the bodies of Python symbols that are defined by assignment statements, which must cover the entire statement.
"""

import os
import sys

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.solidlsp.conftest import PYTHON_BACKEND_LANGUAGES, find_document_symbol

pytestmark = pytest.mark.python

SYMBOL_BODY_FILE = os.path.join("test_repo", "symbol_body.py")
TYPE_ALIAS_BODY_FILE = os.path.join("test_repo", "type_alias_body.py")

ASSIGNMENT_BODIES = {
    "TriageRationale": 'TriageRationale = Annotated[\n    str,\n    Field(\n        description=(\n            "Shown to the developer in the decision log."\n        )\n    ),\n]',
    "SINGLE_LINE_CONSTANT": "SINGLE_LINE_CONSTANT = 42",
    "CONTINUED_SUM": "CONTINUED_SUM = 1 + \\\n    2",
    "IMPLICIT_CONCATENATION": 'IMPLICIT_CONCATENATION = (\n    "first part, "\n    "second part"\n)',
    "TYPED_TABLE": 'TYPED_TABLE: dict[str, int] = {\n    "alpha": 1,\n    "beta": 2,\n}',
    "declared_only": "declared_only: int",
    "chained_first": 'chained_first = chained_second = "chained"',
    "chained_second": 'chained_first = chained_second = "chained"',
    "why_escalated": 'why_escalated: str = Field(\n        description=(\n            "One sentence shown to the developer."\n        )\n    )',
    "declared_field": "declared_field: int",
    "default_field": "default_field: list[str] = field(default_factory=list)",
    "plain_field": "plain_field: int = 0",
    "required_item": "required_item: int",
    "defaulted_item": 'defaulted_item: str = "default"',
}

UNPACKING_BODIES = {
    "unpacked_first": "unpacked_first, unpacked_second = divmod(7, 2)",
    "unpacked_second": "unpacked_first, unpacked_second = divmod(7, 2)",
}

# backends which report names bound by tuple unpacking and type alias statements as symbols (ty and Pyrefly do not)
BACKENDS_REPORTING_ALL_BOUND_NAMES = [LanguageServerId.PYTHON, LanguageServerId.PYTHON_BASEDPYRIGHT]


def _assert_body_and_identifier(language_server: SolidLanguageServer, relative_path: str, name: str, expected_body: str) -> None:
    symbol = find_document_symbol(language_server, relative_path, name)
    assert symbol["body"].get_text() == expected_body

    # the identifier location still points to the name itself
    selection_start = symbol["selectionRange"]["start"]
    with language_server.open_file(relative_path, open_in_ls=False) as file_buffer:
        identifier_line = file_buffer.split_lines()[selection_start["line"]]
    assert identifier_line[selection_start["character"] :].startswith(name)


@pytest.mark.parametrize("language_server", PYTHON_BACKEND_LANGUAGES, indirect=True)
@pytest.mark.parametrize("name", list(ASSIGNMENT_BODIES))
def test_assignment_body_covers_entire_statement(language_server: SolidLanguageServer, name: str) -> None:
    _assert_body_and_identifier(language_server, SYMBOL_BODY_FILE, name, ASSIGNMENT_BODIES[name])


@pytest.mark.parametrize("language_server", BACKENDS_REPORTING_ALL_BOUND_NAMES, indirect=True)
@pytest.mark.parametrize("name", list(UNPACKING_BODIES))
def test_unpacking_assignment_body_covers_entire_statement(language_server: SolidLanguageServer, name: str) -> None:
    _assert_body_and_identifier(language_server, SYMBOL_BODY_FILE, name, UNPACKING_BODIES[name])


@pytest.mark.skipif(sys.version_info < (3, 12), reason="type alias statements require Python 3.12+ to be parsed")
@pytest.mark.parametrize("language_server", BACKENDS_REPORTING_ALL_BOUND_NAMES, indirect=True)
def test_type_alias_body_covers_entire_statement(language_server: SolidLanguageServer) -> None:
    _assert_body_and_identifier(language_server, TYPE_ALIAS_BODY_FILE, "StringToInt", "type StringToInt = dict[\n    str,\n    int,\n]")


@pytest.mark.parametrize("language_server", PYTHON_BACKEND_LANGUAGES, indirect=True)
def test_function_body_is_unaffected_by_preceding_assignments(language_server: SolidLanguageServer) -> None:
    symbol = find_document_symbol(language_server, SYMBOL_BODY_FILE, "function_after_assignments")
    assert symbol["body"].get_text() == "def function_after_assignments() -> int:\n    return SINGLE_LINE_CONSTANT"
