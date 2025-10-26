import os
import pathlib

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.language_servers.gdscript_language_server import GDScriptLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_exceptions import SolidLSPException
from test.conftest import create_ls

pytestmark = [
    pytest.mark.gdscript,
    pytest.mark.skipif(not os.environ.get("GODOT_PATH"), reason="Requires GODOT_PATH to point to a Godot executable"),
]


def _ensure_server_ready(language_server: SolidLanguageServer, timeout: float = 180.0) -> GDScriptLanguageServer:
    server = language_server.language_server
    if not isinstance(server, GDScriptLanguageServer):
        raise AssertionError(f"Expected GDScriptLanguageServer, got {type(server)}")
    if not server.server_ready.wait(timeout):
        raise AssertionError("GDScript language server did not report ready in time")
    if not server.completions_available.wait(timeout):
        raise AssertionError("GDScript language server did not make completions available in time")
    return server


def _find_identifier_position(file_path: pathlib.Path, identifier: str) -> tuple[int, int]:
    for line_number, line in enumerate(file_path.read_text().splitlines()):
        column = line.find(identifier)
        if column != -1:
            return line_number, column
    raise AssertionError(f"Identifier '{identifier}' not found in {file_path}")


@pytest.mark.parametrize("gdscript_ls_with_ignored_dirs", [Language.GDSCRIPT], indirect=True)
def test_symbol_tree_ignores_dir(gdscript_ls_with_ignored_dirs: SolidLanguageServer) -> None:
    root = gdscript_ls_with_ignored_dirs.request_full_symbol_tree()[0]
    children = {child["name"] for child in root["children"]}
    assert "scripts" not in children
    assert "custom_test" not in children
    assert "src" in children


@pytest.mark.parametrize("gdscript_ls_with_ignored_dirs", [Language.GDSCRIPT], indirect=True)
def test_find_references_ignores_dir(gdscript_ls_with_ignored_dirs: SolidLanguageServer, gdscript_repo_path: pathlib.Path) -> None:
    player_path = pathlib.Path("src/player.gd")
    line, column = _find_identifier_position(gdscript_repo_path / player_path, "class_name Player")
    references = gdscript_ls_with_ignored_dirs.request_references(str(player_path), line, column + len("class_name ") + 1)
    ref_paths = {ref["relativePath"].replace("\\", "/") for ref in references}
    assert not any(path.startswith("scripts/") for path in ref_paths)
    assert not any(path.startswith("custom_test/") for path in ref_paths)


def test_refs_and_symbols_with_glob_patterns(gdscript_repo_path: pathlib.Path) -> None:
    ignored = ["*ipts", "custom_t*"]
    ls = create_ls(language=Language.GDSCRIPT, repo_path=str(gdscript_repo_path), ignored_paths=ignored)
    ls.start()
    try:
        _ensure_server_ready(ls)
        root = ls.request_full_symbol_tree()[0]
        children = {child["name"] for child in root["children"]}
        assert "scripts" not in children
        assert "custom_test" not in children
        assert "src" in children

        player_path = pathlib.Path("src/player.gd")
        line, column = _find_identifier_position(gdscript_repo_path / player_path, "class_name Player")
        references = ls.request_references(str(player_path), line, column + len("class_name ") + 1)
        ref_paths = {ref["relativePath"].replace("\\", "/") for ref in references}
        assert not any(path.startswith("scripts/") for path in ref_paths)
        assert not any(path.startswith("custom_test/") for path in ref_paths)
    finally:
        try:
            ls.stop()
        except SolidLSPException:
            pass


@pytest.mark.parametrize("language_server", [Language.GDSCRIPT], indirect=True)
def test_default_ignored_directories(language_server: SolidLanguageServer) -> None:
    server = _ensure_server_ready(language_server)
    for dirname in [".godot", "build", "dist", "node_modules"]:
        assert server.is_ignored_dirname(dirname)
    assert not server.is_ignored_dirname("src")
