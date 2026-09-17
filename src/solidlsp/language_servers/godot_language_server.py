"""GDScript language server for Godot Engine projects.

Connects to an already-running Godot editor via TCP on port 6008.
Both Godot 3 and Godot 4 (tested through 4.6.x) use this port.

The editor must be open with its built-in language server enabled (default).
"""
# SPDX-License-Identifier: MIT

import logging
import os
from collections.abc import Callable
from typing import Any

from solidlsp.ls import DocumentSymbols, LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_process import LanguageServerInterface, TCPConnectionInfo, TCPLanguageServer
from solidlsp.lsp_protocol_handler.server import StringDict
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# Maps config_version in project.godot to the Godot major version
_CONFIG_VERSION_TO_GODOT_MAJOR: dict[int, int] = {4: 3, 5: 4}

DEFAULT_GODOT_LS_PORT = 6008
DEFAULT_GODOT_REQUEST_TIMEOUT = 30.0


class GodotLanguageServer(SolidLanguageServer):
    """GDScript language server that connects to a running Godot editor.

    Both Godot 3 and Godot 4 expose an LSP server on TCP port 6008.
    The Godot editor must already be running — this class connects to it
    rather than launching it.

    ls_specific_settings for ``gdscript``:
        - ``port`` (int): TCP port the Godot editor's LSP listens on (default: 6008).
        - ``request_timeout`` (float): seconds to wait for an LSP response (default: 30.0).
    """

    # Bump whenever _fix_range_end/_fix_symbol_ranges below changes, so a stale cached
    # high-level result (from before this fix existed) is not served back to callers.
    _DOCUMENT_SYMBOLS_CACHE_VERSION = 2

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings) -> None:
        self._godot_version = self._detect_godot_version(repository_root_path)
        if self._godot_version is not None:
            log.info("Detected Godot version %d for project at %s", self._godot_version, repository_root_path)
        else:
            log.warning("Could not detect Godot version for project at %s", repository_root_path)

        self._configured_request_timeout: float | None = None

        # Dummy ProcessLaunchInfo — _create_language_server_interface() ignores it
        super().__init__(config, repository_root_path, None, "gdscript", solidlsp_settings)

    def set_request_timeout(self, timeout: float | None) -> None:
        """Cap the timeout at the value configured in ls_specific_settings, if set."""
        if timeout is not None and self._configured_request_timeout is not None:
            timeout = min(timeout, self._configured_request_timeout)
        super().set_request_timeout(timeout)

    @staticmethod
    def _detect_godot_version(repo_path: str) -> int | None:
        """Read project.godot to determine the major Godot version.

        Returns None if detection fails or the config_version is unrecognized.
        """
        project_file = os.path.join(repo_path, "project.godot")
        try:
            with open(project_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("config_version="):
                        config_version = int(line.split("=", 1)[1])
                        return _CONFIG_VERSION_TO_GODOT_MAJOR.get(config_version)
        except (FileNotFoundError, ValueError, OSError):
            pass
        return None

    def _create_language_server_interface(self, logging_fn: Callable[[str, str, StringDict | str], None] | None) -> LanguageServerInterface:
        settings = self._custom_settings or {}
        port = settings.get("port", DEFAULT_GODOT_LS_PORT)
        request_timeout = settings.get("request_timeout", DEFAULT_GODOT_REQUEST_TIMEOUT)
        self._configured_request_timeout = settings.get("request_timeout")
        self._conn_info = TCPConnectionInfo(host="127.0.0.1", port=port)
        return TCPLanguageServer(
            connection_info=self._conn_info,
            ls_id=self.ls_id,
            determine_log_level=self._determine_log_level,
            logger=logging_fn,
            request_timeout=request_timeout,
        )

    def _create_base_initialize_params(self) -> dict:
        params = {
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "declaration": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {"snippetSupport": True},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                },
            },
        }
        return params

    def _start_server(self) -> None:
        def do_nothing(params: dict) -> None:
            return

        # Godot sends this notification immediately on connect to report the open project path.
        self.server.on_notification("gdscript_client/changeWorkspace", do_nothing)
        # Godot-specific capability advertisement (not standard LSP).
        self.server.on_notification("gdscript/capabilities", do_nothing)
        self.server.on_notification("window/logMessage", lambda msg: log.info("LSP: window/logMessage: %s", msg))
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_request("client/registerCapability", lambda params: None)

        log.info("Connecting to Godot LSP at %s:%d", self._conn_info.host, self._conn_info.port)
        self.server.start()

        initialize_params = self._create_initialize_params()
        log.info("Sending LSP initialize request to Godot")
        self.server.send.initialize(initialize_params)
        self.server.notify.initialized({})
        log.info("Godot LSP initialized")

    def _build_document_symbols_from_raw_symbols(self, relative_file_path: str, file_buffer: LSPFileBuffer) -> DocumentSymbols:
        """Override to correct a Godot GDScript parser off-by-one in reported end columns.

        See :meth:`_fix_range_end` for the mechanism (oraios/serena#1974). Applied here, on the
        converted high-level symbols, rather than in ``_request_raw_document_symbols`` or in the
        generic ``TextUtils.get_index_from_line_col`` (used by every language server): the
        overshoot is specific to Godot's own parser, not a property of LSP position math in
        general, and post-processing at this level only needs to invalidate the high-level
        symbol cache, not the (expensive to rebuild) raw one the language server itself answers.

        TODO: gate this behind a Godot version check once the upstream parser bug is fixed
        (tracked at https://github.com/godotengine/godot/issues, not yet filed there).
        """
        document_symbols = super()._build_document_symbols_from_raw_symbols(relative_file_path, file_buffer)
        lines = file_buffer.split_lines()
        for root_symbol in document_symbols.root_symbols:
            self._fix_symbol_ranges(root_symbol, lines)
        return document_symbols

    def _document_symbols_cache_fingerprint(self) -> int:
        return self._DOCUMENT_SYMBOLS_CACHE_VERSION

    @staticmethod
    def _fix_range_end(rng: Any, lines: list[str]) -> None:
        """Correct a Godot GDScript parser off-by-one in an LSP ``Range``'s end position, in place.

        Godot's ``gdscript_parser.cpp`` closes a node's range using the *next* lookahead token
        instead of the *last consumed* one. When that lookahead is a synthesized NEWLINE token,
        ``gdscript_tokenizer.cpp``'s ``newline()`` sets the token's own ``end_column`` to the
        column reached *after* consuming the newline character, one past where a real content
        token would end. Stacked on top of the usual one-past-the-end range convention, a symbol
        whose body ends at that line reports an end column two past its last character instead of
        one past it (oraios/serena#1974).

        Only that exact, measured overshoot is corrected; a larger one is not this bug and is left
        alone rather than guessed at.
        """
        end = rng.get("end")
        if end is None:
            return
        end_line, end_char = end.get("line"), end.get("character")
        if end_line is None or end_char is None or not (0 <= end_line < len(lines)):
            return
        # The correct one-past-the-end column for this line is len(lines[end_line]).
        correct_end_char = len(lines[end_line])
        if end_char == correct_end_char + 1:
            end["character"] = correct_end_char

    @staticmethod
    def _fix_symbol_ranges(symbol: Any, lines: list[str]) -> None:
        """Recursively apply range corrections to a (raw or unified) symbol and its children."""
        location = symbol.get("location")
        if location is not None:
            GodotLanguageServer._fix_range_end(location.get("range", {}), lines)
            GodotLanguageServer._clamp_trailing_blank_lines(location.get("range", {}), lines)
        symbol_range = symbol.get("range")
        if symbol_range is not None:
            GodotLanguageServer._fix_range_end(symbol_range, lines)
            GodotLanguageServer._clamp_trailing_blank_lines(symbol_range, lines)
        selection_range = symbol.get("selectionRange")
        if selection_range is not None:
            GodotLanguageServer._fix_range_end(selection_range, lines)
        for child in symbol.get("children") or []:
            GodotLanguageServer._fix_symbol_ranges(child, lines)

    @staticmethod
    def _clamp_trailing_blank_lines(rng: Any, lines: list[str]) -> None:
        """Clamp a symbol range so its end does not include trailing blank lines.

        Godot's parser often closes a function's range at the start of the next top-level
        construct (or on the blank separator line). ``replace_symbol_body`` then deletes
        inter-symbol trivia together with the body (oraios/serena#1952). Walk the end
        position back to the last non-blank line of the symbol itself; never move past
        the range start.
        """
        end = rng.get("end")
        if end is None:
            return
        end_line = end.get("line")
        if end_line is None:
            return
        start = rng.get("start") or {}
        start_line = start.get("line", 0)
        line = end_line
        # an end at column 0 means the end_line itself is not part of the body content
        if end.get("character") == 0 and line > start_line:
            line -= 1
        while line > start_line and (line >= len(lines) or not lines[line].strip()):
            line -= 1
        if line < start_line or not (0 <= line < len(lines)):
            return
        if line != end_line or end.get("character") != len(lines[line]):
            end["line"] = line
            end["character"] = len(lines[line])
