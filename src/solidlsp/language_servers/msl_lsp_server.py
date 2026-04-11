"""mSL (mIRC Scripting Language) Language Server.

A minimal LSP implementation for mIRC scripting language (.mrc files).
Provides document symbols (aliases, events, menus, dialogs) for Serena integration.

Launched as a subprocess by MslLanguageServer. Communicates via stdio.
"""

import logging
import re

from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

server = LanguageServer("msl-lsp", "0.1.0")

# mSL top-level construct patterns
ALIAS_PATTERN = re.compile(
    r"^[ \t]*alias\s+(?:-l\s+)?([a-zA-Z_][\w.]*)\s*(?:\{|$)",
    re.MULTILINE | re.IGNORECASE,
)
EVENT_PATTERN = re.compile(
    r"^[ \t]*on\s+(\*|\d+):(\w+):([^{]*?)(?:\{|$)",
    re.MULTILINE | re.IGNORECASE,
)
RAW_EVENT_PATTERN = re.compile(
    r"^[ \t]*raw\s+(\d+):([^{]*?)(?:\{|$)",
    re.MULTILINE | re.IGNORECASE,
)
MENU_PATTERN = re.compile(
    r"^[ \t]*menu\s+([^\s{]+)\s*\{",
    re.MULTILINE | re.IGNORECASE,
)
DIALOG_PATTERN = re.compile(
    r"^[ \t]*dialog\s+(-l\s+)?([a-zA-Z_][\w]*)\s*\{",
    re.MULTILINE | re.IGNORECASE,
)
CTCP_PATTERN = re.compile(
    r"^[ \t]*ctcp\s+(\*|\d+):(\w+):([^{]*?)(?:\{|$)",
    re.MULTILINE | re.IGNORECASE,
)


def _get_line_col(text: str, pos: int) -> tuple[int, int]:
    lines = text[:pos].split("\n")
    return len(lines) - 1, len(lines[-1]) if lines else 0


def _find_block_end(text: str, start: int) -> int:
    count, i = 0, start
    while i < len(text):
        ch = text[i]
        if ch == ";" and count > 0:
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        if ch == "{":
            count += 1
        elif ch == "}":
            count -= 1
            if count == 0:
                return i
        i += 1
    return len(text) - 1


def _make_symbol(
    name: str,
    kind: lsp.SymbolKind,
    detail: str,
    text: str,
    match_start: int,
    match_end: int,
    match_text: str,
) -> lsp.DocumentSymbol:
    sl, sc = _get_line_col(text, match_start)
    bs = text.find("{", match_start)
    if bs != -1:
        el, ec = _get_line_col(text, _find_block_end(text, bs))
    else:
        el, ec = _get_line_col(text, match_end)
    return lsp.DocumentSymbol(
        name=name,
        kind=kind,
        range=lsp.Range(lsp.Position(sl, 0), lsp.Position(el, ec + 1)),
        selection_range=lsp.Range(lsp.Position(sl, sc), lsp.Position(sl, sc + len(match_text))),
        detail=detail,
    )


def parse_symbols(text: str) -> list[lsp.DocumentSymbol]:
    """Parse mSL source code and return document symbols."""
    symbols: list[lsp.DocumentSymbol] = []

    for m in ALIAS_PATTERN.finditer(text):
        symbols.append(_make_symbol(m.group(1), lsp.SymbolKind.Function, "alias", text, m.start(), m.end(), m.group(0)))

    for m in EVENT_PATTERN.finditer(text):
        pat = m.group(3).strip().rstrip(":")
        name = f"on {m.group(1)}:{m.group(2)}" + (f":{pat}" if pat else "")
        symbols.append(_make_symbol(name, lsp.SymbolKind.Event, f"event:{m.group(2)}", text, m.start(), m.end(), m.group(0)))

    for m in RAW_EVENT_PATTERN.finditer(text):
        pat = m.group(2).strip().rstrip(":")
        name = f"raw {m.group(1)}" + (f":{pat}" if pat else "")
        symbols.append(_make_symbol(name, lsp.SymbolKind.Event, "raw event", text, m.start(), m.end(), m.group(0)))

    for m in MENU_PATTERN.finditer(text):
        symbols.append(_make_symbol(f"menu {m.group(1)}", lsp.SymbolKind.Module, "menu", text, m.start(), m.end(), m.group(0)))

    for m in DIALOG_PATTERN.finditer(text):
        symbols.append(_make_symbol(f"dialog {m.group(2)}", lsp.SymbolKind.Class, "dialog", text, m.start(), m.end(), m.group(0)))

    for m in CTCP_PATTERN.finditer(text):
        pat = m.group(3).strip().rstrip(":")
        name = f"ctcp {m.group(1)}:{m.group(2)}" + (f":{pat}" if pat else "")
        symbols.append(_make_symbol(name, lsp.SymbolKind.Event, "ctcp event", text, m.start(), m.end(), m.group(0)))

    symbols.sort(key=lambda s: s.range.start.line)
    return symbols


@server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def did_open(params: lsp.DidOpenTextDocumentParams) -> None:
    pass


@server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
def did_change(params: lsp.DidChangeTextDocumentParams) -> None:
    pass


@server.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
def did_close(params: lsp.DidCloseTextDocumentParams) -> None:
    pass


@server.feature(lsp.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbol(params: lsp.DocumentSymbolParams) -> list[lsp.DocumentSymbol]:
    """Return document symbols for the given document."""
    try:
        doc = server.workspace.get_text_document(params.text_document.uri)
        return parse_symbols(doc.source)
    except Exception as e:
        logger.error(f"Error: {e}")
        return []


@server.feature(lsp.WORKSPACE_SYMBOL)
def workspace_symbol(params: lsp.WorkspaceSymbolParams) -> list[lsp.SymbolInformation]:
    """Search for symbols across the workspace."""
    query = params.query.lower()
    results = []
    for uri, doc in server.workspace.text_documents.items():
        if not uri.endswith(".mrc"):
            continue
        for sym in parse_symbols(doc.source):
            if query in sym.name.lower():
                results.append(
                    lsp.SymbolInformation(
                        name=sym.name,
                        kind=sym.kind,
                        location=lsp.Location(uri=uri, range=sym.range),
                        container_name=sym.detail,
                    )
                )
    return results


if __name__ == "__main__":
    server.start_io()
