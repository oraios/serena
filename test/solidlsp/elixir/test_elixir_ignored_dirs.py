import os
from collections.abc import Generator
from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.conftest import start_ls_context

from . import EXPERT_UNAVAILABLE, EXPERT_UNAVAILABLE_REASON

# These marks will be applied to all tests in this module
pytestmark = [pytest.mark.elixir, pytest.mark.skipif(EXPERT_UNAVAILABLE, reason=f"Expert not available: {EXPERT_UNAVAILABLE_REASON}")]

# Skip slow tests in CI - they require multiple Expert instances which is too slow
IN_CI = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))
SKIP_SLOW_IN_CI = pytest.mark.skipif(
    IN_CI,
    reason="Slow tests skipped in CI - require multiple Expert instances (~60-90s each)",
)


@pytest.fixture(scope="session")
def ls_with_ignored_dirs() -> Generator[SolidLanguageServer, None, None]:
    """Fixture to set up an LS for the elixir test repo with the 'scripts' directory ignored.

    Uses session scope to avoid restarting Expert for each test.
    """
    ignored_paths = ["scripts", "ignored_dir"]
    with start_ls_context(language=Language.ELIXIR, ignored_paths=ignored_paths) as ls:
        yield ls


@pytest.mark.slow
@SKIP_SLOW_IN_CI
def test_symbol_tree_ignores_dir(ls_with_ignored_dirs: SolidLanguageServer):
    """Tests that request_full_symbol_tree ignores the configured directory.

    Note: This test uses a separate Expert instance with custom ignored paths,
    which adds ~60-90s startup time.
    """
    root = ls_with_ignored_dirs.request_full_symbol_tree()[0]
    root_children = root["children"]
    children_names = {child["name"] for child in root_children}

    # Should have lib and test directories, but not scripts or ignored_dir
    expected_dirs = {"lib", "test"}
    assert expected_dirs.issubset(children_names), f"Expected {expected_dirs} to be in {children_names}"
    assert "scripts" not in children_names, f"scripts should not be in {children_names}"
    assert "ignored_dir" not in children_names, f"ignored_dir should not be in {children_names}"


@pytest.mark.slow
@SKIP_SLOW_IN_CI
def test_find_references_ignores_dir(ls_with_ignored_dirs: SolidLanguageServer):
    """Tests that find_references ignores the configured directory.

    Note: This test uses a separate Expert instance with custom ignored paths,
    which adds ~60-90s startup time.
    """
    # Location of User struct, which is referenced in scripts and ignored_dir
    definition_file = "lib/models.ex"

    # Find the User struct definition
    symbols = ls_with_ignored_dirs.request_document_symbols(definition_file).get_all_symbols_and_roots()
    user_symbol = None
    for symbol_group in symbols:
        user_symbol = next((s for s in symbol_group if "User" in s.get("name", "")), None)
        if user_symbol:
            break

    if not user_symbol or "selectionRange" not in user_symbol:
        pytest.skip("User symbol not found for reference testing")

    sel_start = user_symbol["selectionRange"]["start"]
    references = ls_with_ignored_dirs.request_references(definition_file, sel_start["line"], sel_start["character"])

    # Assert that scripts and ignored_dir do not appear in the references
    assert not any("scripts" in ref["relativePath"] for ref in references), "scripts should be ignored"
    assert not any("ignored_dir" in ref["relativePath"] for ref in references), "ignored_dir should be ignored"


@pytest.mark.slow
@SKIP_SLOW_IN_CI
@pytest.mark.parametrize("repo_path", [Language.ELIXIR], indirect=True)
def test_refs_and_symbols_with_glob_patterns(repo_path: Path) -> None:
    """Tests that refs and symbols with glob patterns are ignored.

    Note: This test uses a separate Expert instance with custom ignored paths,
    which adds ~60-90s startup time.
    """
    ignored_paths = ["*cripts", "ignored_*"]  # codespell:ignore cripts
    with start_ls_context(language=Language.ELIXIR, repo_path=str(repo_path), ignored_paths=ignored_paths) as ls:

        # Same as in the above tests
        root = ls.request_full_symbol_tree()[0]
        root_children = root["children"]
        children_names = {child["name"] for child in root_children}

        # Should have lib and test directories, but not scripts or ignored_dir
        expected_dirs = {"lib", "test"}
        assert expected_dirs.issubset(children_names), f"Expected {expected_dirs} to be in {children_names}"
        assert "scripts" not in children_names, f"scripts should not be in {children_names} (glob pattern)"
        assert "ignored_dir" not in children_names, f"ignored_dir should not be in {children_names} (glob pattern)"

        # Test that the refs and symbols with glob patterns are ignored
        definition_file = "lib/models.ex"

        # Find the User struct definition
        symbols = ls.request_document_symbols(definition_file).get_all_symbols_and_roots()
        user_symbol = None
        for symbol_group in symbols:
            user_symbol = next((s for s in symbol_group if "User" in s.get("name", "")), None)
            if user_symbol:
                break

        if user_symbol and "selectionRange" in user_symbol:
            sel_start = user_symbol["selectionRange"]["start"]
            references = ls.request_references(definition_file, sel_start["line"], sel_start["character"])

            # Assert that scripts and ignored_dir do not appear in references
            assert not any("scripts" in ref["relativePath"] for ref in references), "scripts should be ignored (glob)"
            assert not any("ignored_dir" in ref["relativePath"] for ref in references), "ignored_dir should be ignored (glob)"


@pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
def test_default_ignored_directories(language_server: SolidLanguageServer):
    """Test that default Elixir directories are ignored."""
    # Test that Elixir-specific directories are ignored by default
    assert language_server.is_ignored_dirname("_build"), "_build should be ignored"
    assert language_server.is_ignored_dirname("deps"), "deps should be ignored"
    assert language_server.is_ignored_dirname(".elixir_ls"), ".elixir_ls should be ignored"
    assert language_server.is_ignored_dirname("cover"), "cover should be ignored"
    assert language_server.is_ignored_dirname("node_modules"), "node_modules should be ignored"

    # Test that important directories are not ignored
    assert not language_server.is_ignored_dirname("lib"), "lib should not be ignored"
    assert not language_server.is_ignored_dirname("test"), "test should not be ignored"
    assert not language_server.is_ignored_dirname("config"), "config should not be ignored"
    assert not language_server.is_ignored_dirname("priv"), "priv should not be ignored"


@pytest.mark.xfail(
    reason="Expert 0.1.0 bug: document_symbols may return nil for some files (flaky)",
    raises=Exception,
)
@pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
def test_symbol_tree_excludes_build_dirs(language_server: SolidLanguageServer):
    """Test that symbol tree excludes build and dependency directories."""
    symbol_tree = language_server.request_full_symbol_tree()

    if symbol_tree:
        root = symbol_tree[0]
        children_names = {child["name"] for child in root.get("children", [])}

        # Build and dependency directories should not appear
        ignored_dirs = {"_build", "deps", ".elixir_ls", "cover", "node_modules"}
        found_ignored = ignored_dirs.intersection(children_names)
        assert len(found_ignored) == 0, f"Found ignored directories in symbol tree: {found_ignored}"

        # Important directories should appear
        important_dirs = {"lib", "test"}
        found_important = important_dirs.intersection(children_names)
        assert len(found_important) > 0, f"Expected to find important directories: {important_dirs}, got: {children_names}"
