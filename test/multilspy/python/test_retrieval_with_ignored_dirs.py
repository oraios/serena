from collections.abc import Generator
from pathlib import Path

import pytest

from multilspy.language_server import SyncLanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from test.conftest import get_repo_path


@pytest.fixture(scope="module")
def ls_with_ignored_dirs() -> Generator[SyncLanguageServer, None, None]:
    """Fixture to set up an LS for the python test repo with the 'scripts' directory ignored."""
    config = MultilspyConfig(
        code_language=Language.PYTHON,
        trace_lsp_communication=False,
        ignored_paths=["scripts", "custom_test"],  # Configure the relative path to be ignored
    )
    logger = MultilspyLogger()
    repo_path = get_repo_path(Language.PYTHON)
    ls = SyncLanguageServer.create(config, logger, str(repo_path))
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
    config = MultilspyConfig(
        code_language=Language.PYTHON,
        trace_lsp_communication=False,
        ignored_paths=["*ipts", "custom_t*"],
    )
    logger = MultilspyLogger()
    ls = SyncLanguageServer.create(config, logger, str(repo_path))
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
