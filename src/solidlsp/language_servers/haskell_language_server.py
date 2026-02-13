"""
Provides Haskell specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Haskell.
"""

import logging
import os
import pathlib
import shutil
import time

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


class HaskellLanguageServer(SolidLanguageServer):
    """
    Provides Haskell specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Haskell.
    Uses Haskell Language Server (HLS) for LSP functionality.
    """

    @staticmethod
    def _ensure_hls_installed():
        """Ensure haskell-language-server-wrapper is available."""
        # Try common locations
        common_paths = [
            shutil.which("haskell-language-server-wrapper"),
            "/opt/homebrew/bin/haskell-language-server-wrapper",
            "/usr/local/bin/haskell-language-server-wrapper",
            os.path.expanduser("~/.ghcup/bin/haskell-language-server-wrapper"),
            os.path.expanduser("~/.cabal/bin/haskell-language-server-wrapper"),
            os.path.expanduser("~/.local/bin/haskell-language-server-wrapper"),
        ]

        # Check Stack programs directory
        stack_programs = os.path.expanduser("~/.local/share/stack/programs")
        if os.path.exists(stack_programs):
            try:
                for arch_dir in os.listdir(stack_programs):
                    arch_path = os.path.join(stack_programs, arch_dir)
                    if os.path.isdir(arch_path):
                        try:
                            for ghc_dir in os.listdir(arch_path):
                                hls_path = os.path.join(arch_path, ghc_dir, "bin", "haskell-language-server-wrapper")
                                if os.path.isfile(hls_path) and os.access(hls_path, os.X_OK):
                                    common_paths.append(hls_path)
                        except (PermissionError, OSError):
                            # Skip directories we can't read
                            continue
            except (PermissionError, OSError):
                # Stack programs directory not accessible
                pass

        for path in common_paths:
            if path and os.path.isfile(path) and os.access(path, os.X_OK):
                return path

        raise RuntimeError(
            "haskell-language-server-wrapper is not installed or not in PATH.\n"
            "Searched locations:\n" + "\n".join(f"  - {p}" for p in common_paths if p) + "\n"
            "Please install HLS via:\n"
            "  - GHCup: https://www.haskell.org/ghcup/\n"
            "  - Stack: stack install haskell-language-server\n"
            "  - Cabal: cabal install haskell-language-server\n"
            "  - Homebrew (macOS): brew install haskell-language-server"
        )

    @override
    def download_dependencies(self) -> tuple[bool, str]:

        status = True if self._ensure_hls_installed() else False
        message = "haskell found successfully" if status else "You must set haskell LS manually"
        return status, message

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        """
        Creates a HaskellLanguageServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        hls_executable_path = self._ensure_hls_installed()
        logger.log(f"Using haskell-language-server at: {hls_executable_path}", logging.INFO)

        # Check if there's a haskell subdirectory with Stack/Cabal project
        haskell_subdir = os.path.join(repository_root_path, "haskell")
        if os.path.exists(haskell_subdir) and (
            os.path.exists(os.path.join(haskell_subdir, "stack.yaml")) or os.path.exists(os.path.join(haskell_subdir, "cabal.project"))
        ):
            working_dir = haskell_subdir
            logger.log(f"Using Haskell project directory: {working_dir}", logging.INFO)
        else:
            working_dir = repository_root_path

        # Set up environment with GHCup bin in PATH
        env = dict(os.environ)
        ghcup_bin = os.path.expanduser("~/.ghcup/bin")
        if ghcup_bin not in env.get("PATH", ""):
            env["PATH"] = f"{ghcup_bin}{os.pathsep}{env.get('PATH', '')}"

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=[hls_executable_path, "--lsp", "--cwd", working_dir], cwd=working_dir, env=env),
            "haskell",
            solidlsp_settings,
        )

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["dist", "dist-newstyle", ".stack-work", ".cabal-sandbox"]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Haskell Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "clientInfo": {"name": "Serena", "version": "0.1.0"},
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
                    "executeCommand": {"dynamicRegistration": True},
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "workspaceFolders": True,
                    "semanticTokens": {"refreshSupport": True},
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
                    },
                    "linkedEditingRange": {"dynamicRegistration": True},
                },
                "window": {
                    "showMessage": {"messageActionItem": {"additionalPropertiesSupport": True}},
                    "showDocument": {"support": True},
                    "workDoneProgress": True,
                },
                "general": {
                    "staleRequestSupport": {"cancel": True, "retryOnContentModified": []},
                    "regularExpressions": {"engine": "ECMAScript", "version": "ES2020"},
                    "markdown": {
                        "parser": "marked",
                        "version": "1.1.0",
                    },
                    "positionEncodings": ["utf-16"],
                },
            },
            "initializationOptions": {
                "haskell": {
                    "formattingProvider": "ormolu",
                    "checkProject": True,
                }
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
        Starts the Haskell Language Server
        """

        def do_nothing(params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        def register_capability_handler(params):
            """Handle dynamic capability registration from HLS"""
            if "registrations" in params:
                for registration in params.get("registrations", []):
                    method = registration.get("method", "")
                    self.logger.log(f"HLS registered capability: {method}", logging.INFO)
            return

        def workspace_configuration_handler(params):
            """Handle workspace/configuration requests from HLS"""
            self.logger.log(f"HLS requesting configuration: {params}", logging.INFO)

            # Configuration matching VS Code settings and initialization options
            haskell_config = {
                "formattingProvider": "ormolu",
                "checkProject": True,
                "plugin": {"importLens": {"codeActionsOn": False, "codeLensOn": False}, "hlint": {"codeActionsOn": False}},
            }

            # HLS expects array of config items matching requested sections
            if isinstance(params, dict) and "items" in params:
                result = []
                for item in params["items"]:
                    section = item.get("section", "")
                    if section == "haskell":
                        result.append(haskell_config)
                    else:
                        result.append({})
                self.logger.log(f"Returning configuration: {result}", logging.INFO)
                return result

            # Fallback: return single config
            return [haskell_config]

        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("workspace/configuration", workspace_configuration_handler)

        self.logger.log("Starting Haskell Language Server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)

        # Log capabilities returned by HLS
        capabilities = init_response.get("capabilities", {})
        self.logger.log(f"HLS capabilities: {list(capabilities.keys())}", logging.INFO)

        self.server.notify.initialized({})
        self.completions_available.set()

        # Give HLS time to index the project
        # HLS can be slow to index, especially on first run
        self.logger.log("Waiting for HLS to index project...", logging.INFO)
        time.sleep(5)

        self.logger.log("Haskell Language Server initialized successfully", logging.INFO)
