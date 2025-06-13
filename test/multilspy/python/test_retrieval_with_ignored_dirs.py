from collections.abc import Generator
from pathlib import Path

import pytest

from multilspy.language_server import SyncLanguageServer
from multilspy.multilspy_config import Language
from test.conftest import create_ls

# This mark will be applied to all tests in this module
pytestmark = pytest.mark.python


@pytest.fixture(scope="module")
def ls_with_ignored_dirs() -> Generator[SyncLanguageServer, None, None]:
    """Fixture to set up an LS for the python test repo with the 'scripts' directory ignored."""
    ignored_paths = ["scripts", "custom_test"]
    ls = create_ls(ignored_paths=ignored_paths, language=Language.PYTHON)
    ls.start()
    try:
        yield ls
    finally:
        ls.stop()


@pytest.mark.parametrize("ls_with_ignored_dirs", [Language.PYTHON], indirect=True)
def test_symbol_tree_ignores_dir(ls_with_ignored_dirs: SyncLanguageServer):
    """Tests that request_full_symbol_tree ignores the configured directory."""
    root = ls_with_ignored_dirs.request_full_symbol_tree()[0]
    root_children = root["children"]
    children_names = {child["name"] for child in root_children}
    assert children_names == {"test_repo", "examples"}


@pytest.mark.parametrize("ls_with_ignored_dirs", [Language.PYTHON], indirect=True)
def test_find_references_ignores_dir(ls_with_ignored_dirs: SyncLanguageServer):
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
    ls = create_ls(ignored_paths=ignored_paths, repo_path=str(repo_path), language=Language.PYTHON)
    ls.start()
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
