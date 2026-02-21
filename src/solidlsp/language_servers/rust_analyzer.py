"""
Provides Rust specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Rust.
"""

import logging
import os
import pathlib
import platform
import shutil
import subprocess
import threading
from typing import cast

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class RustAnalyzer(SolidLanguageServer):
    """
    Provides Rust specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Rust.
    """

    @staticmethod
    def _determine_log_level(line: str) -> int:
        """Classify rust-analyzer stderr output to avoid false-positive errors."""
        line_lower = line.lower()

        # Known informational/warning messages from rust-analyzer that aren't critical errors
        if any(
            [
                "failed to find any projects in" in line_lower,
                "fetchworkspaceerror" in line_lower,
            ]
        ):
            return logging.DEBUG

        return SolidLanguageServer._determine_log_level(line)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        @staticmethod
        def _get_rustup_version() -> str | None:
            """Get installed rustup version or None if not found."""
            try:
                result = subprocess.run(["rustup", "--version"], capture_output=True, text=True, check=False)
                if result.returncode == 0:
                    return result.stdout.strip()
            except FileNotFoundError:
                return None
            return None

        @staticmethod
        def _get_rust_analyzer_via_rustup() -> str | None:
            """Get rust-analyzer path via rustup. Returns None if not found."""
            try:
                result = subprocess.run(["rustup", "which", "rust-analyzer"], capture_output=True, text=True, check=False)
                if result.returncode == 0:
                    return result.stdout.strip()
            except FileNotFoundError:
                pass
            return None

        @staticmethod
        def _ensure_rust_analyzer_installed() -> str:
            """
            Ensure rust-analyzer is available.

            Priority order:
            1. Rustup existing installation (preferred - matches toolchain version)
            2. Rustup auto-install if rustup is available (ensures correct version)
            3. Common installation locations as fallback (only if rustup not available)
            4. System PATH last (can pick up incompatible versions)

            :return: path to rust-analyzer executable
            """
            # Try rustup FIRST (preferred - avoids picking up incompatible versions from PATH)
            rustup_path = RustAnalyzer.DependencyProvider._get_rust_analyzer_via_rustup()
            if rustup_path:
                return rustup_path

            # If rustup is available but rust-analyzer not installed, auto-install it BEFORE
            # checking common paths. This ensures we get the correct version matching the toolchain.
            if RustAnalyzer.DependencyProvider._get_rustup_version():
                result = subprocess.run(["rustup", "component", "add", "rust-analyzer"], check=False, capture_output=True, text=True)
                if result.returncode == 0:
                    # Verify installation worked
                    rustup_path = RustAnalyzer.DependencyProvider._get_rust_analyzer_via_rustup()
                    if rustup_path:
                        return rustup_path
                # If auto-install failed, fall through to common paths as last resort

            # Determine platform-specific binary name and paths
            is_windows = platform.system() == "Windows"
            binary_name = "rust-analyzer.exe" if is_windows else "rust-analyzer"

            # Fallback to common installation locations (only used if rustup not available)
            common_paths: list[str | None] = []

            if is_windows:
                # Windows-specific paths
                home = pathlib.Path.home()
                common_paths.extend(
                    [
                        str(home / ".cargo" / "bin" / binary_name),  # cargo install / rustup
                        str(home / "scoop" / "shims" / binary_name),  # Scoop package manager
                        str(home / "scoop" / "apps" / "rust-analyzer" / "current" / binary_name),  # Scoop direct
                        str(
                            pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "rust-analyzer" / binary_name
                        ),  # Standalone install
                    ]
                )
            else:
                # Unix-like paths (macOS, Linux)
                common_paths.extend(
                    [
                        "/opt/homebrew/bin/rust-analyzer",  # macOS Homebrew (Apple Silicon)
                        "/usr/local/bin/rust-analyzer",  # macOS Homebrew (Intel) / Linux system
                        os.path.expanduser("~/.cargo/bin/rust-analyzer"),  # cargo install
                        os.path.expanduser("~/.local/bin/rust-analyzer"),  # User local bin
                    ]
                )

            for path in common_paths:
                if path and os.path.isfile(path) and os.access(path, os.X_OK):
                    return path

            # Last resort: check system PATH (can pick up incorrect aliases, hence checked last)
            path_result = shutil.which("rust-analyzer")
            if path_result and os.path.isfile(path_result) and os.access(path_result, os.X_OK):
                return path_result

            # Provide helpful error message with all searched locations
            searched = [p for p in common_paths if p]
            install_instructions = [
                "  - Rustup: rustup component add rust-analyzer",
                "  - Cargo: cargo install rust-analyzer",
            ]
            if is_windows:
                install_instructions.extend(
                    [
                        "  - Scoop: scoop install rust-analyzer",
                        "  - Chocolatey: choco install rust-analyzer",
                        "  - Standalone: Download from https://github.com/rust-lang/rust-analyzer/releases",
                    ]
                )
            else:
                install_instructions.extend(
                    [
                        "  - Homebrew (macOS): brew install rust-analyzer",
                        "  - System package manager (Linux): apt/dnf/pacman install rust-analyzer",
                    ]
                )

            raise RuntimeError(
                "rust-analyzer is not installed or not in PATH.\n"
                "Searched locations:\n" + "\n".join(f"  - {p}" for p in searched) + "\n"
                "Please install rust-analyzer via:\n" + "\n".join(install_instructions)
            )

        def _get_or_install_core_dependency(self) -> str:
            return self._ensure_rust_analyzer_installed()

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path]

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a RustAnalyzer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            "rust",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.service_ready_event = threading.Event()
        self.initialize_searcher_command_available = threading.Event()
        self.resolve_main_method_available = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

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
        return cast(InitializeParams, initialize_params)

    def _start_server(self) -> None:
        """
        Starts the Rust Analyzer Language Server
        """

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
                    self.resolve_main_method_available.set()
            return

        def lang_status_handler(params: dict) -> None:
            # TODO: Should we wait for
            # server -> client: {'jsonrpc': '2.0', 'method': 'language/status', 'params': {'type': 'ProjectStatus', 'message': 'OK'}}
            # Before proceeding?
            if params["type"] == "ServiceReady" and params["message"] == "ServiceReady":
                self.service_ready_event.set()

        def execute_client_command_handler(params: dict) -> list:
            return []

        def do_nothing(params: dict) -> None:
            return

        def check_experimental_status(params: dict) -> None:
            if params["quiescent"] == True:
                self.server_ready.set()

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("language/status", lang_status_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        log.info("Starting RustAnalyzer server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        assert init_response["capabilities"]["textDocumentSync"]["change"] == 2  # type: ignore
        assert "completionProvider" in init_response["capabilities"]
        assert init_response["capabilities"]["completionProvider"] == {
            "resolveProvider": True,
            "triggerCharacters": [":", ".", "'", "("],
            "completionItem": {"labelDetailsSupport": True},
        }
        self.server.notify.initialized({})

        self.server_ready.wait()
