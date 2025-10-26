import os
import pathlib

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.language_servers.gdscript_language_server import GDScriptLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_utils import SymbolUtils
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


@pytest.fixture(scope="module")
def running_ls(gdscript_repo_path: pathlib.Path) -> SolidLanguageServer:
    ls = create_ls(language=Language.GDSCRIPT, repo_path=str(gdscript_repo_path))
    ls.start()
    try:
        _ensure_server_ready(ls)
        yield ls
    finally:
        try:
            ls.stop()
        except SolidLSPException:
            pass


def test_find_symbol(running_ls: SolidLanguageServer) -> None:
    symbols = running_ls.request_full_symbol_tree()
    assert SymbolUtils.symbol_tree_contains_name(symbols, "Player"), "Player class missing from symbol tree"
    assert SymbolUtils.symbol_tree_contains_name(symbols, "MathUtils"), "MathUtils class missing from symbol tree"


def test_find_referencing_symbols(running_ls: SolidLanguageServer, gdscript_repo_path: pathlib.Path) -> None:
    player_path = pathlib.Path("src/player.gd")
    line, column = _find_identifier_position(gdscript_repo_path / player_path, "class_name Player")
    references = running_ls.request_references(str(player_path), line, column + len("class_name ") + 1)
    ref_paths = {ref["relativePath"].replace("\\", "/") for ref in references}
    assert "main.gd" in ref_paths
    assert "scripts/npc.gd" in ref_paths
    assert "generated/extra_usage.gd" in ref_paths


def test_symbol_tree_excludes_build_dirs(running_ls: SolidLanguageServer) -> None:
    root = running_ls.request_full_symbol_tree()[0]
    children = {child["name"] for child in root["children"]}
    assert "build" not in children
    assert "dist" not in children


def test_document_symbols_surface_player_members(running_ls: SolidLanguageServer) -> None:
    all_symbols, roots = running_ls.request_document_symbols("src/player.gd")
    symbol_names = {symbol.get("name", "") for symbol in all_symbols if symbol.get("name")}
    normalized_names = {name.split("(")[0] for name in symbol_names}
    root_names = {root.get("name", "") for root in roots if root.get("name")}
    assert any("player" in name.lower() for name in normalized_names), "Expected Player symbol in document symbols"
    assert {"greet", "heal"}.issubset({name.lower() for name in normalized_names})
    assert any("player" in name.lower() for name in root_names), "Expected Player file or class among root symbols"


def test_defining_symbol_resolves_across_files(running_ls: SolidLanguageServer, gdscript_repo_path: pathlib.Path) -> None:
    line, column = _find_identifier_position(gdscript_repo_path / "main.gd", "Player.new")
    definition = running_ls.request_defining_symbol("main.gd", line, column + 1)
    assert definition is not None, "Expected definition for Player usage in main.gd"
    location = definition.get("location", {})
    relative_path = location.get("relativePath") or location.get("uri", "")
    assert "src/player.gd" in str(relative_path).replace("\\", "/")
    assert "Player" in str(definition.get("name", ""))


def test_containing_symbol_for_method_block(running_ls: SolidLanguageServer, gdscript_repo_path: pathlib.Path) -> None:
    player_file = gdscript_repo_path / "src" / "player.gd"
    line, column = _find_identifier_position(player_file, "func greet")
    containing = running_ls.request_containing_symbol("src/player.gd", line, column + len("func "))
    assert containing is not None, "Expected to locate containing symbol for greet"
    assert "greet" in containing.get("name", "")


def test_completions_offer_player_members(running_ls: SolidLanguageServer, gdscript_repo_path: pathlib.Path) -> None:
    line, column = _find_identifier_position(gdscript_repo_path / "main.gd", "player.")
    completions = running_ls.request_completions("main.gd", line, column + len("player."))
    completion_texts = {item["completionText"].lower() for item in completions}
    assert completion_texts, "Expected completions to be returned for player access"
    assert any("res://" in text for text in completion_texts), f"Unexpected completion payload: {completion_texts}"
