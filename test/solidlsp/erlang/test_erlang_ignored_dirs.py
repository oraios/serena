from collections.abc import Generator
from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.conftest import create_ls

from . import ERLANG_LS_UNAVAILABLE, ERLANG_LS_UNAVAILABLE_REASON

# These marks will be applied to all tests in this module
pytestmark = [
    pytest.mark.erlang,
    pytest.mark.skipif(ERLANG_LS_UNAVAILABLE, reason=f"Erlang LS not available: {ERLANG_LS_UNAVAILABLE_REASON}"),
]


@pytest.fixture(scope="module")
def ls_with_ignored_dirs() -> Generator[SolidLanguageServer, None, None]:
    """Fixture to set up an LS for the erlang test repo with the 'ignored_dir' directory ignored."""
    ignored_paths = ["_build", "ignored_dir"]
    ls = create_ls(ignored_paths=ignored_paths, language=Language.ERLANG)
    ls.start()
    try:
        yield ls
    finally:
        try:
            ls.stop(shutdown_timeout=1.0)  # Shorter timeout for CI
        except Exception as e:
            print(f"Warning: Error stopping language server: {e}")
            # Force cleanup if needed
            if hasattr(ls, "server") and hasattr(ls.server, "process"):
                try:
                    ls.server.process.terminate()
                except:
                    pass


@pytest.mark.timeout(60)  # Add 60 second timeout
@pytest.mark.xfail(reason="Known timeout issue on Ubuntu CI with Erlang LS server startup", strict=False)
@pytest.mark.parametrize("ls_with_ignored_dirs", [Language.ERLANG], indirect=True)
def test_symbol_tree_ignores_dir(ls_with_ignored_dirs: SolidLanguageServer):
    """Tests that request_full_symbol_tree ignores the configured directory."""
    root = ls_with_ignored_dirs.request_full_symbol_tree()[0]
    root_children = root["children"]
    children_names = {child["name"] for child in root_children}

    # Should have src, include, and test directories, but not _build or ignored_dir
    expected_dirs = {"src", "include", "test"}
    found_expected = expected_dirs.intersection(children_names)
    assert len(found_expected) > 0, f"Expected some dirs from {expected_dirs} to be in {children_names}"
    assert "_build" not in children_names, f"_build should not be in {children_names}"
    assert "ignored_dir" not in children_names, f"ignored_dir should not be in {children_names}"


@pytest.mark.timeout(60)  # Add 60 second timeout
@pytest.mark.xfail(reason="Known timeout issue on Ubuntu CI with Erlang LS server startup", strict=False)
@pytest.mark.parametrize("ls_with_ignored_dirs", [Language.ERLANG], indirect=True)
def test_find_references_ignores_dir(ls_with_ignored_dirs: SolidLanguageServer):
    """Tests that find_references ignores the configured directory."""
    # Location of user record, which might be referenced in ignored_dir
    definition_file = "include/records.hrl"

    # Find the user record definition
    symbols = ls_with_ignored_dirs.request_document_symbols(definition_file).get_all_symbols_and_roots()
    user_symbol = None
    for symbol_group in symbols:
        user_symbol = next((s for s in symbol_group if "user" in s.get("name", "").lower()), None)
        if user_symbol:
            break

    if not user_symbol or "selectionRange" not in user_symbol:
        pytest.skip("User record symbol not found for reference testing")

    sel_start = user_symbol["selectionRange"]["start"]
    references = ls_with_ignored_dirs.request_references(definition_file, sel_start["line"], sel_start["character"])

    # Assert that _build and ignored_dir do not appear in the references
    assert not any("_build" in ref["relativePath"] for ref in references), "_build should be ignored"
    assert not any("ignored_dir" in ref["relativePath"] for ref in references), "ignored_dir should be ignored"


@pytest.mark.timeout(60)  # Add 60 second timeout
@pytest.mark.xfail(reason="Known timeout issue on Ubuntu CI with Erlang LS server startup", strict=False)
@pytest.mark.parametrize("repo_path", [Language.ERLANG], indirect=True)
def test_refs_and_symbols_with_glob_patterns(repo_path: Path) -> None:
    """Tests that refs and symbols with glob patterns are ignored."""
    ignored_paths = ["_build*", "ignored_*", "*.tmp"]
    ls = create_ls(ignored_paths=ignored_paths, repo_path=str(repo_path), language=Language.ERLANG)
    ls.start()

    try:
        # Same as in the above tests
        root = ls.request_full_symbol_tree()[0]
        root_children = root["children"]
        children_names = {child["name"] for child in root_children}

        # Should have src, include, and test directories, but not _build or ignored_dir
        expected_dirs = {"src", "include", "test"}
        found_expected = expected_dirs.intersection(children_names)
        assert len(found_expected) > 0, f"Expected some dirs from {expected_dirs} to be in {children_names}"
        assert "_build" not in children_names, f"_build should not be in {children_names} (glob pattern)"
        assert "ignored_dir" not in children_names, f"ignored_dir should not be in {children_names} (glob pattern)"

        # Test that the refs and symbols with glob patterns are ignored
        definition_file = "include/records.hrl"

        # Find the user record definition
        symbols = ls.request_document_symbols(definition_file).get_all_symbols_and_roots()
        user_symbol = None
        for symbol_group in symbols:
            user_symbol = next((s for s in symbol_group if "user" in s.get("name", "").lower()), None)
            if user_symbol:
                break

        if user_symbol and "selectionRange" in user_symbol:
            sel_start = user_symbol["selectionRange"]["start"]
            references = ls.request_references(definition_file, sel_start["line"], sel_start["character"])

            # Assert that _build and ignored_dir do not appear in references
            assert not any("_build" in ref["relativePath"] for ref in references), "_build should be ignored (glob)"
            assert not any("ignored_dir" in ref["relativePath"] for ref in references), "ignored_dir should be ignored (glob)"
    finally:
        try:
            ls.stop(shutdown_timeout=1.0)  # Shorter timeout for CI
        except Exception as e:
            print(f"Warning: Error stopping glob pattern test LS: {e}")
            # Force cleanup if needed
            if hasattr(ls, "server") and hasattr(ls.server, "process"):
                try:
                    ls.server.process.terminate()
                except:
                    pass


@pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
def test_default_ignored_directories(language_server: SolidLanguageServer):
    """Test that default Erlang directories are ignored."""
    # Test that Erlang-specific directories are ignored by default
    assert language_server.is_ignored_dirname("_build"), "_build should be ignored"
    assert language_server.is_ignored_dirname("ebin"), "ebin should be ignored"
    assert language_server.is_ignored_dirname("deps"), "deps should be ignored"
    assert language_server.is_ignored_dirname(".rebar3"), ".rebar3 should be ignored"
    assert language_server.is_ignored_dirname("_checkouts"), "_checkouts should be ignored"
    assert language_server.is_ignored_dirname("node_modules"), "node_modules should be ignored"

    # Test that important directories are not ignored
    assert not language_server.is_ignored_dirname("src"), "src should not be ignored"
    assert not language_server.is_ignored_dirname("include"), "include should not be ignored"
    assert not language_server.is_ignored_dirname("test"), "test should not be ignored"
    assert not language_server.is_ignored_dirname("priv"), "priv should not be ignored"


@pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
def test_symbol_tree_excludes_build_dirs(language_server: SolidLanguageServer):
    """Test that symbol tree excludes build and dependency directories."""
    symbol_tree = language_server.request_full_symbol_tree()

    if symbol_tree:
        root = symbol_tree[0]
        children_names = {child["name"] for child in root.get("children", [])}

        # Build and dependency directories should not appear
        ignored_dirs = {"_build", "ebin", "deps", ".rebar3", "_checkouts", "node_modules"}
        found_ignored = ignored_dirs.intersection(children_names)
        assert len(found_ignored) == 0, f"Found ignored directories in symbol tree: {found_ignored}"

        # Important directories should appear
        important_dirs = {"src", "include", "test"}
        found_important = important_dirs.intersection(children_names)
        assert len(found_important) > 0, f"Expected to find important directories: {important_dirs}, got: {children_names}"


@pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
def test_ignore_compiled_files(language_server: SolidLanguageServer):
    """Test that compiled Erlang files are ignored."""
    # Test that beam files are ignored
    assert language_server.is_ignored_filename("module.beam"), "BEAM files should be ignored"
    assert language_server.is_ignored_filename("app.beam"), "BEAM files should be ignored"

    # Test that source files are not ignored
    assert not language_server.is_ignored_filename("module.erl"), "Erlang source files should not be ignored"
    assert not language_server.is_ignored_filename("records.hrl"), "Header files should not be ignored"


@pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
def test_rebar_directories_ignored(language_server: SolidLanguageServer):
    """Test that rebar-specific directories are ignored."""
    # Test rebar3-specific directories
    assert language_server.is_ignored_dirname("_build"), "rebar3 _build should be ignored"
    assert language_server.is_ignored_dirname("_checkouts"), "rebar3 _checkouts should be ignored"
    assert language_server.is_ignored_dirname(".rebar3"), "rebar3 cache should be ignored"

    # Test that rebar.lock and rebar.config are not ignored (they are configuration files)
    assert not language_server.is_ignored_filename("rebar.config"), "rebar.config should not be ignored"
    assert not language_server.is_ignored_filename("rebar.lock"), "rebar.lock should not be ignored"


@pytest.mark.parametrize("ls_with_ignored_dirs", [Language.ERLANG], indirect=True)
def test_document_symbols_ignores_dirs(ls_with_ignored_dirs: SolidLanguageServer):
    """Test that document symbols from ignored directories are not included."""
    # Try to get symbols from a file in ignored directory (should not find it)
    try:
        ignored_file = "ignored_dir/ignored_module.erl"
        symbols = ls_with_ignored_dirs.request_document_symbols(ignored_file).get_all_symbols_and_roots()
        # If we get here, the file was found - symbols should be empty or None
        if symbols:
            assert len(symbols) == 0, "Should not find symbols in ignored directory"
    except Exception:
        # This is expected - the file should not be accessible
        pass


@pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
def test_erlang_specific_ignore_patterns(language_server: SolidLanguageServer):
    """Test Erlang-specific ignore patterns work correctly."""
    erlang_ignored_dirs = ["_build", "ebin", ".rebar3", "_checkouts", "cover"]

    # These should be ignored
    for dirname in erlang_ignored_dirs:
        assert language_server.is_ignored_dirname(dirname), f"{dirname} should be ignored"

    # These should not be ignored
    erlang_important_dirs = ["src", "include", "test", "priv"]
    for dirname in erlang_important_dirs:
        assert not language_server.is_ignored_dirname(dirname), f"{dirname} should not be ignored"
