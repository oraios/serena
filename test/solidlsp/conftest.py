import re
from collections.abc import Callable

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_types import SymbolKind, UnifiedSymbolInformation

_KEYWORD_PREFIX_PATTERN = re.compile(r"^(?:class|function|interface|enum|struct|module|type)\s+")
_GO_RECEIVER_PATTERN = re.compile(r"^(?:\(\*?[\w\[\], ]+\)|\*?[\w\[\], ]+)\.[A-Za-z_]\w*$")
_TYPED_SIGNATURE_PATTERN = re.compile(r"^(?:[\w\[\].]+\s+)+(?P<name>[A-Za-z_][\w-]*)\s*\(.*\)$")
_CALL_SIGNATURE_PATTERN = re.compile(r"^[A-Za-z_][\w-]*\s*\(.*\)\s*(?::\s*.+)?$")
_TYPE_ANNOTATION_PATTERN = re.compile(r"^[A-Za-z_][\w-]*\s*:\s*.+$")

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


def _is_decorated_symbol_name(name: str, kind: int) -> bool:
    if kind in _TYPE_KINDS:
        return _KEYWORD_PREFIX_PATTERN.match(name) is not None

    if kind in _CALLABLE_KINDS:
        return any(
            [
                _KEYWORD_PREFIX_PATTERN.match(name) is not None,
                _GO_RECEIVER_PATTERN.match(name) is not None,
                _TYPED_SIGNATURE_PATTERN.match(name) is not None,
                _CALL_SIGNATURE_PATTERN.match(name) is not None,
            ]
        )

    if kind in _MEMBER_KINDS:
        return _TYPE_ANNOTATION_PATTERN.match(name) is not None

    return False


@pytest.fixture
def assert_bare_symbol_names() -> Callable[[SolidLanguageServer], None]:
    def assert_for_language_server(language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        offending_symbols = [
            f"{SymbolKind(symbol['kind']).name}:{symbol['name']}"
            for symbol in _iter_symbols(symbols)
            if _is_decorated_symbol_name(symbol["name"], symbol["kind"])
        ]

        assert not offending_symbols, (
            f"Expected bare symbol names for {language_server.language}, but found decorated names: {offending_symbols[:20]}"
        )

    return assert_for_language_server
