"""
Provides TypeScript specific instantiation of the LanguageServer class. Contains various configurations and settings specific to TypeScript.
"""

import logging
import os
import pathlib
import shutil
import subprocess
import threading
from time import sleep

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo

# Platform-specific imports
if os.name != "nt":  # Unix-like systems
    import pwd
else:
    # Dummy pwd module for Windows
    class pwd:
        @staticmethod
        def getpwuid(uid):
            return type("obj", (), {"pw_name": os.environ.get("USERNAME", "unknown")})()


# Conditionally import pwd module (Unix-only)
if not PlatformUtils.get_platform_id().value.startswith("win"):
    import pwd


class TypeScriptLanguageServer(SolidLanguageServer):
    """
    Provides TypeScript specific instantiation of the LanguageServer class. Contains various configurations and settings specific to TypeScript.
    """

    def __init__(self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str):
        """
        Creates a TypeScriptLanguageServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        ts_lsp_executable_path = self.setup_runtime_dependencies(logger, config)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=ts_lsp_executable_path, cwd=repository_root_path),
            "typescript",
        )
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",
            "dist",
            "build",
            "coverage",
        ]

    def setup_runtime_dependencies(self, logger: LanguageServerLogger, config: LanguageServerConfig) -> str:
        """
        Setup runtime dependencies for TypeScript Language Server.
        """
        platform_id = PlatformUtils.get_platform_id()

        valid_platforms = [
            PlatformId.LINUX_x64,
            PlatformId.LINUX_arm64,
            PlatformId.OSX,
            PlatformId.OSX_x64,
            PlatformId.OSX_arm64,
            PlatformId.WIN_x64,
            PlatformId.WIN_arm64,
        ]
        assert platform_id in valid_platforms, f"Platform {platform_id} is not supported for multilspy javascript/typescript at the moment"

        runtime_dependencies = [
            {
                "id": "typescript",
                "description": "typescript package for Linux, OSX, and Windows. Both x64 and arm64 are supported.",
                "command": "npm install --prefix ./ typescript@5.5.4",
            },
            {
                "id": "typescript-language-server",
                "description": "typescript-language-server package for Linux, OSX, and Windows. Both x64 and arm64 are supported.",
                "command": "npm install --prefix ./ typescript-language-server@4.3.3",
            },
        ]
        tsserver_ls_dir = os.path.join(os.path.dirname(__file__), "static", "ts-lsp")
        tsserver_executable_path = os.path.join(tsserver_ls_dir, "typescript-language-server")

        # Verify both node and npm are installed
        is_node_installed = shutil.which("node") is not None
        assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
        is_npm_installed = shutil.which("npm") is not None
        assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."

        # Install typescript and typescript-language-server if not already installed
        if not os.path.exists(tsserver_ls_dir):
            os.makedirs(tsserver_ls_dir, exist_ok=True)
            for dependency in runtime_dependencies:
                # Windows doesn't support the 'user' parameter and doesn't have pwd module
                if PlatformUtils.get_platform_id().value.startswith("win"):
                    subprocess.run(
                        dependency["command"],
                        shell=True,
                        check=True,
                        cwd=tsserver_ls_dir,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    # On Unix-like systems, run as non-root user
                    user = pwd.getpwuid(os.getuid()).pw_name
                    subprocess.run(
                        dependency["command"],
                        shell=True,
                        check=True,
                        user=user,
                        cwd=tsserver_ls_dir,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )

        tsserver_executable_path = os.path.join(tsserver_ls_dir, "node_modules", ".bin", "typescript-language-server")

        assert os.path.exists(
            tsserver_executable_path
        ), "typescript-language-server executable not found. Please install typescript-language-server and try again."
        return f"{tsserver_executable_path} --stdio"

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the TypeScript Language Server.
        """
        initialize_params = {
            "locale": "en",
            "rootPath": "$rootPath",
            "rootUri": "$rootUri",
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
                        "symbolKind": {
                            "valueSet": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26]
                        },
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
                        "symbolKind": {
                            "valueSet": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26]
                        },
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
                    "cfgs": {},
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
            "workspaceFolders": [{"uri": "$uri", "name": "$name"}],
        }

        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params["processId"] = os.getpid()
        initialize_params["rootPath"] = repository_absolute_path
        initialize_params["rootUri"] = root_uri
        initialize_params["workspaceFolders"][0]["uri"] = root_uri
        initialize_params["workspaceFolders"][0]["name"] = os.path.basename(repository_absolute_path)

        return initialize_params

    def _start_server(self):
        """
        Starts the TypeScript Language Server, waits for the server to be ready and yields the LanguageServer instance.

        Usage:
        ```
        async with lsp.start_server():
            # LanguageServer has been initialized and ready to serve requests
            await lsp.request_definition(...)
            await lsp.request_references(...)
            # Shutdown the LanguageServer on exit from scope
        # LanguageServer has been shutdown
        """

        def register_capability_handler(params):
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
                    # TypeScript doesn't have a direct equivalent to resolve_main_method
                    # You might want to set a different flag or remove this line
                    # self.resolve_main_method_available.set()
            return

        def execute_client_command_handler(params):
            return []

        def do_nothing(params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        def check_experimental_status(params):
            """
            Also listen for experimental/serverStatus as a backup signal
            """
            if params.get("quiescent") == True:
                self.server_ready.set()
                self.completions_available.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        self.logger.log("Starting TypeScript server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)

        # TypeScript-specific capability checks
        assert init_response["capabilities"]["textDocumentSync"] == 2
        assert "completionProvider" in init_response["capabilities"]
        assert init_response["capabilities"]["completionProvider"] == {
            "triggerCharacters": [".", '"', "'", "/", "@", "<"],
            "resolveProvider": True,
        }

        self.server.notify.initialized({})
        if self.server_ready.wait(timeout=1.0):
            self.logger.log("TypeScript server is ready", logging.INFO)
        else:
            self.logger.log("Timeout waiting for TypeScript server to become ready, proceeding anyway", logging.INFO)
            # Fallback: assume server is ready after timeout
            self.server_ready.set()
        self.completions_available.set()

    @override
    # For some reason, the LS may need longer to process this, so we just retry
    def _send_references_request(self, relative_file_path: str, line: int, column: int):
        # TODO: The LS doesn't return references contained in other files if it doesn't sleep. This is
        #   despite the LS having processed requests already. I don't know what causes this, but sleeping
        #   one second helps. It may be that sleeping only once is enough but that's hard to reliably test.
        #   It may be that even this 1sec is not enough in larger TS projects, at some point we should find what
        #   causes this and solve it.
        sleep(1)
        return super()._send_references_request(relative_file_path, line, column)
