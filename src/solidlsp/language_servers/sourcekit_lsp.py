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
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


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

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        sourcekit_version = self._get_sourcekit_lsp_version()
        logger.log(f"Starting sourcekit lsp with version: {sourcekit_version}", logging.INFO)

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd="sourcekit-lsp", cwd=repository_root_path),
            "swift",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.request_id = 0
        self._did_sleep_before_requesting_references = False

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

        return initialize_params

    def _start_server(self):
        """Start sourcekit-lsp server process"""

        def register_capability_handler(_params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        def do_nothing(_params):
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting sourcekit-lsp server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)

        capabilities = init_response["capabilities"]
        self.logger.log(f"SourceKit LSP capabilities: {list(capabilities.keys())}", logging.INFO)

        assert "textDocumentSync" in capabilities, "textDocumentSync capability missing"
        assert "definitionProvider" in capabilities, "definitionProvider capability missing"

        self.server.notify.initialized({})
        self.completions_available.set()

        self.server_ready.set()
        self.server_ready.wait()

    @override
    def request_references(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        # SourceKit LSP needs a short initialization period after startup
        # before it can provide accurate reference information. This sleep
        # prevents race conditions where references might not be available yet.
        # Unfortunately, sourcekit doesn't send a signal when it's really ready
        if not self._did_sleep_before_requesting_references:
            self.logger.log("Sleeping 5s before requesting references for the first time", logging.DEBUG)
            time.sleep(5)
            self._did_sleep_before_requesting_references = True
        return super().request_references(relative_file_path, line, column)
