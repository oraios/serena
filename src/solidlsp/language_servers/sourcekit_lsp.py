import logging
import os
import pathlib
import subprocess
import threading
import time

from overrides import override

from solidlsp import ls_types
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class SourceKitLSP(SolidLanguageServer):
    """
    Provides Swift specific instantiation of the LanguageServer class using sourcekit-lsp.
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For Swift projects, we should ignore:
        # - .build: Swift Package Manager build artifacts
        # - .swiftpm: Swift Package Manager metadata
        # - node_modules: if the project has JavaScript components
        # - dist/build: common output directories
        return super().is_ignored_dirname(dirname) or dirname in [".build", ".swiftpm", "node_modules", "dist", "build"]

    @staticmethod
    def _get_sourcekit_lsp_version() -> str:
        """Get the installed sourcekit-lsp version or raise error if sourcekit was not found."""
        try:
            result = subprocess.run(["sourcekit-lsp", "-h"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                raise Exception(f"`sourcekit-lsp -h` resulted in: {result}")
        except Exception as e:
            raise RuntimeError(
                "Could not find sourcekit-lsp, please install it as described in https://github.com/apple/sourcekit-lsp#installation"
                "And make sure it is available on your PATH."
            ) from e

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        custom_command = solidlsp_settings.get_ls_specific_settings(self.get_language_enum_instance()).get(SolidLSPSettings.CustomLSSettings.COMMAND_KEY, None)
        if custom_command:
            cmd = custom_command
        else:
            sourcekit_version = self._get_sourcekit_lsp_version()
            log.info(f"Starting sourcekit lsp with version: {sourcekit_version}")
            cmd = "sourcekit-lsp"

        super().__init__(
            config, repository_root_path, ProcessLaunchInfo(cmd=cmd, cwd=repository_root_path), "swift", solidlsp_settings
        )
        self.server_ready = threading.Event()
        self.request_id = 0
        self._did_sleep_before_requesting_references = False
        self._initialization_timestamp: float | None = None

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Swift Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()

        initialize_params = {
            "capabilities": {
                "general": {
                    "markdown": {"parser": "marked", "version": "1.1.0"},
                    "positionEncodings": ["utf-16"],
                    "regularExpressions": {"engine": "ECMAScript", "version": "ES2020"},
                    "staleRequestSupport": {
                        "cancel": True,
                        "retryOnContentModified": [
                            "textDocument/semanticTokens/full",
                            "textDocument/semanticTokens/range",
                            "textDocument/semanticTokens/full/delta",
                        ],
                    },
                },
                "notebookDocument": {"synchronization": {"dynamicRegistration": True, "executionSummarySupport": True}},
                "textDocument": {
                    "callHierarchy": {"dynamicRegistration": True},
                    "codeAction": {
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
                        "dataSupport": True,
                        "disabledSupport": True,
                        "dynamicRegistration": True,
                        "honorsChangeAnnotations": True,
                        "isPreferredSupport": True,
                        "resolveSupport": {"properties": ["edit"]},
                    },
                    "codeLens": {"dynamicRegistration": True},
                    "colorProvider": {"dynamicRegistration": True},
                    "completion": {
                        "completionItem": {
                            "commitCharactersSupport": True,
                            "deprecatedSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "insertReplaceSupport": True,
                            "insertTextModeSupport": {"valueSet": [1, 2]},
                            "labelDetailsSupport": True,
                            "preselectSupport": True,
                            "resolveSupport": {"properties": ["documentation", "detail", "additionalTextEdits"]},
                            "snippetSupport": True,
                            "tagSupport": {"valueSet": [1]},
                        },
                        "completionItemKind": {
                            "valueSet": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]
                        },
                        "completionList": {"itemDefaults": ["commitCharacters", "editRange", "insertTextFormat", "insertTextMode", "data"]},
                        "contextSupport": True,
                        "dynamicRegistration": True,
                        "insertTextMode": 2,
                    },
                    "declaration": {"dynamicRegistration": True, "linkSupport": True},
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "diagnostic": {"dynamicRegistration": True, "relatedDocumentSupport": False},
                    "documentHighlight": {"dynamicRegistration": True},
                    "documentLink": {"dynamicRegistration": True, "tooltipSupport": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "labelSupport": True,
                        "symbolKind": {
                            "valueSet": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26]
                        },
                        "tagSupport": {"valueSet": [1]},
                    },
                    "foldingRange": {
                        "dynamicRegistration": True,
                        "foldingRange": {"collapsedText": False},
                        "foldingRangeKind": {"valueSet": ["comment", "imports", "region"]},
                        "lineFoldingOnly": True,
                        "rangeLimit": 5000,
                    },
                    "formatting": {"dynamicRegistration": True},
                    "hover": {"contentFormat": ["markdown", "plaintext"], "dynamicRegistration": True},
                    "implementation": {"dynamicRegistration": True, "linkSupport": True},
                    "inlayHint": {
                        "dynamicRegistration": True,
                        "resolveSupport": {"properties": ["tooltip", "textEdits", "label.tooltip", "label.location", "label.command"]},
                    },
                    "inlineValue": {"dynamicRegistration": True},
                    "linkedEditingRange": {"dynamicRegistration": True},
                    "onTypeFormatting": {"dynamicRegistration": True},
                    "publishDiagnostics": {
                        "codeDescriptionSupport": True,
                        "dataSupport": True,
                        "relatedInformation": True,
                        "tagSupport": {"valueSet": [1, 2]},
                        "versionSupport": False,
                    },
                    "rangeFormatting": {"dynamicRegistration": True, "rangesSupport": True},
                    "references": {"dynamicRegistration": True},
                    "rename": {
                        "dynamicRegistration": True,
                        "honorsChangeAnnotations": True,
                        "prepareSupport": True,
                        "prepareSupportDefaultBehavior": 1,
                    },
                    "selectionRange": {"dynamicRegistration": True},
                    "semanticTokens": {
                        "augmentsSyntaxTokens": True,
                        "dynamicRegistration": True,
                        "formats": ["relative"],
                        "multilineTokenSupport": False,
                        "overlappingTokenSupport": False,
                        "requests": {"full": {"delta": True}, "range": True},
                        "serverCancelSupport": True,
                        "tokenModifiers": [
                            "declaration",
                            "definition",
                            "readonly",
                            "static",
                            "deprecated",
                            "abstract",
                            "async",
                            "modification",
                            "documentation",
                            "defaultLibrary",
                        ],
                        "tokenTypes": [
                            "namespace",
                            "type",
                            "class",
                            "enum",
                            "interface",
                            "struct",
                            "typeParameter",
                            "parameter",
                            "variable",
                            "property",
                            "enumMember",
                            "event",
                            "function",
                            "method",
                            "macro",
                            "keyword",
                            "modifier",
                            "comment",
                            "string",
                            "number",
                            "regexp",
                            "operator",
                            "decorator",
                        ],
                    },
                    "signatureHelp": {
                        "contextSupport": True,
                        "dynamicRegistration": True,
                        "signatureInformation": {
                            "activeParameterSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "parameterInformation": {"labelOffsetSupport": True},
                        },
                    },
                    "synchronization": {"didSave": True, "dynamicRegistration": True, "willSave": True, "willSaveWaitUntil": True},
                    "typeDefinition": {"dynamicRegistration": True, "linkSupport": True},
                    "typeHierarchy": {"dynamicRegistration": True},
                },
                "window": {
                    "showDocument": {"support": True},
                    "showMessage": {"messageActionItem": {"additionalPropertiesSupport": True}},
                    "workDoneProgress": True,
                },
                "workspace": {
                    "applyEdit": True,
                    "codeLens": {"refreshSupport": True},
                    "configuration": True,
                    "diagnostics": {"refreshSupport": True},
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {"dynamicRegistration": True, "relativePatternSupport": True},
                    "executeCommand": {"dynamicRegistration": True},
                    "fileOperations": {
                        "didCreate": True,
                        "didDelete": True,
                        "didRename": True,
                        "dynamicRegistration": True,
                        "willCreate": True,
                        "willDelete": True,
                        "willRename": True,
                    },
                    "foldingRange": {"refreshSupport": True},
                    "inlayHint": {"refreshSupport": True},
                    "inlineValue": {"refreshSupport": True},
                    "semanticTokens": {"refreshSupport": False},
                    "symbol": {
                        "dynamicRegistration": True,
                        "resolveSupport": {"properties": ["location.range"]},
                        "symbolKind": {
                            "valueSet": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26]
                        },
                        "tagSupport": {"valueSet": [1]},
                    },
                    "workspaceEdit": {
                        "changeAnnotationSupport": {"groupsOnLabel": True},
                        "documentChanges": True,
                        "failureHandling": "textOnlyTransactional",
                        "normalizesLineEndings": True,
                        "resourceOperations": ["create", "rename", "delete"],
                    },
                    "workspaceFolders": True,
                },
            },
            "clientInfo": {"name": "Visual Studio Code", "version": "1.102.2"},
            "initializationOptions": {
                "backgroundIndexing": True,
                "backgroundPreparationMode": "enabled",
                "textDocument/codeLens": {"supportedCommands": {"swift.debug": "swift.debug", "swift.run": "swift.run"}},
                "window/didChangeActiveDocument": True,
                "workspace/getReferenceDocument": True,
                "workspace/peekDocuments": True,
            },
            "locale": "en",
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
        """Start sourcekit-lsp server process"""

        def register_capability_handler(_params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(_params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting sourcekit-lsp server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        capabilities = init_response["capabilities"]
        log.info(f"SourceKit LSP capabilities: {list(capabilities.keys())}")

        assert "textDocumentSync" in capabilities, "textDocumentSync capability missing"
        assert "definitionProvider" in capabilities, "definitionProvider capability missing"

        self.server.notify.initialized({})
        self.completions_available.set()

        self.server_ready.set()
        self.server_ready.wait()

        # Mark initialization timestamp for smarter delay calculation
        self._initialization_timestamp = time.time()

    @override
    def request_references(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        # SourceKit LSP needs initialization + indexing time after startup
        # before it can provide accurate reference information. This sleep
        # prevents race conditions where references might not be available yet.
        # CI environments need extra time for project indexing and cross-file analysis
        if not self._did_sleep_before_requesting_references:
            # Calculate minimum delay based on how much time has passed since initialization
            if self._initialization_timestamp:
                elapsed = time.time() - self._initialization_timestamp
                # Increased CI delay for project indexing: 15s CI, 5s local
                base_delay = 15 if os.getenv("CI") else 5
                remaining_delay = max(2, base_delay - elapsed)
            else:
                # Fallback if initialization timestamp is missing
                remaining_delay = 15 if os.getenv("CI") else 5

            log.info(f"Sleeping {remaining_delay:.1f}s before requesting references for the first time (CI needs extra indexing time)")
            time.sleep(remaining_delay)
            self._did_sleep_before_requesting_references = True

        # Get references with retry logic for CI stability
        references = super().request_references(relative_file_path, line, column)

        # In CI, if no references found, retry once after additional delay
        if os.getenv("CI") and not references:
            log.info("No references found in CI - retrying after additional 5s delay")
            time.sleep(5)
            references = super().request_references(relative_file_path, line, column)

        return references
