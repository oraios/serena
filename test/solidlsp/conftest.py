from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import UnifiedSymbolInformation

PYTHON_BACKEND_LANGUAGES = [Language.PYTHON, Language.PYTHON_TY]


def has_malformed_name(
    symbol: UnifiedSymbolInformation,
    whitespace_allowed: bool = False,
    period_allowed: bool = False,
    colon_allowed: bool = False,
    brace_allowed: bool = False,
    parenthesis_allowed: bool = False,
    comma_allowed: bool = False,
) -> bool:
    forbidden_chars: list[str] = []

    if not whitespace_allowed:
        forbidden_chars.append(" ")
    if not period_allowed:
        forbidden_chars.append(".")
    if not colon_allowed:
        forbidden_chars.append(":")
    if not brace_allowed:
        forbidden_chars.append("{")
    if not parenthesis_allowed:
        forbidden_chars.append("(")
    if not comma_allowed:
        forbidden_chars.append(",")

    return any(separator in symbol["name"] for separator in forbidden_chars)


def request_all_symbols(language_server: SolidLanguageServer) -> list[UnifiedSymbolInformation]:
    result: list[UnifiedSymbolInformation] = []

    def visit(symbol: UnifiedSymbolInformation) -> None:
        result.append(symbol)
        for child in symbol.get("children", []):
            visit(child)

    symbols = language_server.request_full_symbol_tree()
    for symbol in symbols:
        visit(symbol)

    return result
