from collections.abc import Generator
from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.conftest import start_ls_context

# This mark will be applied to all tests in this module
pytestmark = pytest.mark.python


@pytest.fixture(scope="module")
def ls_with_ignored_dirs() -> Generator[SolidLanguageServer, None, None]:
    """Fixture to set up an LS for the python test repo with the 'scripts' directory ignored."""
    ignored_paths = ["scripts", "custom_test"]
    with start_ls_context(language=Language.PYTHON, ignored_paths=ignored_paths) as ls:
        yield ls


@pytest.mark.parametrize("ls_with_ignored_dirs", [Language.PYTHON], indirect=True)
def test_symbol_tree_ignores_dir(ls_with_ignored_dirs: SolidLanguageServer):
    """Tests that request_full_symbol_tree ignores the configured directory."""
    root = ls_with_ignored_dirs.request_full_symbol_tree()[0]
    root_children = root["children"]
    children_names = {child["name"] for child in root_children}
    assert children_names == {"test_repo", "examples"}


@pytest.mark.parametrize("ls_with_ignored_dirs", [Language.PYTHON], indirect=True)
def test_find_references_ignores_dir(ls_with_ignored_dirs: SolidLanguageServer):
    """Tests that find_references ignores the configured directory."""
    # Location of Item, which is referenced in scripts
    definition_file = "test_repo/models.py"
    definition_line = 56
    definition_col = 6

    references = ls_with_ignored_dirs.request_references(definition_file, definition_line, definition_col)

    # assert that scripts does not appear in the references
    assert not any("scripts" in ref["relativePath"] for ref in references)


@pytest.mark.parametrize("repo_path", [Language.PYTHON], indirect=True)
def test_refs_and_symbols_with_glob_patterns(repo_path: Path) -> None:
    """Tests that refs and symbols with glob patterns are ignored."""
    ignored_paths = ["*ipts", "custom_t*"]
    with start_ls_context(language=Language.PYTHON, repo_path=str(repo_path), ignored_paths=ignored_paths) as ls:
        # same as in the above tests
        root = ls.request_full_symbol_tree()[0]
        root_children = root["children"]
        children_names = {child["name"] for child in root_children}
        assert children_names == {"test_repo", "examples"}

        # test that the refs and symbols with glob patterns are ignored
        definition_file = "test_repo/models.py"
        definition_line = 56
        definition_col = 6

        references = ls.request_references(definition_file, definition_line, definition_col)
        assert not any("scripts" in ref["relativePath"] for ref in references)
