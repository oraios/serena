"""
Provides Kotlin specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Kotlin.

You can configure the following options in ls_specific_settings (in serena_config.yml):

    ls_specific_settings:
      kotlin:
        ls_path: '/path/to/kotlin-lsp.sh'  # Custom path to Kotlin Language Server executable
        kotlin_lsp_version: '261.13587.0'  # Kotlin Language Server version (default: current bundled version)
        jvm_options: '-Xmx2G'  # JVM options for Kotlin Language Server (default: -Xmx2G)

Example configuration for large projects:

    ls_specific_settings:
      kotlin:
        jvm_options: '-Xmx4G -XX:+UseG1GC'
"""

import logging
import os
import pathlib
import stat
import threading
from typing import cast

from overrides import override

from solidlsp.ls import (
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_utils import FileUtils, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# Default JVM options for Kotlin Language Server
# -Xmx2G: 2GB heap is sufficient for most projects; override via ls_specific_settings for large codebases
DEFAULT_KOTLIN_JVM_OPTIONS = "-Xmx2G"

# Default Kotlin Language Server version (can be overridden via ls_specific_settings)
DEFAULT_KOTLIN_LSP_VERSION = "261.13587.0"

# Platform-specific Kotlin LSP download suffixes
PLATFORM_KOTLIN_SUFFIX = {
    "win-x64": "win-x64",
    "linux-x64": "linux-x64",
    "linux-arm64": "linux-aarch64",
    "osx-x64": "mac-x64",
    "osx-arm64": "mac-aarch64",
}


class KotlinLanguageServer(SolidLanguageServer):
    """
    Provides Kotlin specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Kotlin.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a Kotlin Language Server instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            "kotlin",
            solidlsp_settings,
        )

        # Indexing synchronisation: starts SET (= already done), cleared if the server
        # sends window/workDoneProgress/create (async-indexing servers like KLS v261+),
        # set again once all progress tokens have ended.
        self._indexing_complete = threading.Event()
        self._indexing_complete.set()
        self._active_progress_tokens: set[str] = set()
        self._progress_lock = threading.Lock()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def __init__(self, custom_settings: SolidLSPSettings.CustomLSSettings, ls_resources_dir: str):
            super().__init__(custom_settings, ls_resources_dir)
            self._java_home_path: str | None = None

        def _get_or_install_core_dependency(self) -> str:
            """
            Setup runtime dependencies for Kotlin Language Server and return the path to the executable script.
            """
            platform_id = PlatformUtils.get_platform_id()

            # Verify platform support
            assert (
                platform_id.value.startswith("win-") or platform_id.value.startswith("linux-") or platform_id.value.startswith("osx-")
            ), "Only Windows, Linux and macOS platforms are supported for Kotlin in multilspy at the moment"

            kotlin_suffix = PLATFORM_KOTLIN_SUFFIX.get(platform_id.value)
            assert kotlin_suffix, f"Unsupported platform for Kotlin LSP: {platform_id.value}"

            # Setup paths for dependencies
            static_dir = os.path.join(self._ls_resources_dir, "kotlin_language_server")
            os.makedirs(static_dir, exist_ok=True)

            # Setup Kotlin Language Server
            kotlin_script_name = "kotlin-lsp.cmd" if platform_id.value.startswith("win-") else "kotlin-lsp.sh"
            kotlin_script = os.path.join(static_dir, kotlin_script_name)

            if not os.path.exists(kotlin_script):
                kotlin_lsp_version = self._custom_settings.get("kotlin_lsp_version", DEFAULT_KOTLIN_LSP_VERSION)
                kotlin_url = f"https://download-cdn.jetbrains.com/kotlin-lsp/{kotlin_lsp_version}/kotlin-lsp-{kotlin_lsp_version}-{kotlin_suffix}.zip"
                log.info("Downloading Kotlin Language Server...")
                FileUtils.download_and_extract_archive(kotlin_url, static_dir, "zip")

                if os.path.exists(kotlin_script) and not platform_id.value.startswith("win-"):
                    os.chmod(
                        kotlin_script,
                        stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH,
                    )

            if not os.path.exists(kotlin_script):
                raise FileNotFoundError(f"Kotlin Language Server script not found at {kotlin_script}")

            log.info(f"Using Kotlin Language Server script at {kotlin_script}")
            return kotlin_script

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "--stdio"]

        def create_launch_command_env(self) -> dict[str, str]:
            """Provides JAVA_HOME and JVM options for the Kotlin Language Server process."""
            env: dict[str, str] = {}

            if self._java_home_path is not None:
                env["JAVA_HOME"] = self._java_home_path

            # Get JVM options from settings or use default
            # Note: an explicit empty string means "no JVM options", which is distinct from not setting the key
            _sentinel = object()
            custom_jvm_options = self._custom_settings.get("jvm_options", _sentinel)
            if custom_jvm_options is not _sentinel:
                jvm_options = custom_jvm_options
            else:
                jvm_options = DEFAULT_KOTLIN_JVM_OPTIONS

            env["JAVA_TOOL_OPTIONS"] = jvm_options
            return env

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
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
            "trace": "off",
            "processId": os.getpid(),
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
        Starts the Kotlin Language Server
        """

        def execute_client_command_handler(params: dict) -> list:
            return []

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def work_done_progress_create(params: dict) -> dict:
            """Handle window/workDoneProgress/create: the server is about to report async progress.
            Clear the indexing-complete event so _start_server waits until all tokens finish.
            This is triggered by newer KLS versions (261+) that index asynchronously after initialized.
            Older versions (0.253.x) never send this, so _indexing_complete stays set and wait() returns instantly.
            """
            token = str(params.get("token", ""))
            log.debug(f"Kotlin LSP workDoneProgress/create: token={token!r}")
            with self._progress_lock:
                self._active_progress_tokens.add(token)
                self._indexing_complete.clear()
            return {}

        def progress_handler(params: dict) -> None:
            """Track $/progress begin/end to detect when all async indexing work finishes."""
            token = str(params.get("token", ""))
            value = params.get("value", {})
            kind = value.get("kind")
            if kind == "begin":
                title = value.get("title", "")
                log.info(f"Kotlin LSP progress [{token}]: started - {title}")
                with self._progress_lock:
                    self._active_progress_tokens.add(token)
                    self._indexing_complete.clear()
            elif kind == "report":
                pct = value.get("percentage")
                msg = value.get("message", "")
                pct_str = f" ({pct}%)" if pct is not None else ""
                log.debug(f"Kotlin LSP progress [{token}]: {msg}{pct_str}")
            elif kind == "end":
                msg = value.get("message", "")
                log.info(f"Kotlin LSP progress [{token}]: ended - {msg}")
                with self._progress_lock:
                    self._active_progress_tokens.discard(token)
                    if not self._active_progress_tokens:
                        self._indexing_complete.set()

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_request("window/workDoneProgress/create", work_done_progress_create)
        self.server.on_notification("$/progress", progress_handler)
        self.server.on_notification("$/logTrace", do_nothing)
        self.server.on_notification("$/cancelRequest", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)

        log.info("Starting Kotlin server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
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

        # Wait for any async indexing to complete.
        # - Older KLS (0.253.x): indexing is synchronous inside `initialize`, no $/progress is sent,
        #   _indexing_complete stays SET -> wait() returns immediately.
        # - Newer KLS (261+): server sends window/workDoneProgress/create after initialized,
        #   which clears the event; wait() blocks until all progress tokens end.
        _INDEXING_TIMEOUT = 120.0
        log.info("Waiting for Kotlin LSP indexing to complete (if async)...")
        if self._indexing_complete.wait(timeout=_INDEXING_TIMEOUT):
            log.info("Kotlin LSP ready")
        else:
            log.warning("Kotlin LSP did not signal indexing completion within %.0fs; proceeding anyway", _INDEXING_TIMEOUT)

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        """Small safety buffer since we already waited for indexing to complete in _start_server."""
        return 1.0
