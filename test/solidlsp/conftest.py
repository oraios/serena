import re
from pathlib import Path

from serena.util.text_utils import find_text_coordinates
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind, UnifiedSymbolInformation

PYTHON_BACKEND_LANGUAGES = [Language.PYTHON, Language.PYTHON_TY]


def find_in_file(language_server: SolidLanguageServer, relative_path: str, needle: str) -> tuple[int, int]:
    """Locate the (line, column) of the first occurrence of literal ``needle`` in ``relative_path``.

    Thin convenience wrapper around :func:`serena.util.text_utils.find_text_coordinates` that
    reads the file via the language server's repository root and accepts a literal substring
    instead of a regex; returns a plain ``(line, col)`` tuple for ergonomic test code.
    """
    abs_path = Path(language_server.language_server.repository_root_path) / relative_path
    coords = find_text_coordinates(abs_path.read_text(), f"({re.escape(needle)})")
    assert coords is not None, f"Could not find '{needle}' in {relative_path}"
    return coords.line, coords.col


def is_diagnostics_test_file(relative_path: str) -> bool:
    normalized_path = relative_path.replace("\\", "/")
    filename = normalized_path.rsplit("/", 1)[-1].lower()
    return filename.startswith(("diagnosticssample.", "diagnostics_sample."))


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
        relative_path = symbol.get("location", {}).get("relativePath", "")
        if relative_path and is_diagnostics_test_file(relative_path):
            return
        result.append(symbol)
        for child in symbol.get("children", []):
            visit(child)

    symbols = language_server.request_full_symbol_tree()
    for symbol in symbols:
        visit(symbol)

    return result


def format_symbol_for_assert(symbol: UnifiedSymbolInformation) -> str:
    relative_path = symbol.get("location", {}).get("relativePath", "<unknown>")
    try:
        kind = SymbolKind(symbol["kind"]).name
    except ValueError:
        kind = str(symbol["kind"])
    return f"{symbol['name']} [{kind}] ({relative_path})"
