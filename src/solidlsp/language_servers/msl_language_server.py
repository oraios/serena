"""
Provides mSL (mIRC Scripting Language) specific instantiation of the LanguageServer class.
Uses a custom Python-based LSP server (pygls) for parsing .mrc files.
"""

import logging
import os
import pathlib
import subprocess
import sys
import threading

from solidlsp.ls import (
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class MslLanguageServer(SolidLanguageServer):
    """
    Provides mSL (mIRC Scripting Language) specific instantiation of the LanguageServer class.
    Uses a Python-based LSP server for parsing .mrc files (aliases, events, menus, dialogs).
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates an MslLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            "msl",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """Setup runtime dependencies for mSL Language Server and return the path to the venv python."""
            python_path = sys.executable
            assert python_path, "Python executable not found"

            msl_ls_dir = os.path.join(self._ls_resources_dir, "msl-lsp")
            venv_dir = os.path.join(msl_ls_dir, "venv")
            msl_lsp_script = os.path.join(msl_ls_dir, "msl_lsp.py")
            requirements_file = os.path.join(msl_ls_dir, "requirements.txt")

            if os.name == "nt":
                venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
            else:
                venv_python = os.path.join(venv_dir, "bin", "python")

            if not os.path.exists(venv_python):
                log.info(f"mSL Language Server not found at {msl_ls_dir}. Setting up...")
                os.makedirs(msl_ls_dir, exist_ok=True)
                MslLanguageServer._create_msl_lsp_files(msl_ls_dir)

                log.info("Creating virtual environment for mSL LSP...")
                subprocess.run([python_path, "-m", "venv", venv_dir], check=True)

                log.info("Installing mSL LSP dependencies...")
                pip_path = os.path.join(venv_dir, "Scripts" if os.name == "nt" else "bin", "pip")
                subprocess.run([pip_path, "install", "-r", requirements_file], check=True)
                log.info("mSL language server setup complete")

            if not os.path.exists(msl_lsp_script):
                raise FileNotFoundError(f"mSL LSP script not found at {msl_lsp_script}, something went wrong with the installation.")

            return venv_python

        def _create_launch_command(self, core_path: str) -> list[str]:
            msl_ls_dir = os.path.join(self._ls_resources_dir, "msl-lsp")
            msl_lsp_script = os.path.join(msl_ls_dir, "msl_lsp.py")
            return [core_path, msl_lsp_script]

    @staticmethod
    def _create_msl_lsp_files(msl_ls_dir: str) -> None:
        """Create the mSL LSP server files in the given directory."""
        requirements_content = "pygls>=2.0.0\nlsprotocol>=2023.0.0\n"
        with open(os.path.join(msl_ls_dir, "requirements.txt"), "w") as f:
            f.write(requirements_content)

        with open(os.path.join(msl_ls_dir, "msl_lsp.py"), "w") as f:
            f.write(_MSL_LSP_SCRIPT)

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """Returns the initialize params for the mSL Language Server."""
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                },
                "workspace": {
                    "workspaceFolders": True,
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [{"uri": root_uri, "name": os.path.basename(repository_absolute_path)}],
        }
        return initialize_params  # type: ignore

    def _start_server(self) -> None:
        """Starts the mSL Language Server."""

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")
            self.server_ready.set()

        def do_nothing(params: dict) -> None:
            pass

        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting mSL server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request to mSL LSP server")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response: {init_response}")

        self.server.notify.initialized({})

        # Wait briefly for server readiness
        if not self.server_ready.wait(timeout=2.0):
            log.info("Timeout waiting for mSL server ready signal, proceeding anyway")
            self.server_ready.set()

        log.info("mSL server initialization complete")


# ---------------------------------------------------------------------------
# Embedded mSL LSP script (written to disk on first run)
# ---------------------------------------------------------------------------

_MSL_LSP_SCRIPT = r'''#!/usr/bin/env python3
"""mSL (mIRC Scripting Language) Language Server

A minimal LSP implementation for mIRC scripting language (.mrc files).
Provides document symbols (aliases, events, menus, dialogs) for Serena integration.

Dependencies: pygls >= 2.0.0, lsprotocol >= 2023.0.0
"""

import re
import logging
from typing import List

from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

server = LanguageServer("msl-lsp", "0.1.0")

# mSL top-level construct patterns
ALIAS_PATTERN = re.compile(
    r'^[ \t]*alias\s+(?:-l\s+)?([a-zA-Z_][\w.]*)\s*(?:\{|$)',
    re.MULTILINE | re.IGNORECASE,
)
EVENT_PATTERN = re.compile(
    r'^[ \t]*on\s+(\*|\d+):(\w+):([^{]*?)(?:\{|$)',
    re.MULTILINE | re.IGNORECASE,
)
RAW_EVENT_PATTERN = re.compile(
    r'^[ \t]*raw\s+(\d+):([^{]*?)(?:\{|$)',
    re.MULTILINE | re.IGNORECASE,
)
MENU_PATTERN = re.compile(
    r'^[ \t]*menu\s+([^\s{]+)\s*\{',
    re.MULTILINE | re.IGNORECASE,
)
DIALOG_PATTERN = re.compile(
    r'^[ \t]*dialog\s+(-l\s+)?([a-zA-Z_][\w]*)\s*\{',
    re.MULTILINE | re.IGNORECASE,
)
CTCP_PATTERN = re.compile(
    r'^[ \t]*ctcp\s+(\*|\d+):(\w+):([^{]*?)(?:\{|$)',
    re.MULTILINE | re.IGNORECASE,
)


def get_line_col(text: str, pos: int) -> tuple[int, int]:
    lines = text[:pos].split("\n")
    return len(lines) - 1, len(lines[-1]) if lines else 0


def find_block_end(text: str, start: int) -> int:
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
    sl, sc = get_line_col(text, match_start)
    bs = text.find("{", match_start)
    if bs != -1:
        el, ec = get_line_col(text, find_block_end(text, bs))
    else:
        el, ec = get_line_col(text, match_end)
    return lsp.DocumentSymbol(
        name=name,
        kind=kind,
        range=lsp.Range(lsp.Position(sl, 0), lsp.Position(el, ec + 1)),
        selection_range=lsp.Range(
            lsp.Position(sl, sc), lsp.Position(sl, sc + len(match_text))
        ),
        detail=detail,
    )


def parse_symbols(text: str) -> List[lsp.DocumentSymbol]:
    symbols: list[lsp.DocumentSymbol] = []

    for m in ALIAS_PATTERN.finditer(text):
        symbols.append(
            _make_symbol(m.group(1), lsp.SymbolKind.Function, "alias", text, m.start(), m.end(), m.group(0))
        )

    for m in EVENT_PATTERN.finditer(text):
        pat = m.group(3).strip().rstrip(":")
        name = f"on {m.group(1)}:{m.group(2)}" + (f":{pat}" if pat else "")
        symbols.append(
            _make_symbol(name, lsp.SymbolKind.Event, f"event:{m.group(2)}", text, m.start(), m.end(), m.group(0))
        )

    for m in RAW_EVENT_PATTERN.finditer(text):
        pat = m.group(2).strip().rstrip(":")
        name = f"raw {m.group(1)}" + (f":{pat}" if pat else "")
        symbols.append(
            _make_symbol(name, lsp.SymbolKind.Event, "raw event", text, m.start(), m.end(), m.group(0))
        )

    for m in MENU_PATTERN.finditer(text):
        symbols.append(
            _make_symbol(f"menu {m.group(1)}", lsp.SymbolKind.Module, "menu", text, m.start(), m.end(), m.group(0))
        )

    for m in DIALOG_PATTERN.finditer(text):
        symbols.append(
            _make_symbol(f"dialog {m.group(2)}", lsp.SymbolKind.Class, "dialog", text, m.start(), m.end(), m.group(0))
        )

    for m in CTCP_PATTERN.finditer(text):
        pat = m.group(3).strip().rstrip(":")
        name = f"ctcp {m.group(1)}:{m.group(2)}" + (f":{pat}" if pat else "")
        symbols.append(
            _make_symbol(name, lsp.SymbolKind.Event, "ctcp event", text, m.start(), m.end(), m.group(0))
        )

    symbols.sort(key=lambda s: s.range.start.line)
    return symbols


@server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def did_open(params: lsp.DidOpenTextDocumentParams):
    pass


@server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
def did_change(params: lsp.DidChangeTextDocumentParams):
    pass


@server.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
def did_close(params: lsp.DidCloseTextDocumentParams):
    pass


@server.feature(lsp.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbol(params: lsp.DocumentSymbolParams) -> List[lsp.DocumentSymbol]:
    try:
        doc = server.workspace.get_text_document(params.text_document.uri)
        return parse_symbols(doc.source)
    except Exception as e:
        logger.error(f"Error: {e}")
        return []


@server.feature(lsp.WORKSPACE_SYMBOL)
def workspace_symbol(params: lsp.WorkspaceSymbolParams) -> List[lsp.SymbolInformation]:
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
'''
