"""
Tests for the experimental EmmyLua Analyzer language server backend (``lua_emmylua``).

They run against the shared Lua test repository and validate symbol finding as well as
within-file and cross-file reference finding.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_types import SymbolKind
from test.conftest import find_identifier_pos, get_repo_path
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols


def _function_names(language_server: SolidLanguageServer, relative_path: str) -> set[str]:
    symbols = language_server.request_document_symbols(relative_path).get_all_symbols_and_roots()
    symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols
    return {s["name"] for s in symbol_list if s.get("kind") in (SymbolKind.Function, SymbolKind.Method)}


def _reference_lines_by_file(
    language_server: SolidLanguageServer, relative_path: str, identifier: str, occurrence: int = 0
) -> dict[str, set[int]]:
    """Requests references for the given occurrence of ``identifier`` and returns the (0-based) lines by file name."""
    pos = find_identifier_pos(get_repo_path(LanguageServerId.LUA_EMMYLUA) / relative_path, identifier, occurrence)
    assert pos is not None, f"Could not find occurrence {occurrence} of '{identifier}' in {relative_path}"
    references = language_server.request_references(relative_path, *pos)
    lines_by_file: dict[str, set[int]] = {}
    for reference in references:
        file_name = reference["uri"].split("/")[-1]
        lines_by_file.setdefault(file_name, set()).add(reference["range"]["start"]["line"])
    return lines_by_file


@pytest.mark.lua
class TestEmmyLuaLanguageServer:
    @pytest.mark.parametrize("language_server", [LanguageServerId.LUA_EMMYLUA], indirect=True)
    def test_find_symbols_in_calculator(self, language_server: SolidLanguageServer) -> None:
        function_names = _function_names(language_server, "src/calculator.lua")
        expected = {"add", "subtract", "multiply", "divide", "power", "factorial", "mean", "median"}
        assert expected <= function_names, f"Missing functions: {expected - function_names}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.LUA_EMMYLUA], indirect=True)
    def test_find_symbols_in_utils(self, language_server: SolidLanguageServer) -> None:
        function_names = _function_names(language_server, "src/utils.lua")
        expected = {"trim", "split", "starts_with", "ends_with", "deep_copy"}
        assert expected <= function_names, f"Missing functions: {expected - function_names}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.LUA_EMMYLUA], indirect=True)
    def test_find_symbols_in_main(self, language_server: SolidLanguageServer) -> None:
        function_names = _function_names(language_server, "main.lua")
        expected = {"print_banner", "test_calculator", "test_utils", "test_animals", "interactive_calculator"}
        assert expected <= function_names, f"Missing functions: {expected - function_names}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.LUA_EMMYLUA], indirect=True)
    def test_find_symbols_in_animals_with_method_syntax(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_document_symbols("src/animals.lua").get_all_symbols_and_roots()
        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols
        names_by_kind = {(s["name"], s["kind"]) for s in symbol_list}
        # methods defined via `function Animal:speak()` must be reported with their bare names
        assert ("new", SymbolKind.Function) in names_by_kind or ("new", SymbolKind.Method) in names_by_kind
        assert ("speak", SymbolKind.Function) in names_by_kind or ("speak", SymbolKind.Method) in names_by_kind
        assert ("Animal", SymbolKind.Class) in names_by_kind
        assert ("Dog", SymbolKind.Class) in names_by_kind

    @pytest.mark.parametrize("language_server", [LanguageServerId.LUA_EMMYLUA], indirect=True)
    def test_within_file_references(self, language_server: SolidLanguageServer) -> None:
        # the second occurrence of `Animal` is the declaration `local Animal = {}` (line 2); it is used within animals.lua
        # in `Animal.__index = Animal` (line 3), `setmetatable({}, Animal)` (line 8) and `__index = Animal` (line 19)
        lines_by_file = _reference_lines_by_file(language_server, "src/animals.lua", "Animal", occurrence=1)
        assert "animals.lua" in lines_by_file
        animals_lines = lines_by_file["animals.lua"]
        assert {7, 18} <= animals_lines, f"Expected references to Animal at (0-based) lines 7 and 18, got {sorted(animals_lines)}"
        assert set(lines_by_file) == {"animals.lua"}, f"Animal is local to animals.lua, but references were found in {set(lines_by_file)}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.LUA_EMMYLUA], indirect=True)
    def test_cross_file_references_calculator_factorial(self, language_server: SolidLanguageServer) -> None:
        lines_by_file = _reference_lines_by_file(language_server, "src/calculator.lua", "factorial")
        # main.lua line 22 (0-based: 21) calls calculator.factorial(5)
        assert 21 in lines_by_file.get("main.lua", set()), f"Expected usage in main.lua at line 22, got {lines_by_file}"
        # test_calculator.lua uses factorial in several assertions
        assert lines_by_file.get("test_calculator.lua"), f"Expected usages in test_calculator.lua, got {lines_by_file}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.LUA_EMMYLUA], indirect=True)
    def test_cross_file_references_utils_trim(self, language_server: SolidLanguageServer) -> None:
        lines_by_file = _reference_lines_by_file(language_server, "src/utils.lua", "trim")
        # main.lua line 33 (0-based: 32) calls utils.trim("  hello  ")
        assert 32 in lines_by_file.get("main.lua", set()), f"Expected usage in main.lua at line 33, got {lines_by_file}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.LUA_EMMYLUA], indirect=True)
    def test_bare_symbol_names(self, language_server: SolidLanguageServer) -> None:
        malformed_symbols = [
            s
            for s in request_all_symbols(language_server)
            if has_malformed_name(s, whitespace_allowed=s["name"] == " " or s["name"].startswith(("for ", "while ")))
        ]
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )
