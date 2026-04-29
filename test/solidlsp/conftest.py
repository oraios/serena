from pathlib import Path

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind, UnifiedSymbolInformation

PYTHON_BACKEND_LANGUAGES = [Language.PYTHON, Language.PYTHON_TY, Language.PYTHON_PYREFLY]


def read_repo_file(language_server: SolidLanguageServer, relative_path: str) -> str:
    """Read the text content of ``relative_path`` resolved against the LS's repository root.

    Convenience for test code that needs to feed file content to
    :func:`serena.util.text_utils.find_text_coordinates`.
    """
    abs_path = Path(language_server.language_server.repository_root_path) / relative_path
    return abs_path.read_text()


def is_diagnostics_test_file(relative_path: str) -> bool:
    normalized_path = relative_path.replace("\\", "/")
    filename = normalized_path.rsplit("/", 1)[-1].lower()
    return filename.startswith(("diagnosticssample.", "diagnostics_sample."))


def document_symbol_names(language_server: SolidLanguageServer, relative_path: str) -> list[str]:
    """All symbol names in a file's document-symbol tree, including children."""
    symbols = language_server.request_document_symbols(relative_path).get_all_symbols_and_roots()
    symbol_list = symbols[0] if symbols and isinstance(symbols[0], list) else symbols
    names: list[str] = []

    def _collect(syms) -> None:
        for sym in syms:
            names.append(sym.get("name"))
            _collect(sym.get("children", []) or [])

    _collect(symbol_list)
    return names


def find_document_symbol(language_server: SolidLanguageServer, relative_path: str, name: str) -> UnifiedSymbolInformation:
    """The first symbol called ``name`` in a file's document-symbol tree; fails the test if absent."""
    symbols = language_server.request_document_symbols(relative_path).get_all_symbols_and_roots()
    symbol_list = symbols[0] if symbols and isinstance(symbols[0], list) else symbols

    def _search(syms):
        for sym in syms:
            if sym.get("name") == name:
                return sym
            found = _search(sym.get("children", []) or [])
            if found is not None:
                return found
        return None

    result = _search(symbol_list)
    assert result is not None, f"Symbol '{name}' not found in {relative_path}"
    return result


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
