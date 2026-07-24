"""
Provides F# specific instantiation of the LanguageServer class.
"""

import logging
import os
import re
import shutil
import threading
from pathlib import Path

from overrides import override

from serena.util.dotnet import DotNETUtil
from solidlsp import ls_types
from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection
from solidlsp.ls import DocumentSymbols, LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig, LanguageServerId
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_FSAUTOCOMPLETE_VERSION = "0.83.0"
DEFAULT_FSAUTOCOMPLETE_VERSION = "0.83.0"
FSAUTOCOMPLETE_VERSION = DEFAULT_FSAUTOCOMPLETE_VERSION

# Matches an F# module declaration line ("module Foo", "module Foo =", "module rec Foo =",
# dotted names), used to recover the module name's real column. See _fix_module_selection_range.
_MODULE_DECLARATION_PATTERN = re.compile(r"^\s*module\s+(?:rec\s+)?([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)")


class FSharpLanguageServer(SolidLanguageServer):
    """
    Provides F# specific instantiation of the LanguageServer class using Ionide LSP (FsAutoComplete).
    Contains various configurations and settings specific to F# development.

    You can pass the following entries in ``ls_specific_settings["fsharp"]``:
        - fsautocomplete_version: Override the pinned FsAutoComplete version
          installed by Serena (default: the bundled Serena version).
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates an FSharpLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        fsharp_lsp_executable_path = self._setup_runtime_dependencies(config, solidlsp_settings)
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=fsharp_lsp_executable_path, cwd=repository_root_path),
            "fsharp",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "bin",
            "obj",
            "packages",
            ".paket",
            "paket-files",
            ".fake",
            ".ionide",
        ]

    def _fix_module_selection_range(
        self, symbol: ls_types.UnifiedSymbolInformation, file_content: str
    ) -> ls_types.UnifiedSymbolInformation:
        """
        FsAutoComplete's selectionRange for a `module <Name>` declaration points at the `module`
        keyword itself instead of at `<Name>` (confirmed by dsyme and MischaPanch in #925), so any
        caller that hovers or searches references from selectionRange.start (e.g.
        serena.symbol.LanguageServerSymbol.line/.column) gets the generic keyword's info instead of
        the module's own. Other symbol kinds (functions, types, `open`) already select the
        identifier correctly, so only Module symbols are touched here.
        """
        if symbol.get("kind") != ls_types.SymbolKind.Module or "selectionRange" not in symbol:
            return symbol

        sel_range = symbol["selectionRange"]
        start_line = sel_range["start"]["line"]
        lines = file_content.split("\n")
        if start_line >= len(lines):
            return symbol

        match = _MODULE_DECLARATION_PATTERN.match(lines[start_line])
        if not match:
            return symbol

        name_start, name_end = match.span(1)
        if sel_range["start"]["character"] == name_start:
            return symbol  # already correct (e.g. a future FsAutoComplete release)

        corrected_symbol = symbol.copy()
        corrected_symbol["selectionRange"] = {
            "start": {"line": start_line, "character": name_start},
            "end": {"line": start_line, "character": name_end},
        }
        return corrected_symbol

    @override
    def request_document_symbols(self, relative_file_path: str, file_buffer: LSPFileBuffer | None = None) -> DocumentSymbols:
        # Override to fix FsAutoComplete's incorrect selectionRange for module declarations (#925):
        # it points at the `module` keyword instead of the module name, so hover-by-selectionRange
        # returns the keyword's docs instead of the module's own.
        document_symbols = super().request_document_symbols(relative_file_path, file_buffer=file_buffer)

        with self.open_file(relative_file_path) as file_data:
            file_content = file_data.contents

        def fix_symbol_and_children(symbol: ls_types.UnifiedSymbolInformation) -> ls_types.UnifiedSymbolInformation:
            fixed = self._fix_module_selection_range(symbol, file_content)
            if fixed.get("children"):
                fixed["children"] = [fix_symbol_and_children(child) for child in fixed["children"]]
            return fixed

        fixed_root_symbols = [fix_symbol_and_children(sym) for sym in document_symbols.root_symbols]
        return DocumentSymbols(fixed_root_symbols)

    @classmethod
    def _setup_runtime_dependencies(cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings) -> str:
        """
        Setup runtime dependencies for F# Language Server and return the command to start the server.
        """
        fsharp_settings = solidlsp_settings.get_ls_specific_settings(LanguageServerId.FSHARP)
        fsautocomplete_version = fsharp_settings.get("fsautocomplete_version", DEFAULT_FSAUTOCOMPLETE_VERSION)
        dotnet_exe = DotNETUtil("8.0", allow_higher_version=True).get_dotnet_path_or_raise()

        RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="fsautocomplete",
                    description="FsAutoComplete (Ionide F# Language Server)",
                    command=f"dotnet tool install --tool-path ./ fsautocomplete --version {fsautocomplete_version}",
                    platform_id="any",
                ),
            ]
        )

        # Install FsAutoComplete if not already installed
        # legacy unversioned dir reserved for INITIAL; every other version goes into a versioned subdir
        ls_dirname = "fsharp-lsp" if fsautocomplete_version == INITIAL_FSAUTOCOMPLETE_VERSION else f"fsharp-lsp-{fsautocomplete_version}"
        fsharp_ls_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), ls_dirname)
        fsautocomplete_path = os.path.join(fsharp_ls_dir, "fsautocomplete")

        # Handle Windows executable extension
        if os.name == "nt":
            fsautocomplete_path += ".exe"

        if not os.path.exists(fsautocomplete_path):
            log.info(f"FsAutoComplete executable not found at {fsautocomplete_path}. Installing...")

            # Ensure the directory exists
            os.makedirs(fsharp_ls_dir, exist_ok=True)

            # Install FsAutoComplete using dotnet tool install
            try:
                import subprocess

                result = subprocess.run(
                    [dotnet_exe, "tool", "install", "--tool-path", fsharp_ls_dir, "fsautocomplete", "--version", fsautocomplete_version],
                    cwd=fsharp_ls_dir,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                log.info("FsAutoComplete installed successfully")
                log.debug(f"Installation output: {result.stdout}")
            except subprocess.CalledProcessError as e:
                log.error(f"Failed to install FsAutoComplete: {e.stderr}")
                raise RuntimeError(f"Failed to install FsAutoComplete: {e.stderr}")

        if not os.path.exists(fsautocomplete_path):
            raise FileNotFoundError(
                f"FsAutoComplete executable not found at {fsautocomplete_path}, something went wrong with the installation."
            )

        # FsAutoComplete uses --lsp flag for LSP mode
        return f"{fsautocomplete_path} --adaptive-lsp-server-enabled --project-graph-enabled --use-fcs-transparent-compiler"

    def _create_base_initialize_params(self) -> dict:
        """
        Returns the initialize params for the F# Language Server.
        """
        initialize_params = {
            "capabilities": {
                "workspace": {
                    "applyEdit": True,
                    "workspaceEdit": {"documentChanges": True},
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
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
                    "completion": {
                        "dynamicRegistration": True,
                        "contextSupport": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "deprecatedSupport": True,
                        },
                    },
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"],
                    },
                    "signatureHelp": {
                        "dynamicRegistration": True,
                        "signatureInformation": {"documentationFormat": ["markdown", "plaintext"]},
                    },
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentHighlight": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},  # All SymbolKind values (1-26)
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
                    "codeLens": {"dynamicRegistration": True},
                    "formatting": {"dynamicRegistration": True},
                    "rangeFormatting": {"dynamicRegistration": True},
                    "onTypeFormatting": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True},
                    "documentLink": {"dynamicRegistration": True},
                    "publishDiagnostics": {
                        "relatedInformation": True,
                        "versionSupport": False,
                        "tagSupport": {"valueSet": [1, 2]},
                    },
                    "implementation": {"dynamicRegistration": True},
                    "typeDefinition": {"dynamicRegistration": True},
                    "colorProvider": {"dynamicRegistration": True},
                    "foldingRange": {
                        "dynamicRegistration": True,
                        "rangeLimit": 5000,
                        "lineFoldingOnly": True,
                    },
                    "declaration": {"dynamicRegistration": True},
                    "selectionRange": {"dynamicRegistration": True},
                },
                "window": {
                    "workDoneProgress": True,
                },
            },
            "initializationOptions": {
                # F# specific initialization options
                "automaticWorkspaceInit": True,
                "abstractClassStubGeneration": True,
                "abstractClassStubGenerationObjectIdentifier": "this",
                "abstractClassStubGenerationMethodBody": 'failwith "Not Implemented"',
                "addFsiWatcher": False,
                "codeLenses": {"signature": {"enabled": True}, "references": {"enabled": True}},
                "disableInMemoryProjectReferences": False,
                "dotNetRoot": self._get_dotnet_root(),
                "enableMSBuildProjectGraph": False,
                "excludeProjectDirectories": ["paket-files"],
                "externalAutocomplete": False,
                "fsac": {"attachDebugger": False, "silencedLogs": [], "conserveMemory": False, "netCoreDllPath": ""},
                "fsiExtraParameters": [],
                "generateBinlog": False,
                "interfaceStubGeneration": True,
                "interfaceStubGenerationObjectIdentifier": "this",
                "interfaceStubGenerationMethodBody": 'failwith "Not Implemented"',
                "keywordsAutocomplete": True,
                "linter": True,
                "pipelineHints": {"enabled": True},
                "recordStubGeneration": True,
                "recordStubGenerationBody": 'failwith "Not Implemented"',
                "resolveNamespaces": True,
                "saveOnlyOpenFiles": False,
                "showProjectExplorerIn": ["ionide", "solution"],
                "simplifyNameAnalyzer": True,
                "smartIndent": False,
                "suggestGitignore": True,
                "suggestSdkScripts": True,
                "unionCaseStubGeneration": True,
                "unionCaseStubGenerationBody": 'failwith "Not Implemented"',
                "unusedDeclarationsAnalyzer": True,
                "unusedOpensAnalyzer": True,
                "verboseLogging": False,
                "workspaceModePeekDeepLevel": 2,
                "workspacePath": self.repository_root_path,
            },
            "trace": "off",
        }

        return initialize_params

    def _get_dotnet_root(self) -> str:
        """
        Get the .NET root directory.
        """
        dotnet_exe = shutil.which("dotnet")
        if dotnet_exe:
            # Try to get the installation path
            try:
                import subprocess

                result = subprocess.run([dotnet_exe, "--info"], capture_output=True, text=True, check=True)
                lines = result.stdout.split("\n")
                for line in lines:
                    if "Base Path:" in line or "Base path:" in line:
                        base_path = line.split(":", 1)[1].strip()
                        # Get the parent directory (remove 'sdk/version' part)
                        return str(Path(base_path).parent.parent)
            except (subprocess.CalledProcessError, Exception):
                pass

        # Fallback: use the directory containing dotnet executable
        if dotnet_exe:
            return str(Path(dotnet_exe).parent)

        return ""

    def _start_server(self) -> None:
        """
        Start the F# Language Server with custom handlers.
        """

        def handle_window_log_message(params: dict) -> None:
            """Handle window/logMessage from the LSP server."""
            message = params.get("message", "")
            message_type = params.get("type", 1)

            # Map LSP log levels to Python logging levels
            level_map = {1: logging.ERROR, 2: logging.WARNING, 3: logging.INFO, 4: logging.DEBUG}
            level = level_map.get(message_type, logging.INFO)

            log.log(level, f"FsAutoComplete: {message}")

        def handle_window_show_message(params: dict) -> None:
            """Handle window/showMessage from the LSP server."""
            message = params.get("message", "")
            message_type = params.get("type", 1)

            # Map LSP message types to Python logging levels
            level_map = {1: logging.ERROR, 2: logging.WARNING, 3: logging.INFO, 4: logging.DEBUG}
            level = level_map.get(message_type, logging.INFO)

            log.log(level, f"FsAutoComplete Message: {message}")

        def handle_workspace_configuration(params: dict) -> list:
            """Handle workspace/configuration requests from the LSP server."""
            # Return empty configuration for now
            items = params.get("items", [])
            return [None] * len(items)

        def handle_client_register_capability(params: dict) -> None:
            """Handle client/registerCapability requests from the LSP server."""
            # For now, just acknowledge the registration
            return

        def handle_client_unregister_capability(params: dict) -> None:
            """Handle client/unregisterCapability requests from the LSP server."""
            # For now, just acknowledge the unregistration
            return

        def handle_work_done_progress_create(params: dict) -> None:
            """Handle window/workDoneProgress/create requests from the LSP server."""
            # Just acknowledge the request - we don't need to track progress for now
            return

        # Register custom handlers
        self.server.on_notification("window/logMessage", handle_window_log_message)
        self.server.on_notification("window/showMessage", handle_window_show_message)
        self.server.on_request("workspace/configuration", handle_workspace_configuration)
        self.server.on_request("client/registerCapability", handle_client_register_capability)
        self.server.on_request("client/unregisterCapability", handle_client_unregister_capability)
        self.server.on_request("window/workDoneProgress/create", handle_work_done_progress_create)

        log.info("Starting FsAutoComplete F# language server process")

        try:
            self.server.start()
        except Exception as e:
            log.error(f"Failed to start F# language server process: {e}")
            raise SolidLSPException(f"Failed to start F# language server: {e}")

        # Send initialization
        initialize_params = self._create_initialize_params()

        log.info("Sending initialize request to F# language server")
        try:
            self.server.send.initialize(initialize_params)
            log.debug("Received initialize response from F# language server")
        except Exception as e:
            raise SolidLSPException(f"Failed to initialize F# language server for {self.repository_root_path}: {e}") from e

        # Complete initialization
        self.server.notify.initialized({})

        log.info("F# language server initialized successfully")

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        """
        F# projects can be large and may need more time for cross-file analysis.
        """
        return 15.0  # 15 seconds should be sufficient for most F# projects
