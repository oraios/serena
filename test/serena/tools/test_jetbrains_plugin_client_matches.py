# tests/test_jetbrains_plugin_client_matches.py
from pathlib import Path

from serena.tools.jetbrains_plugin_client import JetBrainsPluginClient


def _client_with_plugin_root(root: str):
    c = JetBrainsPluginClient.__new__(JetBrainsPluginClient)
    c._project_root = root
    return c


def test_exact_posix_match():
    c = _client_with_plugin_root("/mnt/c/foo/project")
    assert c.matches(Path("/mnt/c/foo/project"))


def test_windows_drive_match():
    c = _client_with_plugin_root("C:/foo/project")
    assert c.matches(Path("/mnt/c/foo/project"))


def test_devcontainer_prefix_match():
    c = _client_with_plugin_root("/workspaces/serena/C:/Users/me/foo/project")
    assert c.matches(Path("/mnt/c/Users/me/foo/project"))


def test_trailing_and_dotdots():
    c = _client_with_plugin_root("C:/a/b/../project/")
    assert c.matches(Path("/mnt/c/a/project"))


def test_different_projects_false():
    c = _client_with_plugin_root("C:/other/project")
    assert not c.matches(Path("/mnt/c/this/project"))


def test_last_three_components_match():
    c = _client_with_plugin_root("/some/prefix/a/b/c/project")
    assert c.matches(Path("/mnt/c/a/b/c/project"))


def test_original_comparison_logging_no_raise_on_missing():
    # plugin path that doesn't exist locally should not raise
    c = _client_with_plugin_root("C:/nonexistent/path")
    # should simply return False (no exception)
    assert c.matches(Path("/mnt/c/another/path")) is False
