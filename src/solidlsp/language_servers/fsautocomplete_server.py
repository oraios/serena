"""
F# Language Server using FsAutoComplete (Ionide's F# LSP server)
"""

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Generator
from typing import Any, Callable, cast

from packaging.version import Version
from overrides import override

from solidlsp import ls_types
from solidlsp.ls import DocumentSymbols, LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import PathUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


def breadth_first_file_scan(
    root_dir: str, ignore_dirname: Callable[[str], bool] | None = None
) -> Generator[str, None, None]:
    """
    Perform a breadth-first scan of files in the given directory.
    Yields file paths in breadth-first order.
    """
    queue = [root_dir]
    while queue:
        current_dir = queue.pop(0)
        try:
            for item in os.listdir(current_dir):
                if item.startswith("."):
                    continue
                if ignore_dirname and ignore_dirname(item):
                    continue
                item_path = os.path.join(current_dir, item)
                if os.path.isdir(item_path):
                    queue.append(item_path)
                elif os.path.isfile(item_path):
                    yield item_path
        except (PermissionError, OSError):
            # Skip directories we can't access
            pass


def find_solution_or_project_file(
    root_dir: str, ignore_dirname: Callable[[str], bool] | None = None
) -> str | None:
    """
    Find the first .sln file in breadth-first order.
    If no .sln file is found, look for a .fsproj file.
    """
    sln_file = None
    fsproj_file = None

    for filename in breadth_first_file_scan(root_dir, ignore_dirname=ignore_dirname):
        if filename.endswith(".sln") and sln_file is None:
            sln_file = filename
        elif filename.endswith(".fsproj") and fsproj_file is None:
            fsproj_file = filename

        # If we found a .sln file, return it immediately
        if sln_file:
            return sln_file

    # If no .sln file was found, return the first .fsproj file
    return fsproj_file


def find_all_project_files(
    root_dir: str, ignore_dirname: Callable[[str], bool] | None = None
) -> list[str]:
    """
    Find all .fsproj files in breadth-first order under the root.
    """
    projects: list[str] = []
    for filename in breadth_first_file_scan(root_dir, ignore_dirname=ignore_dirname):
        if filename.endswith(".fsproj"):
            projects.append(filename)
    return projects


class FsAutoCompleteServer(SolidLanguageServer):
    """
    Provides F# specific instantiation of the LanguageServer class using FsAutoComplete,
    the official F# language server from Ionide.

    FsAutoComplete can be installed via:
        dotnet tool install --global fsautocomplete

    Or it may be available through your package manager.
    """

    @staticmethod
    def _ensure_fsautocomplete_installed() -> str:
        """Ensure FsAutoComplete is available."""
        # Try common locations
        common_paths = [
            shutil.which("fsautocomplete"),
            os.path.expanduser("~/.dotnet/tools/fsautocomplete"),
            os.path.expanduser("~/.local/bin/fsautocomplete"),
            "/usr/local/bin/fsautocomplete",
        ]

        for path in common_paths:
            if path and os.path.isfile(path) and os.access(path, os.X_OK):
                return path

        # If not found, try to check if it's available via dotnet tool
        try:
            result = subprocess.run(
                ["dotnet", "tool", "list", "--global"],
                capture_output=True,
                text=True,
                check=True,
            )
            if "fsautocomplete" in result.stdout.lower():
                # It's installed as a dotnet tool, return the command
                return "fsautocomplete"
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        raise RuntimeError(
            "FsAutoComplete is not installed or not in PATH.\n"
            "Searched locations:\n"
            + "\n".join(f"  - {p}" for p in common_paths if p)
            + "\n"
            "Please install FsAutoComplete via:\n"
            "  - .NET tool: dotnet tool install --global fsautocomplete\n"
            "  - From source: https://github.com/ionide/FsAutoComplete"
        )

    def __init__(
        self,
        config: LanguageServerConfig,
        logger: LanguageServerLogger,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
    ):
        """
        Creates a FsAutoCompleteServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        fsautocomplete_path = self._ensure_fsautocomplete_installed()
        logger.log(f"Using FsAutoComplete at: {fsautocomplete_path}", logging.INFO)

        # Build command for FsAutoComplete
        cmd = [fsautocomplete_path]

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=cmd, cwd=repository_root_path),
            "fsharp",
            solidlsp_settings,
        )

        self.workspace_loaded = threading.Event()
        self.fsac_version: str | None = None

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "bin",
            "obj",
            "packages",
            ".fake",
            ".ionide",
            "paket-files",
        ]

    def _get_initialize_params(self) -> InitializeParams:
        """
        Returns the initialize params for FsAutoComplete.
        """
        root_uri = PathUtils.path_to_uri(self.repository_root_path)
        root_name = os.path.basename(self.repository_root_path)
        return cast(
            InitializeParams,
            {
                "workspaceFolders": [{"uri": root_uri, "name": root_name}],
                "processId": os.getpid(),
                "rootPath": self.repository_root_path,
                "rootUri": root_uri,
                "capabilities": {
                    "window": {
                        "workDoneProgress": True,
                        "showMessage": {
                            "messageActionItem": {"additionalPropertiesSupport": True}
                        },
                        "showDocument": {"support": True},
                    },
                    "workspace": {
                        "applyEdit": True,
                        "workspaceEdit": {"documentChanges": True},
                        "didChangeConfiguration": {"dynamicRegistration": True},
                        "didChangeWatchedFiles": {"dynamicRegistration": True},
                        "symbol": {
                            "dynamicRegistration": True,
                            "symbolKind": {"valueSet": list(range(1, 27))},
                        },
                        "executeCommand": {"dynamicRegistration": True},
                        "configuration": True,
                        "workspaceFolders": True,
                    },
                    "textDocument": {
                        "synchronization": {
                            "dynamicRegistration": True,
                            "willSave": True,
                            "willSaveWaitUntil": True,
                            "didSave": True,
                        },
                        "hover": {
                            "dynamicRegistration": True,
                            "contentFormat": ["markdown", "plaintext"],
                        },
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
                        "signatureHelp": {
                            "dynamicRegistration": True,
                            "signatureInformation": {
                                "documentationFormat": ["markdown", "plaintext"],
                                "parameterInformation": {"labelOffsetSupport": True},
                            },
                        },
                        "definition": {
                            "dynamicRegistration": True,
                            "linkSupport": True,
                        },
                        "references": {"dynamicRegistration": True},
                        "documentHighlight": {"dynamicRegistration": True},
                        "documentSymbol": {
                            "dynamicRegistration": True,
                            "symbolKind": {"valueSet": list(range(1, 27))},
                            "hierarchicalDocumentSymbolSupport": True,
                        },
                        "codeAction": {
                            "dynamicRegistration": True,
                            "codeActionLiteralSupport": {
                                "codeActionKind": {
                                    "valueSet": [
                                        "",
                                        "quickfix",
                                        "refactor",
                                        "refactor.extract",
                                        "refactor.inline",
                                        "refactor.rewrite",
                                        "source",
                                        "source.organizeImports",
                                    ]
                                }
                            },
                        },
                        "formatting": {"dynamicRegistration": True},
                        "rangeFormatting": {"dynamicRegistration": True},
                        "rename": {"dynamicRegistration": True, "prepareSupport": True},
                    },
                },
                "initializationOptions": {
                    "AutomaticWorkspaceInit": True,
                },
            },
        )

    def _start_server(self) -> None:
        """
        Starts the FsAutoComplete language server
        """

        def do_nothing(params: Any) -> None:
            return

        def window_log_message(msg: Any) -> None:
            """Log messages from the language server."""
            message_text = msg.get("message", "")
            level = msg.get("type", 4)  # Default to Log level

            # Map LSP message types to Python logging levels
            level_map = {
                1: logging.ERROR,
                2: logging.WARNING,
                3: logging.INFO,
                4: logging.DEBUG,
            }  # Error  # Warning  # Info  # Log

            self.logger.log(f"LSP: {message_text}", level_map.get(level, logging.DEBUG))

        def handle_workspace_configuration(params: Any) -> list[Any]:
            """Handle workspace/configuration requests from the server."""
            items = params.get("items", [])
            result = []

            for item in items:
                section = item.get("section", "")

                # Provide F# specific configuration
                if section.startswith("FSharp"):
                    # Default F# settings
                    fsharp_config = {
                        "keywordsAutocomplete": True,
                        "ExternalAutocomplete": False,
                        "Linter": True,
                        "UnionCaseStubGeneration": True,
                        "UnionCaseStubGenerationBody": 'failwith "Not Implemented"',
                        "RecordStubGeneration": True,
                        "RecordStubGenerationBody": 'failwith "Not Implemented"',
                        "InterfaceStubGeneration": True,
                        "InterfaceStubGenerationObjectIdentifier": "this",
                        "InterfaceStubGenerationMethodBody": 'failwith "Not Implemented"',
                        "UnusedOpensAnalyzer": True,
                        "UnusedDeclarationsAnalyzer": True,
                        "SimplifyNameAnalyzer": False,
                        "ResolveNamespaces": True,
                        "EnableReferenceCodeLens": True,
                        "UseSdkScripts": True,
                    }
                    result.append(
                        fsharp_config.get(section.replace("FSharp.", ""), None)
                    )
                else:
                    result.append(None)

            return result

        def handle_work_done_progress_create(params: Any) -> None:
            """Handle work done progress create requests."""
            # Just acknowledge the request
            return

        def handle_notify_workspace(params: Any) -> None:
            """
            Handle fsharp/notifyWorkspace notifications.
            These contain JSON-serialized content strings about project loading status.
            """
            try:
                # The 'content' parameter is a JSON string that needs double-deserialization
                content_str = params.get("content", "{}")
                content = json.loads(content_str)

                kind = content.get("Kind")
                if kind == "workspaceLoad":
                    data = content.get("Data", {})
                    status = data.get("Status")
                    if status == "finished":
                        self.logger.log(
                            "FsAutoComplete workspace loading finished", logging.INFO
                        )
                        self.workspace_loaded.set()
            except Exception as e:
                self.logger.log(
                    f"Error parsing fsharp/notifyWorkspace: {e}", logging.WARNING
                )

        # Set up notification and request handlers
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("fsharp/notifyWorkspace", handle_notify_workspace)
        self.server.on_notification("fsharp/notifyWorkspacePeek", do_nothing)
        self.server.on_request(
            "workspace/configuration", handle_workspace_configuration
        )
        self.server.on_request(
            "window/workDoneProgress/create", handle_work_done_progress_create
        )

        self.logger.log("Starting FsAutoComplete language server process", logging.INFO)

        try:
            self.server.start()
        except Exception as e:
            self.logger.log(
                f"Failed to start language server process: {e}", logging.ERROR
            )
            raise SolidLSPException(f"Failed to start F# language server: {e}")

        # Send initialization
        initialize_params = self._get_initialize_params()

        self.logger.log("Sending initialize request to language server", logging.INFO)
        try:
            init_response = self.server.send.initialize(initialize_params)
            self.fsac_version = (
                init_response.get("result", {}).get("serverInfo", {}).get("version")
            )
            if self.fsac_version:
                self.logger.log(
                    f"FsAutoComplete server version: {self.fsac_version}", logging.INFO
                )
            else:
                self.logger.log(
                    "Could not determine FsAutoComplete server version.",
                    logging.WARNING,
                )
            self.logger.log("Received initialize response", logging.DEBUG)
        except Exception as e:
            raise SolidLSPException(
                f"Failed to initialize F# language server for {self.repository_root_path}: {e}"
            ) from e

        # Verify required capabilities
        capabilities = init_response.get("capabilities", {})
        required_capabilities = [
            "textDocumentSync",
            "definitionProvider",
            "referencesProvider",
            "documentSymbolProvider",
        ]
        missing = [cap for cap in required_capabilities if cap not in capabilities]
        if missing:
            self.logger.log(
                f"Warning: Language server is missing some capabilities: {', '.join(missing)}",
                logging.WARNING,
            )

        # Complete initialization
        self.server.notify.initialized({})
        self.completions_available.set()

        # Open solution or project files, mirroring C# behavior
        solution_or_project = find_solution_or_project_file(
            self.repository_root_path, ignore_dirname=self.is_ignored_dirname
        )
        project_files = find_all_project_files(
            self.repository_root_path, ignore_dirname=self.is_ignored_dirname
        )
        if solution_or_project:
            self.logger.log(
                f"Opening solution/project file: {solution_or_project}", logging.INFO
            )
            self.server.notify.send_notification(
                "solution/open",
                {"solution": PathUtils.path_to_uri(solution_or_project)},
            )
        if project_files:
            self.logger.log(f"Opening project files: {project_files}", logging.DEBUG)
            project_uris = [PathUtils.path_to_uri(p) for p in project_files]
            self.server.notify.send_notification(
                "project/open", {"projects": project_uris}
            )

        # Wait for workspace load signal instead of polling
        if not self.workspace_loaded.wait(timeout=10):
            self.logger.log(
                "Timeout waiting for FsAutoComplete workspace load signal. Proceeding anyway.",
                logging.WARNING,
            )

        self.logger.log(
            "FsAutoComplete language server initialized and ready", logging.INFO
        )

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 3

    def request_hover(
        self, relative_file_path: str, line: int, column: int
    ) -> ls_types.Hover | None:
        """
        Retry hover briefly if FsAutoComplete hasn't produced check results yet.
        """
        return self._retry_no_check_results(
            lambda: SolidLanguageServer.request_hover(
                self, relative_file_path, line, column
            )
        )

    def request_definition(
        self, relative_file_path: str, line: int, column: int
    ) -> list[Any] | None:
        """
        Retry definition briefly if FsAutoComplete hasn't produced check results yet.
        """
        return self._retry_no_check_results(
            lambda: SolidLanguageServer.request_definition(
                self, relative_file_path, line, column
            )
        )

    def _retry_no_check_results(
        self, func: Callable[[], Any], attempts: int = 3, delay: float = 0.5
    ) -> Any:
        for attempt in range(attempts):
            try:
                return func()
            except SolidLSPException as e:
                if "No check results found" in str(e) and attempt < attempts - 1:
                    time.sleep(delay)
                    continue
                raise

    @staticmethod
    def _fix_selection_range(
        symbol: ls_types.UnifiedSymbolInformation,
        file_lines: list[str],
        fsac_version: str | None = None,
    ) -> ls_types.UnifiedSymbolInformation:
        """
        FsAutoComplete sometimes anchors ranges on the blank line before a doc comment.
        Nudge the range/selectionRange to the doc comment when present.
        All numbers remain 0-based here; 1-based conversion happens later.
        """

        def is_pre_0_100(version: str | None) -> bool:
            try:
                return version is None or Version(version) < Version("0.100.0")
            except Exception:
                # If parsing fails, err on the side of applying the fix
                return True

        # Only apply the workaround for FsAC versions older than 0.100.0
        if not is_pre_0_100(fsac_version):
            return symbol

        selection = symbol.get("selectionRange")
        rng = symbol.get("range")
        loc_rng = (
            symbol.get("location", {}).get("range") if "location" in symbol else None
        )

        if selection is None:
            return symbol

        start_line = selection["start"]["line"]

        if start_line >= len(file_lines):
            return symbol

        shift = 0
        # Case 1: FSAC anchored to blank line above doc comment
        if (
            start_line + 1 < len(file_lines)
            and file_lines[start_line].strip() == ""
            and file_lines[start_line + 1].lstrip().startswith("///")
        ):
            shift = 1
        # Case 2: FSAC anchored to type line, doc comment directly above
        elif start_line - 1 >= 0 and file_lines[start_line - 1].lstrip().startswith(
            "///"
        ):
            shift = -1

        if shift != 0:

            def apply(target: dict[str, Any] | None) -> None:
                if target:
                    target["start"]["line"] += shift
                    target["end"]["line"] += shift

            apply(selection)
            apply(rng)
            apply(loc_rng)

        # Ensure range/location start aligns with selection (doc comment)
        if rng and selection:
            delta = selection["start"]["line"] - rng["start"]["line"]
            rng["start"]["line"] = selection["start"]["line"]
            rng["end"]["line"] += delta
            if loc_rng:
                loc_rng["start"]["line"] += delta
                loc_rng["end"]["line"] += delta

        # Heuristic: if the very next line after range end is a closing brace or a trailing member, include it.
        if rng:
            next_line_idx = rng["end"]["line"] + 1
            if next_line_idx < len(file_lines):
                stripped = file_lines[next_line_idx].strip()
                if stripped == "}" or stripped.startswith("member "):
                    rng["end"]["line"] += 1
                    if selection:
                        selection["end"]["line"] = max(
                            selection["end"]["line"], rng["end"]["line"]
                        )
                    if loc_rng:
                        loc_rng["end"]["line"] = max(
                            loc_rng["end"]["line"], rng["end"]["line"]
                        )

        return symbol

    @staticmethod
    def _convert_ranges_to_one_based(
        symbols: list[ls_types.UnifiedSymbolInformation],
    ) -> list[ls_types.UnifiedSymbolInformation]:
        """
        Convert all line numbers in range/selectionRange/location to 1-based for external consumers.
        """

        def bump_range(rng: dict[str, Any] | None) -> None:
            if rng is None:
                return
            rng["start"]["line"] += 1
            rng["end"]["line"] += 1

        def recurse(
            sym: ls_types.UnifiedSymbolInformation,
        ) -> ls_types.UnifiedSymbolInformation:
            bump_range(sym.get("range"))
            bump_range(sym.get("selectionRange"))
            if "location" in sym:
                bump_range(sym["location"].get("range"))
            # Align range/location start with selectionRange
            if sym.get("range") and sym.get("selectionRange"):
                r = sym["range"]
                s = sym["selectionRange"]
                delta = s["start"]["line"] - r["start"]["line"]
                r["start"]["line"] = s["start"]["line"]
                r["end"]["line"] += delta
                if "location" in sym and sym["location"].get("range"):
                    sym["location"]["range"]["start"]["line"] += delta
                    sym["location"]["range"]["end"]["line"] += delta
            if sym.get("children"):
                sym["children"] = [recurse(child) for child in sym["children"]]
            return sym

        return [recurse(sym) for sym in symbols]

    @staticmethod
    def _align_ranges_to_selection(
        symbols: list[ls_types.UnifiedSymbolInformation],
    ) -> list[ls_types.UnifiedSymbolInformation]:
        """
        After conversion, ensure range/location start lines are aligned with selectionRange start.
        """

        def recurse(
            sym: ls_types.UnifiedSymbolInformation,
        ) -> ls_types.UnifiedSymbolInformation:
            if sym.get("range") and sym.get("selectionRange"):
                r = sym["range"]
                s = sym["selectionRange"]
                r["start"]["line"] = s["start"]["line"]
                if "location" in sym and sym["location"].get("range"):
                    sym["location"]["range"]["start"]["line"] = s["start"]["line"]
            if sym.get("children"):
                sym["children"] = [recurse(child) for child in sym["children"]]
            return sym

        return [recurse(sym) for sym in symbols]

    def _fix_selection_ranges(
        self, symbols: list[ls_types.UnifiedSymbolInformation], file_lines: list[str]
    ) -> list[ls_types.UnifiedSymbolInformation]:
        fixed: list[ls_types.UnifiedSymbolInformation] = []
        for sym in symbols:
            fixed_sym = self._fix_selection_range(sym, file_lines, self.fsac_version)
            if fixed_sym.get("children"):
                fixed_sym["children"] = self._fix_selection_ranges(
                    fixed_sym["children"], file_lines
                )
            fixed.append(fixed_sym)
        return fixed

    @override
    def request_document_symbols(
        self, relative_file_path: str, file_buffer: LSPFileBuffer | None = None
    ) -> DocumentSymbols:
        # Clear caches for this file to ensure fresh post-processing (ranges depend on FsAC quirks).
        self._raw_document_symbols_cache.pop(relative_file_path, None)
        self._document_symbols_cache.pop(relative_file_path, None)
        # First get the symbols from the base implementation
        document_symbols = super().request_document_symbols(
            relative_file_path, file_buffer=file_buffer
        )

        # Load file content for aligning selection ranges
        with self.open_file(relative_file_path) as file_data:
            file_lines = file_data.split_lines()

        fixed_root_symbols = self._fix_selection_ranges(
            document_symbols.root_symbols, file_lines
        )
        one_based = self._convert_ranges_to_one_based(fixed_root_symbols)
        aligned = self._align_ranges_to_selection(one_based)
        return DocumentSymbols(aligned)

    def retrieve_symbol_body(
        self,
        symbol: Any,
        file_lines: list[str] | None = None,
        file_buffer: LSPFileBuffer | None = None,
    ) -> str:
        """
        Override to account for 1-based ranges in F# post-processing.
        """
        # Work with copies so callers keep 1-based lines
        sym_copy = json.loads(json.dumps(symbol))
        if "location" in sym_copy and "range" in sym_copy["location"]:
            rng = sym_copy["location"]["range"]
            rng["start"]["line"] = max(0, rng["start"]["line"] - 1)
            rng["end"]["line"] = max(0, rng["end"]["line"] - 1)
        if "range" in sym_copy:
            sym_copy["range"]["start"]["line"] = max(
                0, sym_copy["range"]["start"]["line"] - 1
            )
            sym_copy["range"]["end"]["line"] = max(
                0, sym_copy["range"]["end"]["line"] - 1
            )
        if "selectionRange" in sym_copy:
            sym_copy["selectionRange"]["start"]["line"] = max(
                0, sym_copy["selectionRange"]["start"]["line"] - 1
            )
            sym_copy["selectionRange"]["end"]["line"] = max(
                0, sym_copy["selectionRange"]["end"]["line"] - 1
            )

        return super().retrieve_symbol_body(
            sym_copy, file_lines=file_lines, file_buffer=file_buffer
        )
