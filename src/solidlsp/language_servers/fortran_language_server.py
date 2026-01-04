"""
Fortran Language Server implementation using fortls.
"""

import logging
import os
import pathlib
import re
import shutil
import threading

from overrides import override

from solidlsp import ls_types
from solidlsp.ls import DocumentSymbols, LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class FortranLanguageServer(SolidLanguageServer):
    """Fortran Language Server implementation using fortls."""

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 3.0  # fortls needs time for workspace indexing

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For Fortran projects, ignore common build directories
        return super().is_ignored_dirname(dirname) or dirname in [
            "build",
            "Build",
            "BUILD",
            "bin",
            "lib",
            "mod",  # Module files directory
            "obj",  # Object files directory
            ".cmake",
            "CMakeFiles",
        ]

    def _fix_fortls_selection_range(
        self, symbol: ls_types.UnifiedSymbolInformation, file_content: str
    ) -> ls_types.UnifiedSymbolInformation:
        """
        Fix fortls's incorrect selectionRange that points to line start instead of identifier name.

        fortls bug: selectionRange.start.character is 0 (line start) but should point to the
        function/subroutine/module/program name position. This breaks MCP server features that
        rely on the exact identifier position for finding references.

        Args:
            symbol: The symbol with potentially incorrect selectionRange
            file_content: Full file content to parse the line

        Returns:
            Symbol with corrected selectionRange pointing to the identifier name

        """
        if "selectionRange" not in symbol:
            return symbol

        sel_range = symbol["selectionRange"]
        start_line = sel_range["start"]["line"]
        start_char = sel_range["start"]["character"]

        # Split file content into lines
        lines = file_content.split("\n")
        if start_line >= len(lines):
            return symbol

        line = lines[start_line]

        # Fortran keywords that define named constructs
        # Match patterns:
        # Standard keywords: <keyword> <whitespace> <identifier_name>
        #   "    function add_numbers(a, b) result(sum)"  -> keyword="function", name="add_numbers"
        #   "subroutine print_result(value)"             -> keyword="subroutine", name="print_result"
        #   "module math_utils"                          -> keyword="module", name="math_utils"
        #   "program test_program"                       -> keyword="program", name="test_program"
        #   "interface distance"                         -> keyword="interface", name="distance"
        #
        # Type definitions (can have :: syntax):
        #   "type point"                                 -> keyword="type", name="point"
        #   "type :: point"                              -> keyword="type", name="point"
        #   "type, extends(base) :: derived"             -> keyword="type", name="derived"
        #
        # Submodules (have parent module in parentheses):
        #   "submodule (parent_mod) child_mod"           -> keyword="submodule", name="child_mod"

        # Try type pattern first (has complex syntax with optional comma and ::)
        type_pattern = r"^\s*type\s*(?:,.*?)?\s*(?:::)?\s*([a-zA-Z_]\w*)"
        match = re.match(type_pattern, line, re.IGNORECASE)

        if match:
            # For type pattern, identifier is in group 1
            identifier_name = match.group(1)
            identifier_start = match.start(1)
        else:
            # Try standard keywords pattern
            standard_pattern = r"^\s*(function|subroutine|module|program|interface)\s+([a-zA-Z_]\w*)"
            match = re.match(standard_pattern, line, re.IGNORECASE)

            if not match:
                # Try submodule pattern
                submodule_pattern = r"^\s*submodule\s*\([^)]+\)\s+([a-zA-Z_]\w*)"
                match = re.match(submodule_pattern, line, re.IGNORECASE)

                if match:
                    identifier_name = match.group(1)
                    identifier_start = match.start(1)
            else:
                identifier_name = match.group(2)
                identifier_start = match.start(2)

        if match:
            # Create corrected selectionRange
            new_sel_range = {
                "start": {"line": start_line, "character": identifier_start},
                "end": {"line": start_line, "character": identifier_start + len(identifier_name)},
            }

            # Create modified symbol with corrected selectionRange
            corrected_symbol = symbol.copy()
            corrected_symbol["selectionRange"] = new_sel_range  # type: ignore[typeddict-item]

            log.debug(f"Fixed fortls selectionRange for {identifier_name}: char {start_char} -> {identifier_start}")

            return corrected_symbol

        # If no match, return symbol unchanged (e.g., for variables, which don't have this pattern)
        return symbol

    @override
    def request_document_symbols(self, relative_file_path: str, file_buffer: LSPFileBuffer | None = None) -> DocumentSymbols:
        # Override to fix fortls's incorrect selectionRange bug.
        #
        # fortls returns selectionRange pointing to line start (character 0) instead of the
        # identifier name position. This breaks MCP server features that rely on exact positions.
        #
        # This override:
        # 1. Gets symbols from fortls via parent implementation
        # 2. Parses each symbol's line to find the correct identifier position
        # 3. Fixes selectionRange for all symbols recursively
        # 4. Returns corrected symbols

        # Get symbols from fortls (with incorrect selectionRange)
        document_symbols = super().request_document_symbols(relative_file_path, file_buffer=file_buffer)

        # Get file content for parsing
        with self.open_file(relative_file_path) as file_data:
            file_content = file_data.contents

        # Fix selectionRange recursively for all symbols
        def fix_symbol_and_children(symbol: ls_types.UnifiedSymbolInformation) -> ls_types.UnifiedSymbolInformation:
            # Fix this symbol's selectionRange
            fixed = self._fix_fortls_selection_range(symbol, file_content)

            # Fix children recursively
            if fixed.get("children"):
                fixed["children"] = [fix_symbol_and_children(child) for child in fixed["children"]]

            return fixed

        # Apply fix to all symbols
        fixed_root_symbols = [fix_symbol_and_children(sym) for sym in document_symbols.root_symbols]

        return DocumentSymbols(fixed_root_symbols)

    @staticmethod
    def _check_fortls_installation() -> str:
        """Check if fortls is available."""
        fortls_path = shutil.which("fortls")
        if fortls_path is None:
            raise RuntimeError("fortls is not installed or not in PATH.\nInstall it with: pip install fortls")
        return fortls_path

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        # Check fortls installation
        fortls_path = self._check_fortls_installation()

        # Command to start fortls language server
        # fortls uses stdio for LSP communication by default
        fortls_cmd = f"{fortls_path}"

        super().__init__(
            config, repository_root_path, ProcessLaunchInfo(cmd=fortls_cmd, cwd=repository_root_path), "fortran", solidlsp_settings
        )
        self.server_ready = threading.Event()

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """Initialize params for Fortran Language Server."""
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "deprecatedSupport": True,
                            "preselectSupport": True,
                        },
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "inlayHint": {"dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "formatting": {"dynamicRegistration": True},
                    "rangeFormatting": {"dynamicRegistration": True},
                    "codeAction": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                },
            },
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }
        return initialize_params  # type: ignore[return-value]

    def _start_server(self) -> None:
        """Start Fortran Language Server process."""

        def window_log_message(msg: dict) -> None:
            log.info(f"Fortran LSP: window/logMessage: {msg}")

        def do_nothing(params: dict) -> None:
            return

        def register_capability_handler(params: dict) -> None:
            return

        # Register LSP message handlers
        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", self._handle_publish_diagnostics)

        log.info("Starting Fortran Language Server (fortls) process")
        self.server.start()

        initialize_params = self._get_initialize_params(self.repository_root_path)
        log.info("Sending initialize request to Fortran Language Server")

        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        capabilities = init_response.get("capabilities", {})
        assert "textDocumentSync" in capabilities
        if "completionProvider" in capabilities:
            log.info("Fortran LSP completion provider available")
        if "definitionProvider" in capabilities:
            log.info("Fortran LSP definition provider available")
        if "referencesProvider" in capabilities:
            log.info("Fortran LSP references provider available")
        if "documentSymbolProvider" in capabilities:
            log.info("Fortran LSP document symbol provider available")

        self.server.notify.initialized({})
        self.completions_available.set()

        # Fortran Language Server is ready after initialization
        self.server_ready.set()
        log.info("Fortran Language Server initialization complete")
