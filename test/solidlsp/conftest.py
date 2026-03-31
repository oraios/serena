from collections.abc import Callable

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind, UnifiedSymbolInformation

_TYPE_KEYWORD_PREFIXES = ("class ", "interface ", "enum ", "struct ", "module ", "type ")
_CALLABLE_KEYWORD_PREFIXES = _TYPE_KEYWORD_PREFIXES + ("function ", "def ", "defp ")
_AL_CALLABLE_KEYWORD_PREFIXES = _CALLABLE_KEYWORD_PREFIXES + ("action ",)

_CALLABLE_KINDS = {
    SymbolKind.Function,
    SymbolKind.Method,
    SymbolKind.Constructor,
}
_TYPE_KINDS = {
    SymbolKind.Class,
    SymbolKind.Struct,
    SymbolKind.Interface,
    SymbolKind.Enum,
}
_MEMBER_KINDS = {
    SymbolKind.Property,
    SymbolKind.Field,
}


def _iter_symbols(symbols: list[UnifiedSymbolInformation]) -> list[UnifiedSymbolInformation]:
    result: list[UnifiedSymbolInformation] = []

    def visit(symbol: UnifiedSymbolInformation) -> None:
        result.append(symbol)
        for child in symbol.get("children", []):
            visit(child)

    for symbol in symbols:
        visit(symbol)

    return result


def _is_decorated_symbol_name_default(name: str, kind: int) -> bool:
    stripped_name = name.strip()
    lowercase_name = stripped_name.lower()

    if kind in _TYPE_KINDS:
        return lowercase_name.startswith(_TYPE_KEYWORD_PREFIXES)

    if kind in _CALLABLE_KINDS:
        return lowercase_name.startswith(_CALLABLE_KEYWORD_PREFIXES) or any(
            separator in stripped_name for separator in ("(", ",", ".", "{")
        )

    return False


def _is_decorated_symbol_name_al(name: str, kind: int) -> bool:
    stripped_name = name.strip()
    lowercase_name = stripped_name.lower()

    if kind in _MEMBER_KINDS:
        return ":" in stripped_name

    if kind in _CALLABLE_KINDS:
        return lowercase_name.startswith(_AL_CALLABLE_KEYWORD_PREFIXES) or any(
            separator in stripped_name for separator in ("(", ",", ".", "{")
        )

    return _is_decorated_symbol_name_default(name, kind)


def _is_decorated_symbol_name_elixir(name: str, kind: int) -> bool:
    stripped_name = name.strip()
    lowercase_name = stripped_name.lower()

    if kind in _TYPE_KINDS and stripped_name.startswith("%") and stripped_name.endswith("{}"):
        return False

    if kind in _CALLABLE_KINDS and lowercase_name.startswith(('test "', 'describe "')):
        return False

    return _is_decorated_symbol_name_default(name, kind)


def _is_decorated_symbol_name_nix(name: str, kind: int) -> bool:
    if name.strip() == "(anonymous lambda)":
        return False

    return _is_decorated_symbol_name_default(name, kind)


def _is_decorated_symbol_name_vue(name: str, kind: int) -> bool:
    if name.strip().endswith(" callback"):
        return False

    return _is_decorated_symbol_name_default(name, kind)


_DECORATED_SYMBOL_NAME_CHECKERS: dict[Language, Callable[[str, int], bool]] = {
    Language.AL: _is_decorated_symbol_name_al,
    Language.ELIXIR: _is_decorated_symbol_name_elixir,
    Language.NIX: _is_decorated_symbol_name_nix,
    Language.VUE: _is_decorated_symbol_name_vue,
}


@pytest.fixture
def assert_bare_symbol_names() -> Callable[[SolidLanguageServer], None]:
    def assert_for_language_server(language_server: SolidLanguageServer) -> None:
        is_decorated_symbol_name = _DECORATED_SYMBOL_NAME_CHECKERS.get(language_server.language, _is_decorated_symbol_name_default)
        symbols = language_server.request_full_symbol_tree()
        offending_symbols = [
            f"{symbol['name']}" for symbol in _iter_symbols(symbols) if is_decorated_symbol_name(symbol["name"], symbol["kind"])
        ]

        assert not offending_symbols, (
            f"Expected bare symbol names for {language_server.language}, but found decorated names: {offending_symbols[:20]}"
        )

    return assert_for_language_server
