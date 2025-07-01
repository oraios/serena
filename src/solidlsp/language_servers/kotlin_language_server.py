"""
Provides Kotlin specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Kotlin.
"""

import dataclasses
import logging
import os
import pathlib
import stat

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import FileUtils, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo


@dataclasses.dataclass
class KotlinRuntimeDependencyPaths:
    """
    Stores the paths to the runtime dependencies of Kotlin Language Server
    """

    java_path: str
    java_home_path: str
    kotlin_executable_path: str


class KotlinLanguageServer(SolidLanguageServer):
    """
    Provides Kotlin specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Kotlin.
    """

    def __init__(self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str):
        """
        Creates a Kotlin Language Server instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        runtime_dependency_paths = self.setup_runtime_dependencies(logger, config)
        self.runtime_dependency_paths = runtime_dependency_paths

        # Create command to execute the Kotlin Language Server script
        cmd = f'"{self.runtime_dependency_paths.kotlin_executable_path}"'

        # Set environment variables including JAVA_HOME
        proc_env = {"JAVA_HOME": self.runtime_dependency_paths.java_home_path}

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=cmd, env=proc_env, cwd=repository_root_path),
            "kotlin",
        )

    def setup_runtime_dependencies(self, logger: LanguageServerLogger, config: LanguageServerConfig) -> KotlinRuntimeDependencyPaths:
        """
        Setup runtime dependencies for Kotlin Language Server.
        """
        platform_id = PlatformUtils.get_platform_id()

        # Verify platform support
        assert (
            platform_id.value.startswith("win-") or platform_id.value.startswith("linux-") or platform_id.value.startswith("osx-")
        ), "Only Windows, Linux and macOS platforms are supported for Kotlin in multilspy at the moment"

        # Runtime dependency information
        runtime_dependencies = {
            "runtimeDependency": {
                "id": "KotlinLsp",
                "description": "Kotlin Language Server",
                "url": "https://github.com/fwcd/kotlin-language-server/releases/download/1.3.13/server.zip",
                "archiveType": "zip",
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

        kotlin_dependency = runtime_dependencies["runtimeDependency"]
        java_dependency = runtime_dependencies["java"][platform_id.value]

        # Setup paths for dependencies
        static_dir = os.path.join(os.path.dirname(__file__), "static", "kotlin_language_server")
        os.makedirs(static_dir, exist_ok=True)

        # Setup Java paths
        java_dir = os.path.join(static_dir, "java")
        os.makedirs(java_dir, exist_ok=True)

        java_home_path = os.path.join(java_dir, java_dependency["java_home_path"])
        java_path = os.path.join(java_dir, java_dependency["java_path"])

        # Download and extract Java if not exists
        if not os.path.exists(java_path):
            logger.log(f"Downloading Java for {platform_id.value}...", logging.INFO)
            FileUtils.download_and_extract_archive(logger, java_dependency["url"], java_dir, java_dependency["archiveType"])
            # Make Java executable
            if not platform_id.value.startswith("win-"):
                os.chmod(java_path, 0o755)

        assert os.path.exists(java_path), f"Java executable not found at {java_path}"

        # Setup Kotlin Language Server paths
        kotlin_ls_dir = os.path.join(static_dir, "server")

        # Get platform-specific executable script path
        if platform_id.value.startswith("win-"):
            kotlin_script = os.path.join(kotlin_ls_dir, "bin", "kotlin-language-server.bat")
        else:
            kotlin_script = os.path.join(kotlin_ls_dir, "bin", "kotlin-language-server")

        # Download and extract Kotlin Language Server if script doesn't exist
        if not os.path.exists(kotlin_script):
            logger.log("Downloading Kotlin Language Server...", logging.INFO)
            FileUtils.download_and_extract_archive(logger, kotlin_dependency["url"], static_dir, kotlin_dependency["archiveType"])

            # Make script executable on Unix platforms
            if os.path.exists(kotlin_script) and not platform_id.value.startswith("win-"):
                os.chmod(
                    kotlin_script, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
                )

        # Use script file
        if os.path.exists(kotlin_script):
            kotlin_executable_path = kotlin_script
            logger.log(f"Using Kotlin Language Server script at {kotlin_script}", logging.INFO)
        else:
            raise FileNotFoundError(f"Kotlin Language Server script not found at {kotlin_script}")

        return KotlinRuntimeDependencyPaths(
            java_path=java_path, java_home_path=java_home_path, kotlin_executable_path=kotlin_executable_path
        )

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Kotlin Language Server.
        """
        if not os.path.isabs(repository_absolute_path):
            repository_absolute_path = os.path.abspath(repository_absolute_path)

        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "clientInfo": {"name": "Multilspy Kotlin Client", "version": "1.0.0"},
            "locale": "en",
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
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
                    "synchronization": {"dynamicRegistration": True, "willSave": True, "willSaveWaitUntil": True, "didSave": True},
                    "completion": {
                        "dynamicRegistration": True,
                        "contextSupport": True,
                        "completionItem": {
                            "snippetSupport": False,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "deprecatedSupport": True,
                            "preselectSupport": True,
                            "tagSupport": {"valueSet": [1]},
                            "insertReplaceSupport": False,
                            "resolveSupport": {"properties": ["documentation", "detail", "additionalTextEdits"]},
                            "insertTextModeSupport": {"valueSet": [1, 2]},
                            "labelDetailsSupport": True,
                        },
                        "insertTextMode": 2,
                        "completionItemKind": {
                            "valueSet": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]
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
                        "augmentsSyntaxTokens": True,
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
                    "markdown": {"parser": "marked", "version": "1.1.0"},
                    "positionEncodings": ["utf-16"],
                },
                "notebookDocument": {"synchronization": {"dynamicRegistration": True, "executionSummarySupport": True}},
            },
            "initializationOptions": {
                "workspaceFolders": [root_uri],
                "storagePath": None,
                "codegen": {"enabled": False},
                "compiler": {"jvm": {"target": "default"}},
                "completion": {"snippets": {"enabled": True}},
                "diagnostics": {"enabled": True, "level": 4, "debounceTime": 250},
                "scripts": {"enabled": True, "buildScriptsEnabled": True},
                "indexing": {"enabled": True},
                "externalSources": {"useKlsScheme": False, "autoConvertToKotlin": False},
                "inlayHints": {"typeHints": False, "parameterHints": False, "chainedHints": False},
                "formatting": {
                    "formatter": "ktfmt",
                    "ktfmt": {
                        "style": "google",
                        "indent": 4,
                        "maxWidth": 100,
                        "continuationIndent": 8,
                        "removeUnusedImports": True,
                    },
                },
            },
            "trace": "verbose",
            "processId": os.getpid(),
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
        Starts the Kotlin Language Server
        """

        def execute_client_command_handler(params):
            return []

        def do_nothing(params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)

        self.logger.log("Starting Kotlin server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)

        capabilities = init_response["capabilities"]
        assert "textDocumentSync" in capabilities, "Server must support textDocumentSync"
        assert "hoverProvider" in capabilities, "Server must support hover"
        assert "completionProvider" in capabilities, "Server must support code completion"
        assert "signatureHelpProvider" in capabilities, "Server must support signature help"
        assert "definitionProvider" in capabilities, "Server must support go to definition"
        assert "referencesProvider" in capabilities, "Server must support find references"
        assert "documentSymbolProvider" in capabilities, "Server must support document symbols"
        assert "workspaceSymbolProvider" in capabilities, "Server must support workspace symbols"
        assert "semanticTokensProvider" in capabilities, "Server must support semantic tokens"

        self.server.notify.initialized({})
        self.completions_available.set()
