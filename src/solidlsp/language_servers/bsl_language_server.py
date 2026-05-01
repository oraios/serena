"""
BSL (1C:Enterprise) Language Server implementation for the SolidLSP framework.
Provides support for 1C:Enterprise and OneScript languages via BSL Language Server.
"""

import dataclasses
import logging
import os
import pathlib

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import FileUtils, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


@dataclasses.dataclass
class BslRuntimeDependencyPaths:
    """
    Stores the paths to the runtime dependencies of BSL Language Server
    """

    java_path: str
    java_home_path: str
    bsl_jar_path: str


class BslLanguageServer(SolidLanguageServer):
    """
    BSL Language Server for 1C:Enterprise and OneScript.
    Provides comprehensive language support including diagnostics, navigation,
    code completion, and refactoring for BSL (1C:Enterprise script language).
    """

    def __init__(
        self,
        config: LanguageServerConfig,
        logger: LanguageServerLogger,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
    ):
        """
        Creates a BSL Language Server instance.
        This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        runtime_dependency_paths = self._setup_runtime_dependencies(logger, config, solidlsp_settings)
        self.runtime_dependency_paths = runtime_dependency_paths

        # Create command to execute the BSL Language Server JAR
        cmd = [
            self.runtime_dependency_paths.java_path,
            "-jar",
            self.runtime_dependency_paths.bsl_jar_path,
            # BSL Language Server uses stdio by default, no additional parameters needed
        ]

        # Set environment variables including JAVA_HOME
        proc_env = {"JAVA_HOME": self.runtime_dependency_paths.java_home_path}

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=cmd, env=proc_env, cwd=repository_root_path),
            "bsl",
            solidlsp_settings,
        )

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        """
        Ignore directories that are typically not part of 1C source code.
        """
        return super().is_ignored_dirname(dirname) or dirname in [
            "out",  # 1C output directory
            "bin",  # Binary files
            "ConfigDumpInfo",  # Configuration dump
            "DT-INF",  # 1C Designer info
            ".git",  # Git repository
            ".vscode",  # VSCode settings
            ".idea",  # IntelliJ IDEA settings
        ]

    @classmethod
    def _setup_runtime_dependencies(
        cls,
        logger: LanguageServerLogger,
        config: LanguageServerConfig,
        solidlsp_settings: SolidLSPSettings,
    ) -> BslRuntimeDependencyPaths:
        """
        Setup runtime dependencies for BSL Language Server and return the paths.
        Downloads Java runtime and BSL Language Server JAR if not present.
        """
        platform_id = PlatformUtils.get_platform_id()

        # Verify platform support
        assert platform_id.value.startswith("win-") or platform_id.value.startswith("linux-") or platform_id.value.startswith("osx-"), (
            "Only Windows, Linux and macOS platforms are supported for BSL"
        )

        # Runtime dependency information
        # Using latest stable version from https://github.com/1c-syntax/bsl-language-server/releases
        runtime_dependencies = {
            "bsl_server": {
                "id": "BslLanguageServer",
                "description": "BSL Language Server for 1C:Enterprise",
                "url": "https://github.com/1c-syntax/bsl-language-server/releases/download/v0.24.0-rc.3/bsl-language-server-0.24.0-rc.3-exec.jar",
                "archiveType": "jar",  # Direct JAR download, no extraction needed
            },
            "java": {
                "win-x64": {
                    "url": "https://github.com/redhat-developer/vscode-java/releases/download/v1.42.0/java-win32-x64-1.42.0-561.vsix",
                    "archiveType": "zip",
                    "java_home_path": "extension/jre/21.0.7-win32-x86_64",
                    "java_path": "extension/jre/21.0.7-win32-x86_64/bin/java.exe",
                },
                "linux-x64": {
                    "url": "https://github.com/redhat-developer/vscode-java/releases/download/v1.42.0/java-linux-x64-1.42.0-561.vsix",
                    "archiveType": "zip",
                    "java_home_path": "extension/jre/21.0.7-linux-x86_64",
                    "java_path": "extension/jre/21.0.7-linux-x86_64/bin/java",
                },
                "linux-arm64": {
                    "url": "https://github.com/redhat-developer/vscode-java/releases/download/v1.42.0/java-linux-arm64-1.42.0-561.vsix",
                    "archiveType": "zip",
                    "java_home_path": "extension/jre/21.0.7-linux-aarch64",
                    "java_path": "extension/jre/21.0.7-linux-aarch64/bin/java",
                },
                "osx-x64": {
                    "url": "https://github.com/redhat-developer/vscode-java/releases/download/v1.42.0/java-darwin-x64-1.42.0-561.vsix",
                    "archiveType": "zip",
                    "java_home_path": "extension/jre/21.0.7-macosx-x86_64",
                    "java_path": "extension/jre/21.0.7-macosx-x86_64/bin/java",
                },
                "osx-arm64": {
                    "url": "https://github.com/redhat-developer/vscode-java/releases/download/v1.42.0/java-darwin-arm64-1.42.0-561.vsix",
                    "archiveType": "zip",
                    "java_home_path": "extension/jre/21.0.7-macosx-aarch64",
                    "java_path": "extension/jre/21.0.7-macosx-aarch64/bin/java",
                },
            },
        }

        bsl_dependency = runtime_dependencies["bsl_server"]
        java_dependency = runtime_dependencies["java"][platform_id.value]

        # Setup paths for dependencies
        static_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), "bsl_language_server")
        os.makedirs(static_dir, exist_ok=True)

        # Setup Java paths
        java_dir = os.path.join(static_dir, "java")
        os.makedirs(java_dir, exist_ok=True)

        java_home_path = os.path.join(java_dir, java_dependency["java_home_path"])
        java_path = os.path.join(java_dir, java_dependency["java_path"])

        # Download and extract Java if not exists
        if not os.path.exists(java_path):
            logger.log(f"Downloading Java for {platform_id.value}...", logging.INFO)
            FileUtils.download_and_extract_archive(
                logger,
                java_dependency["url"],
                java_dir,
                java_dependency["archiveType"],
            )
            # Make Java executable on Unix platforms
            if not platform_id.value.startswith("win-"):
                os.chmod(java_path, 0o755)

        assert os.path.exists(java_path), f"Java executable not found at {java_path}"

        # Setup BSL Language Server JAR path
        bsl_jar_path = os.path.join(static_dir, "bsl-language-server.jar")

        # Download BSL Language Server JAR if not exists
        if not os.path.exists(bsl_jar_path):
            logger.log("Downloading BSL Language Server JAR...", logging.INFO)
            # Direct download of JAR file
            import urllib.request

            urllib.request.urlretrieve(bsl_dependency["url"], bsl_jar_path)
            logger.log(f"BSL Language Server downloaded to {bsl_jar_path}", logging.INFO)

        assert os.path.exists(bsl_jar_path), f"BSL Language Server JAR not found at {bsl_jar_path}"

        return BslRuntimeDependencyPaths(
            java_path=java_path,
            java_home_path=java_home_path,
            bsl_jar_path=bsl_jar_path,
        )

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the BSL Language Server.
        """
        if not os.path.isabs(repository_absolute_path):
            repository_absolute_path = os.path.abspath(repository_absolute_path)

        root_uri = pathlib.Path(repository_absolute_path).as_uri()

        initialize_params: InitializeParams = {
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "initializationOptions": {
                # BSL Language Server specific options
                "diagnosticLanguage": "ru",  # Use Russian for diagnostics
                "showCognitiveComplexityCodeLens": True,
                "showCyclomaticComplexityCodeLens": True,
                "computeDiagnostics": "onType",  # or "onSave"
                "traceLog": False,
                "configurationPath": "",  # Path to .bsl-language-server.json if needed
            },
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
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {
                        "dynamicRegistration": True,
                        "relativePatternSupport": True,
                    },
                    "symbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                        "tagSupport": {"valueSet": [1]},
                        "resolveSupport": {"properties": ["location.range"]},
                    },
                    "codeLens": {"refreshSupport": True},
                    "executeCommand": {"dynamicRegistration": True},
                    "configuration": True,
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
                            "preselectSupport": True,
                            "tagSupport": {"valueSet": [1]},
                            "insertReplaceSupport": False,
                            "resolveSupport": {
                                "properties": [
                                    "documentation",
                                    "detail",
                                    "additionalTextEdits",
                                ]
                            },
                            "insertTextModeSupport": {"valueSet": [1, 2]},
                            "labelDetailsSupport": True,
                        },
                        "insertTextMode": 2,
                        "completionItemKind": {"valueSet": list(range(1, 26))},
                        "completionList": {
                            "itemDefaults": [
                                "commitCharacters",
                                "editRange",
                                "insertTextFormat",
                                "insertTextMode",
                            ]
                        },
                    },
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"],
                    },
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
                    "documentLink": {
                        "dynamicRegistration": True,
                        "tooltipSupport": True,
                    },
                    "typeDefinition": {
                        "dynamicRegistration": True,
                        "linkSupport": True,
                    },
                    "implementation": {
                        "dynamicRegistration": True,
                        "linkSupport": True,
                    },
                    "colorProvider": {"dynamicRegistration": True},
                    "foldingRange": {
                        "dynamicRegistration": True,
                        "rangeLimit": 5000,
                        "lineFoldingOnly": True,
                        "foldingRangeKind": {"valueSet": ["comment", "imports", "region"]},
                        "foldingRange": {"collapsedText": False},
                    },
                    "declaration": {
                        "dynamicRegistration": True,
                        "linkSupport": True,
                    },
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
                        "augmentsSyntaxTokens": True,
                    },
                    "linkedEditingRange": {"dynamicRegistration": True},
                    "typeHierarchy": {"dynamicRegistration": True},
                    "inlineValue": {"dynamicRegistration": True},
                    "inlayHint": {
                        "dynamicRegistration": True,
                        "resolveSupport": {
                            "properties": [
                                "tooltip",
                                "textEdits",
                                "label.tooltip",
                                "label.location",
                                "label.command",
                            ]
                        },
                    },
                    "diagnostic": {
                        "dynamicRegistration": True,
                        "relatedDocumentSupport": False,
                    },
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
                    "markdown": {"parser": "marked", "version": "1.1.0"},
                    "positionEncodings": ["utf-16"],
                },
                "notebookDocument": {
                    "synchronization": {
                        "dynamicRegistration": True,
                        "executionSummarySupport": True,
                    }
                },
            },
            "trace": "verbose",
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
        Starts the BSL Language Server
        """

        def do_nothing(params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        # Register common notification handlers
        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting BSL Language Server process", logging.INFO)
        self.server.start()

        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to BSL Language Server and awaiting response",
            logging.INFO,
        )

        init_response = self.server.send.initialize(initialize_params)

        # Verify required capabilities
        capabilities = init_response.get("capabilities", {})

        # BSL Language Server should support these basic features
        assert "textDocumentSync" in capabilities, "Server must support textDocumentSync"
        assert "definitionProvider" in capabilities, "Server must support go to definition"
        assert "referencesProvider" in capabilities, "Server must support find references"
        assert "documentSymbolProvider" in capabilities, "Server must support document symbols"

        # Optional but useful capabilities
        if "hoverProvider" in capabilities:
            self.logger.log("Hover support available", logging.INFO)

        if "completionProvider" in capabilities:
            self.logger.log("Code completion support available", logging.INFO)

        if "signatureHelpProvider" in capabilities:
            self.logger.log("Signature help support available", logging.INFO)

        if "workspaceSymbolProvider" in capabilities:
            self.logger.log("Workspace symbols support available", logging.INFO)

        # Notify server that initialization is complete
        self.server.notify.initialized({})

        # BSL Language Server is ready
        self.completions_available.set()

        self.logger.log("BSL Language Server initialized successfully", logging.INFO)
