from pathlib import Path

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind, UnifiedSymbolInformation

PYTHON_BACKEND_LANGUAGES = [Language.PYTHON, Language.PYTHON_TY]


def find_in_file(language_server: SolidLanguageServer, relative_path: str, needle: str, occurrence: int = 0) -> tuple[int, int]:
    """Locate the (line, column) of ``needle`` in ``relative_path`` (0-based, LSP coords).

    The column points to the first character of the match. Pass ``occurrence`` to skip
    earlier hits when the substring repeats.

    Prefer this over hardcoded coordinates: tests stay readable and don't break when
    the fixture shifts by a line.
    """
    abs_path = Path(language_server.language_server.repository_root_path) / relative_path
    seen = -1
    for i, line in enumerate(abs_path.read_text().splitlines()):
        start = 0
        while True:
            idx = line.find(needle, start)
            if idx < 0:
                break
            seen += 1
            if seen == occurrence:
                return i, idx
            start = idx + 1
    raise AssertionError(f"Could not find occurrence #{occurrence} of '{needle}' in {relative_path}")


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
