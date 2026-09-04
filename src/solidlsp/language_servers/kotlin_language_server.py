"""
Provides Kotlin specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Kotlin.

You can configure the following options in ls_specific_settings (in serena_config.yml):

    ls_specific_settings:
      kotlin:
        ls_path: '/path/to/bin/intellij-server'  # Custom path to Kotlin Language Server executable
        kotlin_lsp_version: '262.9593.0'  # Kotlin Language Server version (default: current bundled version)
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
from dataclasses import dataclass

import psutil
from overrides import override

from solidlsp.dependency_provider import DownloadedDependency, DownloadedDependencyHashDatabase
from solidlsp.ls import (
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_utils import FileUtils, PlatformId, PlatformUtils
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# Default JVM options for Kotlin Language Server
# -Xmx2G: 2GB heap is sufficient for most projects; override via ls_specific_settings for large codebases
DEFAULT_KOTLIN_JVM_OPTIONS = "-Xmx2G"

KOTLIN_LSP_ALLOWED_HOSTS = ("download-cdn.jetbrains.com",)

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
# NOTE: After changing either pinned version, run scripts/update_downloaded_dependency_hashes.py.
INITIAL_KOTLIN_LSP_VERSION = "261.13587.0"
DEFAULT_KOTLIN_LSP_VERSION = "262.9593.0"

# Versions before this one use kotlin-lsp-{version}-{platform}.zip and a kotlin-lsp script.
# Starting with 262.4739.0, JetBrains publishes kotlin-server archives with platform-specific
# formats, a bundled JBR, and bin/intellij-server as the launcher.
KOTLIN_SERVER_PACKAGING_MIN_VERSION = (262, 4739, 0)

# The first modern archives remained under the legacy /kotlin-lsp CDN path.
# Starting with 262.8190.0, JetBrains moved them to /language-server/kotlin-server.
KOTLIN_SERVER_CDN_PATH_MIN_VERSION = (262, 8190, 0)

# Platform-specific suffixes used by legacy Kotlin LSP ZIP archives.
LEGACY_PLATFORM_KOTLIN_SUFFIX = {
    "win-x64": "win-x64",
    "linux-x64": "linux-x64",
    "linux-arm64": "linux-aarch64",
    "osx-x64": "mac-x64",
    "osx-arm64": "mac-aarch64",
}

# Modern archive filename suffix, FileUtils archive type, and launcher path within the archive.
KOTLIN_SERVER_ARTIFACT_BY_PLATFORM: dict[str, tuple[str, FileUtils.ArchiveType, tuple[str, ...]]] = {
    "win-x64": (".win.zip", "zip", ("bin", "intellij-server.exe")),
    "win-arm64": ("-aarch64.win.zip", "zip", ("bin", "intellij-server.exe")),
    "linux-x64": (".tar.gz", "gztar", ("kotlin-server-{version}", "bin", "intellij-server")),
    "linux-arm64": ("-aarch64.tar.gz", "gztar", ("kotlin-server-{version}", "bin", "intellij-server")),
    "osx-x64": (".sit", "zip", ("kotlin-server-{version}", "bin", "intellij-server")),
    "osx-arm64": ("-aarch64.sit", "zip", ("kotlin-server-{version}", "bin", "intellij-server")),
}


@dataclass(frozen=True)
class KotlinLSPArtifact:
    dependency: DownloadedDependency
    launcher_parts: tuple[str, ...]


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
        self._intellij_server_ready = threading.Event()
        self._active_progress_tokens: set[str] = set()
        self._progress_lock = threading.Lock()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir, str(self.cache_dir))

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def __init__(self, custom_settings: SolidLSPSettings.CustomLSSettings, ls_resources_dir: str, project_cache_dir: str):
            super().__init__(custom_settings, ls_resources_dir)
            self._project_cache_dir = project_cache_dir

        @classmethod
        def _create_artifact(cls, version: str, platform_id: PlatformId) -> KotlinLSPArtifact:
            """Build download and launcher metadata for one Kotlin LSP release.

            JetBrains has three publishing layouts: legacy ZIPs before 262.4739.0,
            modern platform archives under ``/kotlin-lsp`` through 262.7569.0,
            and modern archives under ``/language-server/kotlin-server`` from
            262.8190.0 onward. Serena verifies the frozen initial and current default
            releases; arbitrary user-selected versions are unverified by design.
            """
            try:
                version_parts = tuple(int(part) for part in version.split("."))
            except ValueError as exc:
                raise ValueError(f"Kotlin LSP version must contain only dot-separated integers: {version!r}") from exc

            verified = version in {INITIAL_KOTLIN_LSP_VERSION, DEFAULT_KOTLIN_LSP_VERSION}
            if version_parts >= KOTLIN_SERVER_PACKAGING_MIN_VERSION:
                artifact_config = KOTLIN_SERVER_ARTIFACT_BY_PLATFORM.get(platform_id.value)
                if artifact_config is None:
                    raise ValueError(f"Unsupported platform for Kotlin LSP {version}: {platform_id.value}")

                asset_suffix, archive_type, launcher_parts = artifact_config
                asset_name = f"kotlin-server-{version}{asset_suffix}"
                cdn_path = "language-server/kotlin-server" if version_parts >= KOTLIN_SERVER_CDN_PATH_MIN_VERSION else "kotlin-lsp"
                return KotlinLSPArtifact(
                    dependency=DownloadedDependency(
                        url=f"https://download-cdn.jetbrains.com/{cdn_path}/{version}/{asset_name}",
                        archive_type=archive_type,
                        allowed_hosts=KOTLIN_LSP_ALLOWED_HOSTS,
                        verified=verified,
                    ),
                    launcher_parts=tuple(part.format(version=version) for part in launcher_parts),
                )

            kotlin_suffix = LEGACY_PLATFORM_KOTLIN_SUFFIX.get(platform_id.value)
            if kotlin_suffix is None:
                raise ValueError(f"Unsupported platform for Kotlin LSP {version}: {platform_id.value}")

            return KotlinLSPArtifact(
                dependency=DownloadedDependency(
                    url=f"https://download-cdn.jetbrains.com/kotlin-lsp/{version}/kotlin-lsp-{version}-{kotlin_suffix}.zip",
                    archive_type="zip",
                    allowed_hosts=KOTLIN_LSP_ALLOWED_HOSTS,
                    verified=verified,
                ),
                launcher_parts=("kotlin-lsp.cmd",) if platform_id.is_windows() else ("kotlin-lsp.sh",),
            )

        @classmethod
        def update_dep_hashes(cls) -> None:
            pinned_artifacts = [
                *(cls._create_artifact(INITIAL_KOTLIN_LSP_VERSION, PlatformId(platform)) for platform in LEGACY_PLATFORM_KOTLIN_SUFFIX),
                *(
                    cls._create_artifact(DEFAULT_KOTLIN_LSP_VERSION, PlatformId(platform))
                    for platform in KOTLIN_SERVER_ARTIFACT_BY_PLATFORM
                ),
            ]
            with DownloadedDependencyHashDatabase.get_instance().update_context() as database:
                for artifact in pinned_artifacts:
                    database.update(artifact.dependency)

        def _get_or_install_core_dependency(self) -> str:
            """
            Setup runtime dependencies for Kotlin Language Server and return the path to the executable script.
            """
            platform_id = PlatformUtils.get_platform_id()

            # Setup paths for dependencies; legacy unversioned dir reserved for INITIAL only
            kotlin_lsp_version = self._custom_settings.get("kotlin_lsp_version", DEFAULT_KOTLIN_LSP_VERSION)
            artifact = self._create_artifact(kotlin_lsp_version, platform_id)
            ls_dirname = (
                "kotlin_language_server"
                if kotlin_lsp_version == INITIAL_KOTLIN_LSP_VERSION
                else f"kotlin_language_server-{kotlin_lsp_version}"
            )
            static_dir = os.path.join(self._ls_resources_dir, ls_dirname)
            os.makedirs(static_dir, exist_ok=True)

            # Setup Kotlin Language Server
            kotlin_script = os.path.join(static_dir, *artifact.launcher_parts)

            if not os.path.exists(kotlin_script):
                log.info("Downloading Kotlin Language Server...")
                artifact.dependency.download_to(static_dir)

                if os.path.exists(kotlin_script) and not platform_id.is_windows():
                    os.chmod(
                        kotlin_script,
                        stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH,
                    )

            if not os.path.exists(kotlin_script):
                raise FileNotFoundError(f"Kotlin Language Server script not found at {kotlin_script}")

            log.info(f"Using Kotlin Language Server script at {kotlin_script}")
            return kotlin_script

        def _create_launch_command(self, core_path: str) -> list[str]:
            command = [core_path, "--stdio"]
            # A custom ls_path is independent of Serena's managed version. Select
            # arguments from the actual launcher so existing kotlin-lsp.sh/.cmd
            # configurations do not inherit IntelliJ-server-only options.
            platform_id = PlatformUtils.get_platform_id()
            intellij_launcher_name = "intellij-server.exe" if platform_id.is_windows() else "intellij-server"
            if os.path.basename(core_path).lower() == intellij_launcher_name:
                command.extend(["--system-path", os.path.join(self._project_cache_dir, "kotlin-lsp-system")])
            return command

        def create_launch_command_env(self) -> dict[str, str]:
            """Provides JVM options for the Kotlin Language Server process."""
            env: dict[str, str] = {}

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

    def _create_base_initialize_params(self) -> dict:
        """
        Returns the initialize params for the Kotlin Language Server.
        """
        root_uri = pathlib.Path(self.repository_root_path).as_uri()
        initialize_params = {
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
        }
        return initialize_params

    def _start_server(self) -> None:
        """
        Starts the Kotlin Language Server
        """
        self._intellij_server_ready.clear()

        def execute_client_command_handler(params: dict) -> list:
            return []

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def intellij_server_ready(_params: dict | None) -> None:
            """Mark the modern IntelliJ-based server ready after its startup/import phase."""
            log.info("Kotlin IntelliJ language server reported that it is ready")
            self._intellij_server_ready.set()

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
        # We advertise `refreshSupport` for these features in the client
        # capabilities above, so the server is entitled to send the matching
        # refresh requests. Without a handler the client answers
        # `MethodNotFound`, which the Kotlin LSP treats as fatal and shuts
        # itself down, taking any in-flight request with it.
        self.server.on_request("workspace/diagnostic/refresh", do_nothing)
        self.server.on_request("workspace/inlayHint/refresh", do_nothing)
        self.server.on_request("workspace/inlineValue/refresh", do_nothing)
        self.server.on_request("workspace/semanticTokens/refresh", do_nothing)
        self.server.on_request("workspace/codeLens/refresh", do_nothing)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("window/showMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_request("workspace/diagnostic/refresh", do_nothing)
        self.server.on_request("window/workDoneProgress/create", work_done_progress_create)
        self.server.on_notification("$/progress", progress_handler)
        self.server.on_notification("intellij/ready-for-test", intellij_server_ready)
        self.server.on_notification("$/logTrace", do_nothing)
        self.server.on_notification("$/cancelRequest", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)

        log.info("Starting Kotlin server process")
        self.server.start()
        initialize_params = self._create_initialize_params()

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        capabilities = init_response["capabilities"]
        server_info = init_response.get("serverInfo", {})
        wait_for_intellij_ready = isinstance(server_info, dict) and server_info.get("name") == "IntelliJ Language Server by JetBrains"
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

        # Wait for workspace import and async indexing to complete.
        # - Older KLS (0.253.x): indexing is synchronous inside `initialize`, no $/progress is sent,
        #   _indexing_complete stays SET -> wait() returns immediately.
        # - Newer KLS (261+): server sends window/workDoneProgress/create after initialized,
        #   which clears the event; wait() blocks until all progress tokens end.
        # - IntelliJ-based KLS (262.4739+): server sends intellij/ready-for-test after
        #   its workspace import and indexing phase completes.
        _INDEXING_TIMEOUT = 120.0
        log.info("Waiting for Kotlin LSP indexing to complete (if async)...")
        ready_event = self._intellij_server_ready if wait_for_intellij_ready else self._indexing_complete
        if ready_event.wait(timeout=_INDEXING_TIMEOUT):
            log.info("Kotlin LSP ready")
        else:
            log.warning("Kotlin LSP did not signal indexing completion within %.0fs; proceeding anyway", _INDEXING_TIMEOUT)

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        """Small safety buffer since we already waited for indexing to complete in _start_server."""
        return 1.0

    @override
    def stop(self, shutdown_timeout: float = 2.0) -> None:
        assert isinstance(self._dependency_provider, self.DependencyProvider)
        java_home = self._dependency_provider._java_home_path
        assert java_home is not None
        super().stop(shutdown_timeout=shutdown_timeout)
        self._kill_gradle_daemons(java_home)

    @staticmethod
    def _kill_gradle_daemons(java_home: str) -> None:
        """Kill Gradle daemons spawned by KLS during project indexing.

        KLS triggers Gradle during indexing, which spawns persistent daemon processes that
        outlive the KLS process (3-hour idle timeout, ~500MB RSS each). These daemons are
        not children of KLS and are invisible to normal process-tree cleanup.

        We identify them by matching the java executable in their command line against
        the JAVA_HOME used by this KLS instance.
        """
        java_bin_resolved = os.path.realpath(os.path.join(java_home, "bin", "java"))

        killed: list[psutil.Process] = []
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmdline = proc.info["cmdline"]
                if not cmdline:
                    continue
                if not any("GradleDaemon" in arg for arg in cmdline):
                    continue
                # cmdline[0] is the java binary path used to start the daemon
                if os.path.realpath(cmdline[0]) == java_bin_resolved:
                    log.info("Terminating Gradle daemon (PID %d) spawned by KLS", proc.pid)
                    proc.terminate()
                    killed.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        if killed:
            _, alive = psutil.wait_procs(killed, timeout=5)
            for proc in alive:
                log.warning("Gradle daemon (PID %d) did not terminate gracefully, killing", proc.pid)
                try:
                    proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
