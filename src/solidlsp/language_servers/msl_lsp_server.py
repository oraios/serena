"""mSL (mIRC Scripting Language) Language Server.

A minimal LSP implementation for mIRC scripting language (.mrc files).
Provides document symbols, hover, references, go-to-definition, and workspace symbols
for aliases, events, menus, dialogs, and CTCP handlers.

Launched as a subprocess by MslLanguageServer. Communicates via stdio.
"""

import logging
import os
import pathlib
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


def _get_workspace_roots() -> list[str]:
    """Get workspace root paths from the server's workspace object.

    After initialization, pygls populates ``server.workspace`` with the
    root URI/path and any workspace folders sent by the client.
    """
    from pygls.uris import to_fs_path

    roots: list[str] = []
    try:
        ws = server.workspace
    except (RuntimeError, AttributeError):
        return roots

    # workspace.folders is a dict of {uri_string: WorkspaceFolder}
    if hasattr(ws, "folders") and ws.folders:
        for folder_uri in ws.folders:
            fs_path = to_fs_path(folder_uri)
            if fs_path:
                # resolve() normalizes drive letter casing on Windows
                fs_path = str(pathlib.Path(fs_path).resolve())
                if os.path.isdir(fs_path):
                    roots.append(fs_path)

    # Fall back to root_path
    if not roots and hasattr(ws, "root_path") and ws.root_path:
        root = str(pathlib.Path(ws.root_path).resolve())
        if os.path.isdir(root):
            roots.append(root)

    return roots


def _path_to_uri(path: str) -> str:
    """Convert a filesystem path to a file URI."""
    return pathlib.Path(path).as_uri()


def _get_all_mrc_files() -> list[tuple[str, str, str]]:
    """Scan workspace roots for all .mrc files.

    Returns list of (uri, file_path, source_text) tuples.
    Prefers content from already-opened documents over disk reads.
    """
    results: list[tuple[str, str, str]] = []
    seen_paths: set[str] = set()

    # First, include all files currently open in the workspace
    try:
        for uri, doc in server.workspace.text_documents.items():
            if uri.endswith(".mrc"):
                # Resolve the filesystem path from the URI
                from pygls.uris import to_fs_path

                file_path = to_fs_path(uri) or uri
                norm = os.path.normcase(os.path.normpath(file_path))
                seen_paths.add(norm)
                results.append((uri, file_path, doc.source))
    except (RuntimeError, AttributeError):
        pass

    # Then scan workspace roots for any .mrc files not yet opened
    for root in _get_workspace_roots():
        for dirpath, _dirnames, filenames in os.walk(root):
            for fname in filenames:
                if not fname.endswith(".mrc"):
                    continue
                full_path = os.path.join(dirpath, fname)
                norm = os.path.normcase(os.path.normpath(full_path))
                if norm in seen_paths:
                    continue
                seen_paths.add(norm)
                try:
                    with open(full_path, encoding="utf-8", errors="replace") as f:
                        source = f.read()
                    uri = _path_to_uri(full_path)
                    results.append((uri, full_path, source))
                except OSError:
                    pass

    return results


def _find_symbol_at_position(text: str, line: int, character: int) -> str | None:
    """Find the symbol name at the given position in the text."""
    lines = text.split("\n")
    if line >= len(lines):
        return None
    line_text = lines[line]

    # Check if position is within an alias definition
    for m in ALIAS_PATTERN.finditer(text):
        sl, _ = _get_line_col(text, m.start())
        if sl == line:
            return m.group(1)

    # Check if position is within an event definition
    for m in EVENT_PATTERN.finditer(text):
        sl, _ = _get_line_col(text, m.start())
        if sl == line:
            pat = m.group(3).strip().rstrip(":")
            return f"on {m.group(1)}:{m.group(2)}" + (f":{pat}" if pat else "")

    # Check if position is within a raw event
    for m in RAW_EVENT_PATTERN.finditer(text):
        sl, _ = _get_line_col(text, m.start())
        if sl == line:
            pat = m.group(2).strip().rstrip(":")
            return f"raw {m.group(1)}" + (f":{pat}" if pat else "")

    # Check if position is within a menu
    for m in MENU_PATTERN.finditer(text):
        sl, _ = _get_line_col(text, m.start())
        if sl == line:
            return f"menu {m.group(1)}"

    # Check if position is within a dialog
    for m in DIALOG_PATTERN.finditer(text):
        sl, _ = _get_line_col(text, m.start())
        if sl == line:
            return f"dialog {m.group(2)}"

    # Check if position is within a CTCP handler
    for m in CTCP_PATTERN.finditer(text):
        sl, _ = _get_line_col(text, m.start())
        if sl == line:
            return f"ctcp {m.group(1)}:{m.group(2)}"

    # Fall back: extract word at position (for alias call sites)
    if character < len(line_text):
        pos = character
        # Skip leading $ if cursor is on it (e.g., $format.coins)
        if pos < len(line_text) and line_text[pos] == "$":
            pos += 1
        start = pos
        while start > 0 and (line_text[start - 1].isalnum() or line_text[start - 1] in "_."):
            start -= 1
        end = pos
        while end < len(line_text) and (line_text[end].isalnum() or line_text[end] in "_."):
            end += 1
        word = line_text[start:end]
        if word:
            return word
    return None


def _get_symbol_detail(text: str, symbol_name: str) -> str | None:
    """Get detail/documentation text for a symbol by finding its definition and extracting context."""
    for sym in parse_symbols(text):
        if sym.name == symbol_name:
            # Extract the definition line and a few lines of body for hover
            text_lines = text.split("\n")
            start_line = sym.range.start.line
            end_line = min(sym.range.end.line, start_line + 5)
            snippet_lines = text_lines[start_line : end_line + 1]
            snippet = "\n".join(snippet_lines)
            return f"```msl\n{snippet}\n```\n\n**Kind**: {sym.detail}"
    return None


def _build_call_pattern(alias_name: str) -> re.Pattern[str]:
    """Build a regex that matches calls to an alias (both as command and as $identifier)."""
    escaped = re.escape(alias_name)
    return re.compile(
        rf"(?<![.\w])(?:\$)?{escaped}(?![.\w])",
        re.MULTILINE | re.IGNORECASE,
    )


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


@server.feature(lsp.TEXT_DOCUMENT_HOVER)
def hover(params: lsp.HoverParams) -> lsp.Hover | None:
    """Return hover information for the symbol at the given position."""
    try:
        doc = server.workspace.get_text_document(params.text_document.uri)
        symbol_name = _find_symbol_at_position(doc.source, params.position.line, params.position.character)
        if not symbol_name:
            return None

        # Search all files for the symbol definition to get its detail
        for _uri, _path, source in _get_all_mrc_files():
            detail = _get_symbol_detail(source, symbol_name)
            if detail:
                return lsp.Hover(
                    contents=lsp.MarkupContent(kind=lsp.MarkupKind.Markdown, value=detail),
                )

        # Fallback: return the symbol name itself
        return lsp.Hover(
            contents=lsp.MarkupContent(kind=lsp.MarkupKind.Markdown, value=f"**{symbol_name}**"),
        )
    except Exception as e:
        logger.error(f"Error in hover: {e}")
        return None


@server.feature(lsp.TEXT_DOCUMENT_REFERENCES)
def references(params: lsp.ReferenceParams) -> list[lsp.Location]:
    """Find all references to the symbol at the given position across the workspace."""
    try:
        doc = server.workspace.get_text_document(params.text_document.uri)
        symbol_name = _find_symbol_at_position(
            doc.source,
            params.position.line,
            params.position.character,
        )
        if not symbol_name:
            return []

        results: list[lsp.Location] = []

        # For alias symbols, search for call sites across all .mrc files
        # For events/menus/dialogs, only return the definition location
        is_alias = not any(symbol_name.startswith(prefix) for prefix in ("on ", "raw ", "menu ", "dialog ", "ctcp "))

        for uri, _path, source in _get_all_mrc_files():
            if is_alias:
                call_pattern = _build_call_pattern(symbol_name)
                for m in call_pattern.finditer(source):
                    ref_line, ref_col = _get_line_col(source, m.start())
                    results.append(
                        lsp.Location(
                            uri=uri,
                            range=lsp.Range(
                                lsp.Position(ref_line, ref_col),
                                lsp.Position(ref_line, ref_col + len(m.group(0))),
                            ),
                        )
                    )
            else:
                # For non-alias symbols, find the definition
                for sym in parse_symbols(source):
                    if sym.name == symbol_name:
                        results.append(lsp.Location(uri=uri, range=sym.range))

        return results
    except Exception as e:
        logger.error(f"Error finding references: {e}")
        return []


@server.feature(lsp.TEXT_DOCUMENT_DEFINITION)
def definition(params: lsp.DefinitionParams) -> list[lsp.Location]:
    """Go to definition of the symbol at the given position."""
    try:
        doc = server.workspace.get_text_document(params.text_document.uri)
        symbol_name = _find_symbol_at_position(
            doc.source,
            params.position.line,
            params.position.character,
        )
        if not symbol_name:
            return []

        results: list[lsp.Location] = []
        for uri, _path, source in _get_all_mrc_files():
            for sym in parse_symbols(source):
                if sym.name == symbol_name:
                    results.append(lsp.Location(uri=uri, range=sym.selection_range))
        return results
    except Exception as e:
        logger.error(f"Error finding definition: {e}")
        return []


@server.feature(lsp.WORKSPACE_SYMBOL)
def workspace_symbol(params: lsp.WorkspaceSymbolParams) -> list[lsp.SymbolInformation]:
    """Search for symbols across the workspace."""
    query = params.query.lower()
    results = []
    for uri, _path, source in _get_all_mrc_files():
        for sym in parse_symbols(source):
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
