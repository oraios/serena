"""
The type hierarchy over the language server backend: the subtypes and supertypes of a class, and
`find_implementing_symbols` falling back to the subtypes for a class the server reports no implementations for.

pyrefly answers `typeHierarchy/subtypes` and `/supertypes` with the whole chain (indirect descendants and ancestors
included, the LSP spec's "direct" notwithstanding), so the assertions are supersets. typescript-language-server (5.1.3)
does not implement `textDocument/prepareTypeHierarchy` at all; the request answers MethodNotFound, which the layer
reports as an empty hierarchy — the TypeScript case is covered by that contract, not by a fixture.
"""

import os

import pytest

from serena.symbol import LanguageServerSymbolRetriever
from solidlsp.ls_config import LanguageServerId
from test.conftest import get_pytest_markers, project_with_explicit_ls_context

PYTHON_MODELS = os.path.join("test_repo", "models.py")


def _names(symbols) -> set[str]:
    return {s.name for s in symbols}


@pytest.mark.parametrize(
    "ls_id",
    [pytest.param(LanguageServerId.PYTHON_PYREFLY, marks=get_pytest_markers(LanguageServerId.PYTHON_PYREFLY), id="python_pyrefly")],
)
class TestPythonTypeHierarchy:
    def test_subtypes_of_a_base_class(self, ls_id: LanguageServerId) -> None:
        with project_with_explicit_ls_context(ls_id) as project:
            retriever = LanguageServerSymbolRetriever(project)
            subtypes = retriever.find_subtype_symbols("BaseService", PYTHON_MODELS)
            assert {"DataService", "NetworkService"} <= _names(subtypes)
            assert "User" not in _names(subtypes), "an unrelated class is never a subtype"
            assert all(s.relative_path == PYTHON_MODELS for s in subtypes)

    def test_supertypes_of_a_multiply_inheriting_class(self, ls_id: LanguageServerId) -> None:
        with project_with_explicit_ls_context(ls_id) as project:
            retriever = LanguageServerSymbolRetriever(project)
            supertypes = retriever.find_supertype_symbols("DataSyncService", PYTHON_MODELS)
            assert {"DataService", "NetworkService"} <= _names(supertypes)
            assert "ABC" not in _names(supertypes), "a supertype outside the repository (typeshed) is skipped, never raised on"

    def test_find_implementations_of_a_class_falls_back_to_its_subtypes(self, ls_id: LanguageServerId) -> None:
        with project_with_explicit_ls_context(ls_id) as project:
            retriever = LanguageServerSymbolRetriever(project)
            implementations = retriever.find_implementing_symbols("BaseService", PYTHON_MODELS)
            assert {"DataService", "NetworkService"} <= _names(implementations)


@pytest.mark.parametrize(
    "ls_id",
    [pytest.param(LanguageServerId.TYPESCRIPT, marks=get_pytest_markers(LanguageServerId.TYPESCRIPT), id="typescript")],
)
class TestTypeScriptTypeHierarchy:
    def test_a_server_without_type_hierarchy_answers_empty_not_an_error(self, ls_id: LanguageServerId) -> None:
        with project_with_explicit_ls_context(ls_id) as project:
            retriever = LanguageServerSymbolRetriever(project)
            assert retriever.find_subtype_symbols("Greeter", "formatters.ts") == []
            assert retriever.find_supertype_symbols("ConsoleGreeter", "formatters.ts") == []
