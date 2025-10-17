"""
Provides Rust specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Rust.
"""

import logging
import os
import pathlib
import shutil
import subprocess
import threading

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


class RustAnalyzer(SolidLanguageServer):
    """
    Provides Rust specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Rust.
    """

    @staticmethod
    def _get_rustup_version():
        """Get installed rustup version or None if not found."""
        try:
            result = subprocess.run(["rustup", "--version"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        return None

    @staticmethod
    def _get_rust_analyzer_path():
        """Get rust-analyzer path via rustup or system PATH."""
        # First try rustup
        try:
            result = subprocess.run(["rustup", "which", "rust-analyzer"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            pass

        # Fallback to system PATH
        return shutil.which("rust-analyzer")

    @staticmethod
    def _ensure_rust_analyzer_installed():
        """Ensure rust-analyzer is available, install via rustup if needed."""
        path = RustAnalyzer._get_rust_analyzer_path()
        if path:
            return path

        # Check if rustup is available
        if not RustAnalyzer._get_rustup_version():
            raise RuntimeError(
                "Neither rust-analyzer nor rustup is installed.\n"
                "Please install Rust via https://rustup.rs/ or install rust-analyzer separately."
            )

        # Try to install rust-analyzer component
        result = subprocess.run(["rustup", "component", "add", "rust-analyzer"], check=False, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to install rust-analyzer via rustup: {result.stderr}")

        # Try again after installation
        path = RustAnalyzer._get_rust_analyzer_path()
        if not path:
            raise RuntimeError("rust-analyzer installation succeeded but binary not found in PATH")

        return path

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        """
        Creates a RustAnalyzer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        rustanalyzer_executable_path = self._ensure_rust_analyzer_installed()
        logger.log(f"Using rust-analyzer at: {rustanalyzer_executable_path}", logging.INFO)

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=rustanalyzer_executable_path, cwd=repository_root_path),
            "rust",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.service_ready_event = threading.Event()
        self.initialize_searcher_command_available = threading.Event()
        self.resolve_main_method_available = threading.Event()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["target"]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Rust Analyzer Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "clientInfo": {"name": "Visual Studio Code - Insiders", "version": "1.82.0-insider"},
            "locale": "en",
            "capabilities": {
                "workspace": {
                    "applyEdit": True,
                    "workspaceEdit": {
                        "documentChanges": True,
                        "resourceOperations": ["create", "rename", "delete"],
                        "failureHandling": "textOnlyTransactional",
                        "normalizesLineEndings": True,
                        "changeAnnotationSupport": {"groupsOnLabel": True},
                    },
                    "configuration": True,
                    "didChangeWatchedFiles": {"dynamicRegistration": True, "relativePatternSupport": True},
                    "symbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                        "tagSupport": {"valueSet": [1]},
                        "resolveSupport": {"properties": ["location.range"]},
                    },
                    "codeLens": {"refreshSupport": True},
                    "executeCommand": {"dynamicRegistration": True},
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "workspaceFolders": True,
                    "semanticTokens": {"refreshSupport": True},
                    "fileOperations": {
                        "dynamicRegistration": True,
                        "didCreate": True,
                        "didRename": True,
                        "didDelete": True,
                        "willCreate": True,
                        "willRename": True,
                        "willDelete": True,
                    },
                    "inlineValue": {"refreshSupport": True},
                    "inlayHint": {"refreshSupport": True},
                    "diagnostics": {"refreshSupport": True},
                },
                "textDocument": {
                    "publishDiagnostics": {
                        "relatedInformation": True,
                        "versionSupport": False,
                        "tagSupport": {"valueSet": [1, 2]},
                        "codeDescriptionSupport": True,
                        "dataSupport": True,
                    },
                    "synchronization": {"dynamicRegistration": True, "willSave": True, "willSaveWaitUntil": True, "didSave": True},
                    "completion": {
                        "dynamicRegistration": True,
                        "contextSupport": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "deprecatedSupport": True,
                            "preselectSupport": True,
                            "tagSupport": {"valueSet": [1]},
                            "insertReplaceSupport": True,
                            "resolveSupport": {"properties": ["documentation", "detail", "additionalTextEdits"]},
                            "insertTextModeSupport": {"valueSet": [1, 2]},
                            "labelDetailsSupport": True,
                        },
                        "insertTextMode": 2,
                        "completionItemKind": {
                            "valueSet": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]
                        },
                        "completionList": {"itemDefaults": ["commitCharacters", "editRange", "insertTextFormat", "insertTextMode"]},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "signatureHelp": {
                        "dynamicRegistration": True,
                        "signatureInformation": {
                            "documentationFormat": ["markdown", "plaintext"],
                            "parameterInformation": {"labelOffsetSupport": True},
                            "activeParameterSupport": True,
                        },
                        "contextSupport": True,
                    },
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentHighlight": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                        "hierarchicalDocumentSymbolSupport": True,
                        "tagSupport": {"valueSet": [1]},
                        "labelSupport": True,
                    },
                    "codeAction": {
                        "dynamicRegistration": True,
                        "isPreferredSupport": True,
                        "disabledSupport": True,
                        "dataSupport": True,
                        "resolveSupport": {"properties": ["edit"]},
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
                        "honorsChangeAnnotations": False,
                    },
                    "codeLens": {"dynamicRegistration": True},
                    "formatting": {"dynamicRegistration": True},
                    "rangeFormatting": {"dynamicRegistration": True},
                    "onTypeFormatting": {"dynamicRegistration": True},
                    "rename": {
                        "dynamicRegistration": True,
                        "prepareSupport": True,
                        "prepareSupportDefaultBehavior": 1,
                        "honorsChangeAnnotations": True,
                    },
                    "documentLink": {"dynamicRegistration": True, "tooltipSupport": True},
                    "typeDefinition": {"dynamicRegistration": True, "linkSupport": True},
                    "implementation": {"dynamicRegistration": True, "linkSupport": True},
                    "colorProvider": {"dynamicRegistration": True},
                    "foldingRange": {
                        "dynamicRegistration": True,
                        "rangeLimit": 5000,
                        "lineFoldingOnly": True,
                        "foldingRangeKind": {"valueSet": ["comment", "imports", "region"]},
                        "foldingRange": {"collapsedText": False},
                    },
                    "declaration": {"dynamicRegistration": True, "linkSupport": True},
                    "selectionRange": {"dynamicRegistration": True},
                    "callHierarchy": {"dynamicRegistration": True},
                    "semanticTokens": {
                        "dynamicRegistration": True,
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
                        "formats": ["relative"],
                        "requests": {"range": True, "full": {"delta": True}},
                        "multilineTokenSupport": False,
                        "overlappingTokenSupport": False,
                        "serverCancelSupport": True,
                        "augmentsSyntaxTokens": False,
                    },
                    "linkedEditingRange": {"dynamicRegistration": True},
                    "typeHierarchy": {"dynamicRegistration": True},
                    "inlineValue": {"dynamicRegistration": True},
                    "inlayHint": {
                        "dynamicRegistration": True,
                        "resolveSupport": {"properties": ["tooltip", "textEdits", "label.tooltip", "label.location", "label.command"]},
                    },
                    "diagnostic": {"dynamicRegistration": True, "relatedDocumentSupport": False},
                },
                "window": {
                    "showMessage": {"messageActionItem": {"additionalPropertiesSupport": True}},
                    "showDocument": {"support": True},
                    "workDoneProgress": True,
                },
                "general": {
                    "staleRequestSupport": {
                        "cancel": True,
                        "retryOnContentModified": [
                            "textDocument/semanticTokens/full",
                            "textDocument/semanticTokens/range",
                            "textDocument/semanticTokens/full/delta",
                        ],
                    },
                    "regularExpressions": {"engine": "ECMAScript", "version": "ES2020"},
                    "markdown": {
                        "parser": "marked",
                        "version": "1.1.0",
                        "allowedTags": [
                            "ul",
                            "li",
                            "p",
                            "code",
                            "blockquote",
                            "ol",
                            "h1",
                            "h2",
                            "h3",
                            "h4",
                            "h5",
                            "h6",
                            "hr",
                            "em",
                            "pre",
                            "table",
                            "thead",
                            "tbody",
                            "tr",
                            "th",
                            "td",
                            "div",
                            "del",
                            "a",
                            "strong",
                            "br",
                            "img",
                            "span",
                        ],
                    },
                    "positionEncodings": ["utf-16"],
                },
                "notebookDocument": {"synchronization": {"dynamicRegistration": True, "executionSummarySupport": True}},
                "experimental": {
                    "snippetTextEdit": True,
                    "codeActionGroup": True,
                    "hoverActions": True,
                    "serverStatusNotification": True,
                    "colorDiagnosticOutput": True,
                    "openServerLogs": True,
                    "localDocs": True,
                    "commands": {
                        "commands": [
                            "rust-analyzer.runSingle",
                            "rust-analyzer.debugSingle",
                            "rust-analyzer.showReferences",
                            "rust-analyzer.gotoLocation",
                            "editor.action.triggerParameterHints",
                        ]
                    },
                },
            },
            "initializationOptions": {
                "cargoRunner": None,
                "runnables": {"extraEnv": None, "problemMatcher": ["$rustc"], "command": None, "extraArgs": []},
                "statusBar": {"clickAction": "openLogs"},
                "server": {"path": None, "extraEnv": None},
                "trace": {"server": "verbose", "extension": False},
                "debug": {
                    "engine": "auto",
                    "sourceFileMap": {"/rustc/<id>": "${env:USERPROFILE}/.rustup/toolchains/<toolchain-id>/lib/rustlib/src/rust"},
                    "openDebugPane": False,
                    "engineSettings": {},
                },
                "restartServerOnConfigChange": False,
                "typing": {"continueCommentsOnNewline": True, "autoClosingAngleBrackets": {"enable": False}},
                "diagnostics": {
                    "previewRustcOutput": False,
                    "useRustcErrorCode": False,
                    "disabled": [],
                    "enable": True,
                    "experimental": {"enable": False},
                    "remapPrefix": {},
                    "warningsAsHint": [],
                    "warningsAsInfo": [],
                },
                "discoverProjectRunner": None,
                "showUnlinkedFileNotification": True,
                "showDependenciesExplorer": True,
                "assist": {"emitMustUse": False, "expressionFillDefault": "todo"},
                "cachePriming": {"enable": True, "numThreads": 0},
                "cargo": {
                    "autoreload": True,
                    "buildScripts": {
                        "enable": True,
                        "invocationLocation": "workspace",
                        "invocationStrategy": "per_workspace",
                        "overrideCommand": None,
                        "useRustcWrapper": True,
                    },
                    "cfgs": [],
                    "extraArgs": [],
                    "extraEnv": {},
                    "features": [],
                    "noDefaultFeatures": False,
                    "sysroot": "discover",
                    "sysrootSrc": None,
                    "target": None,
                    "unsetTest": ["core"],
                },
                "checkOnSave": True,
                "check": {
                    "allTargets": True,
                    "command": "check",
                    "extraArgs": [],
                    "extraEnv": {},
                    "features": None,
                    "ignore": [],
                    "invocationLocation": "workspace",
                    "invocationStrategy": "per_workspace",
                    "noDefaultFeatures": None,
                    "overrideCommand": None,
                    "targets": None,
                },
                "completion": {
                    "autoimport": {"enable": True},
                    "autoself": {"enable": True},
                    "callable": {"snippets": "fill_arguments"},
                    "fullFunctionSignatures": {"enable": False},
                    "limit": None,
                    "postfix": {"enable": True},
                    "privateEditable": {"enable": False},
                    "snippets": {
                        "custom": {
                            "Arc::new": {
                                "postfix": "arc",
                                "body": "Arc::new(${receiver})",
                                "requires": "std::sync::Arc",
                                "description": "Put the expression into an `Arc`",
                                "scope": "expr",
                            },
                            "Rc::new": {
                                "postfix": "rc",
                                "body": "Rc::new(${receiver})",
                                "requires": "std::rc::Rc",
                                "description": "Put the expression into an `Rc`",
                                "scope": "expr",
                            },
                            "Box::pin": {
                                "postfix": "pinbox",
                                "body": "Box::pin(${receiver})",
                                "requires": "std::boxed::Box",
                                "description": "Put the expression into a pinned `Box`",
                                "scope": "expr",
                            },
                            "Ok": {
                                "postfix": "ok",
                                "body": "Ok(${receiver})",
                                "description": "Wrap the expression in a `Result::Ok`",
                                "scope": "expr",
                            },
                            "Err": {
                                "postfix": "err",
                                "body": "Err(${receiver})",
                                "description": "Wrap the expression in a `Result::Err`",
                                "scope": "expr",
                            },
                            "Some": {
                                "postfix": "some",
                                "body": "Some(${receiver})",
                                "description": "Wrap the expression in an `Option::Some`",
                                "scope": "expr",
                            },
                        }
                    },
                },
                "files": {"excludeDirs": [], "watcher": "client"},
                "highlightRelated": {
                    "breakPoints": {"enable": True},
                    "closureCaptures": {"enable": True},
                    "exitPoints": {"enable": True},
                    "references": {"enable": True},
                    "yieldPoints": {"enable": True},
                },
                "hover": {
                    "actions": {
                        "debug": {"enable": True},
                        "enable": True,
                        "gotoTypeDef": {"enable": True},
                        "implementations": {"enable": True},
                        "references": {"enable": False},
                        "run": {"enable": True},
                    },
                    "documentation": {"enable": True, "keywords": {"enable": True}},
                    "links": {"enable": True},
                    "memoryLayout": {"alignment": "hexadecimal", "enable": True, "niches": False, "offset": "hexadecimal", "size": "both"},
                },
                "imports": {
                    "granularity": {"enforce": False, "group": "crate"},
                    "group": {"enable": True},
                    "merge": {"glob": True},
                    "preferNoStd": False,
                    "preferPrelude": False,
                    "prefix": "plain",
                },
                "inlayHints": {
                    "bindingModeHints": {"enable": False},
                    "chainingHints": {"enable": True},
                    "closingBraceHints": {"enable": True, "minLines": 25},
                    "closureCaptureHints": {"enable": False},
                    "closureReturnTypeHints": {"enable": "never"},
                    "closureStyle": "impl_fn",
                    "discriminantHints": {"enable": "never"},
                    "expressionAdjustmentHints": {"enable": "never", "hideOutsideUnsafe": False, "mode": "prefix"},
                    "lifetimeElisionHints": {"enable": "never", "useParameterNames": False},
                    "maxLength": 25,
                    "parameterHints": {"enable": True},
                    "reborrowHints": {"enable": "never"},
                    "renderColons": True,
                    "typeHints": {"enable": True, "hideClosureInitialization": False, "hideNamedConstructor": False},
                },
                "interpret": {"tests": False},
                "joinLines": {"joinAssignments": True, "joinElseIf": True, "removeTrailingComma": True, "unwrapTrivialBlock": True},
                "lens": {
                    "debug": {"enable": True},
                    "enable": True,
                    "forceCustomCommands": True,
                    "implementations": {"enable": True},
                    "location": "above_name",
                    "references": {
                        "adt": {"enable": False},
                        "enumVariant": {"enable": False},
                        "method": {"enable": False},
                        "trait": {"enable": False},
                    },
                    "run": {"enable": True},
                },
                "linkedProjects": [],
                "lru": {"capacity": None, "query": {"capacities": {}}},
                "notifications": {"cargoTomlNotFound": True},
                "numThreads": None,
                "procMacro": {"attributes": {"enable": True}, "enable": True, "ignored": {}, "server": None},
                "references": {"excludeImports": False},
                "rust": {"analyzerTargetDir": None},
                "rustc": {"source": None},
                "rustfmt": {"extraArgs": [], "overrideCommand": None, "rangeFormatting": {"enable": False}},
                "semanticHighlighting": {
                    "doc": {"comment": {"inject": {"enable": True}}},
                    "nonStandardTokens": True,
                    "operator": {"enable": True, "specialization": {"enable": False}},
                    "punctuation": {"enable": False, "separate": {"macro": {"bang": False}}, "specialization": {"enable": False}},
                    "strings": {"enable": True},
                },
                "signatureInfo": {"detail": "full", "documentation": {"enable": True}},
                "workspace": {"symbol": {"search": {"kind": "only_types", "limit": 128, "scope": "workspace"}}},
            },
            "trace": "verbose",
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
        """
        Starts the Rust Analyzer Language Server
        """

        def register_capability_handler(params):
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
                    self.resolve_main_method_available.set()
            return

        def lang_status_handler(params):
            # TODO: Should we wait for
            # server -> client: {'jsonrpc': '2.0', 'method': 'language/status', 'params': {'type': 'ProjectStatus', 'message': 'OK'}}
            # Before proceeding?
            if params["type"] == "ServiceReady" and params["message"] == "ServiceReady":
                self.service_ready_event.set()

        def execute_client_command_handler(params):
            return []

        def do_nothing(params):
            return

        def check_experimental_status(params):
            if params["quiescent"] == True:
                self.server_ready.set()

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("language/status", lang_status_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        self.logger.log("Starting RustAnalyzer server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)
        assert init_response["capabilities"]["textDocumentSync"]["change"] == 2
        assert "completionProvider" in init_response["capabilities"]
        assert init_response["capabilities"]["completionProvider"] == {
            "resolveProvider": True,
            "triggerCharacters": [":", ".", "'", "("],
            "completionItem": {"labelDetailsSupport": True},
        }
        self.server.notify.initialized({})
        self.completions_available.set()

        self.server_ready.wait()
