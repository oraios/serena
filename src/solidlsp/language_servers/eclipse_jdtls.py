"""
Provides Java specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Java.
"""

import dataclasses
import logging
import os
import pathlib
import shutil
import threading
import uuid
from pathlib import PurePath
from time import sleep
from typing import cast

from overrides import override

from solidlsp import ls_types
from solidlsp.ls import LanguageServerDependencyProvider, LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_types import UnifiedSymbolInformation
from solidlsp.ls_utils import FileUtils, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import DocumentSymbol, InitializeParams, SymbolInformation
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


@dataclasses.dataclass
class RuntimeDependencyPaths:
    """
    Stores the paths to the runtime dependencies of EclipseJDTLS
    """

    gradle_path: str
    lombok_jar_path: str
    jre_path: str
    jre_home_path: str
    jdtls_launcher_jar_path: str
    jdtls_readonly_config_path: str
    intellicode_jar_path: str
    intellisense_members_path: str


class EclipseJDTLS(SolidLanguageServer):
    r"""
    The EclipseJDTLS class provides a Java specific implementation of the LanguageServer class

    You can configure the following options in ls_specific_settings (in serena_config.yml):
        - maven_user_settings: Path to Maven settings.xml file (default: ~/.m2/settings.xml)
        - gradle_user_home: Path to Gradle user home directory (default: ~/.gradle)

    Note: Gradle wrapper is disabled by default. Projects will use the bundled Gradle distribution.

    Example configuration in ~/.serena/serena_config.yml:
    ```yaml
    ls_specific_settings:
      java:
        maven_user_settings: "/home/user/.m2/settings.xml"  # Unix/Linux/Mac
        # maven_user_settings: 'C:\\Users\\YourName\\.m2\\settings.xml'  # Windows (use single quotes!)
        gradle_user_home: "/home/user/.gradle"  # Unix/Linux/Mac
        # gradle_user_home: 'C:\\Users\\YourName\\.gradle'  # Windows (use single quotes!)
    ```
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a new EclipseJDTLS instance initializing the language server settings appropriately.
        This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        super().__init__(config, repository_root_path, None, "java", solidlsp_settings)

        # Extract runtime_dependency_paths from the dependency provider
        assert isinstance(self._dependency_provider, self.DependencyProvider)
        self.runtime_dependency_paths = self._dependency_provider.runtime_dependency_paths

        self._service_ready_event = threading.Event()
        self._project_ready_event = threading.Event()
        self._intellicode_enable_command_available = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        ls_resources_dir = self.ls_resources_dir(self._solidlsp_settings)
        return self.DependencyProvider(self._custom_settings, ls_resources_dir, self._solidlsp_settings, self.repository_root_path)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # Ignore common Java build directories from different build tools:
        # - Maven: target
        # - Gradle: build, .gradle
        # - Eclipse: bin, .settings
        # - IntelliJ IDEA: out, .idea
        # - General: classes, dist, lib
        return super().is_ignored_dirname(dirname) or dirname in [
            "target",  # Maven
            "build",  # Gradle
            "bin",  # Eclipse
            "out",  # IntelliJ IDEA
            "classes",  # General
            "dist",  # General
            "lib",  # General
        ]

    class DependencyProvider(LanguageServerDependencyProvider):
        def __init__(
            self,
            custom_settings: SolidLSPSettings.CustomLSSettings,
            ls_resources_dir: str,
            solidlsp_settings: SolidLSPSettings,
            repository_root_path: str,
        ):
            super().__init__(custom_settings, ls_resources_dir)
            self._solidlsp_settings = solidlsp_settings
            self._repository_root_path = repository_root_path
            self.runtime_dependency_paths = self._setup_runtime_dependencies(ls_resources_dir)

        @classmethod
        def _setup_runtime_dependencies(cls, ls_resources_dir: str) -> RuntimeDependencyPaths:
            """
            Setup runtime dependencies for EclipseJDTLS and return the paths.
            """
            platformId = PlatformUtils.get_platform_id()

            runtime_dependencies = {
                "gradle": {
                    "platform-agnostic": {
                        "url": "https://services.gradle.org/distributions/gradle-8.14.2-bin.zip",
                        "archiveType": "zip",
                        "relative_extraction_path": ".",
                    }
                },
                "vscode-java": {
                    "darwin-arm64": {
                        "url": "https://github.com/redhat-developer/vscode-java/releases/download/v1.42.0/java-darwin-arm64-1.42.0-561.vsix",
                        "archiveType": "zip",
                        "relative_extraction_path": "vscode-java",
                    },
                    "osx-arm64": {
                        "url": "https://github.com/redhat-developer/vscode-java/releases/download/v1.42.0/java-darwin-arm64-1.42.0-561.vsix",
                        "archiveType": "zip",
                        "relative_extraction_path": "vscode-java",
                        "jre_home_path": "extension/jre/21.0.7-macosx-aarch64",
                        "jre_path": "extension/jre/21.0.7-macosx-aarch64/bin/java",
                        "lombok_jar_path": "extension/lombok/lombok-1.18.36.jar",
                        "jdtls_launcher_jar_path": "extension/server/plugins/org.eclipse.equinox.launcher_1.7.0.v20250424-1814.jar",
                        "jdtls_readonly_config_path": "extension/server/config_mac_arm",
                    },
                    "osx-x64": {
                        "url": "https://github.com/redhat-developer/vscode-java/releases/download/v1.42.0/java-darwin-x64-1.42.0-561.vsix",
                        "archiveType": "zip",
                        "relative_extraction_path": "vscode-java",
                        "jre_home_path": "extension/jre/21.0.7-macosx-x86_64",
                        "jre_path": "extension/jre/21.0.7-macosx-x86_64/bin/java",
                        "lombok_jar_path": "extension/lombok/lombok-1.18.36.jar",
                        "jdtls_launcher_jar_path": "extension/server/plugins/org.eclipse.equinox.launcher_1.7.0.v20250424-1814.jar",
                        "jdtls_readonly_config_path": "extension/server/config_mac",
                    },
                    "linux-arm64": {
                        "url": "https://github.com/redhat-developer/vscode-java/releases/download/v1.42.0/java-linux-arm64-1.42.0-561.vsix",
                        "archiveType": "zip",
                        "relative_extraction_path": "vscode-java",
                        "jre_home_path": "extension/jre/21.0.7-linux-aarch64",
                        "jre_path": "extension/jre/21.0.7-linux-aarch64/bin/java",
                        "lombok_jar_path": "extension/lombok/lombok-1.18.36.jar",
                        "jdtls_launcher_jar_path": "extension/server/plugins/org.eclipse.equinox.launcher_1.7.0.v20250424-1814.jar",
                        "jdtls_readonly_config_path": "extension/server/config_linux_arm",
                    },
                    "linux-x64": {
                        "url": "https://github.com/redhat-developer/vscode-java/releases/download/v1.42.0/java-linux-x64-1.42.0-561.vsix",
                        "archiveType": "zip",
                        "relative_extraction_path": "vscode-java",
                        "jre_home_path": "extension/jre/21.0.7-linux-x86_64",
                        "jre_path": "extension/jre/21.0.7-linux-x86_64/bin/java",
                        "lombok_jar_path": "extension/lombok/lombok-1.18.36.jar",
                        "jdtls_launcher_jar_path": "extension/server/plugins/org.eclipse.equinox.launcher_1.7.0.v20250424-1814.jar",
                        "jdtls_readonly_config_path": "extension/server/config_linux",
                    },
                    "win-x64": {
                        "url": "https://github.com/redhat-developer/vscode-java/releases/download/v1.42.0/java-win32-x64-1.42.0-561.vsix",
                        "archiveType": "zip",
                        "relative_extraction_path": "vscode-java",
                        "jre_home_path": "extension/jre/21.0.7-win32-x86_64",
                        "jre_path": "extension/jre/21.0.7-win32-x86_64/bin/java.exe",
                        "lombok_jar_path": "extension/lombok/lombok-1.18.36.jar",
                        "jdtls_launcher_jar_path": "extension/server/plugins/org.eclipse.equinox.launcher_1.7.0.v20250424-1814.jar",
                        "jdtls_readonly_config_path": "extension/server/config_win",
                    },
                },
                "intellicode": {
                    "platform-agnostic": {
                        "url": "https://VisualStudioExptTeam.gallery.vsassets.io/_apis/public/gallery/publisher/VisualStudioExptTeam/extension/vscodeintellicode/1.2.30/assetbyname/Microsoft.VisualStudio.Services.VSIXPackage",
                        "alternate_url": "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/VisualStudioExptTeam/vsextensions/vscodeintellicode/1.2.30/vspackage",
                        "archiveType": "zip",
                        "relative_extraction_path": "intellicode",
                        "intellicode_jar_path": "extension/dist/com.microsoft.jdtls.intellicode.core-0.7.0.jar",
                        "intellisense_members_path": "extension/dist/bundledModels/java_intellisense-members",
                    }
                },
            }

            gradle_path = str(
                PurePath(
                    ls_resources_dir,
                    "gradle-8.14.2",
                )
            )

            if not os.path.exists(gradle_path):
                FileUtils.download_and_extract_archive(
                    runtime_dependencies["gradle"]["platform-agnostic"]["url"],
                    str(PurePath(gradle_path).parent),
                    runtime_dependencies["gradle"]["platform-agnostic"]["archiveType"],
                )

            assert os.path.exists(gradle_path)

            dependency = runtime_dependencies["vscode-java"][platformId.value]
            vscode_java_path = str(PurePath(ls_resources_dir, dependency["relative_extraction_path"]))
            os.makedirs(vscode_java_path, exist_ok=True)
            jre_home_path = str(PurePath(vscode_java_path, dependency["jre_home_path"]))
            jre_path = str(PurePath(vscode_java_path, dependency["jre_path"]))
            lombok_jar_path = str(PurePath(vscode_java_path, dependency["lombok_jar_path"]))
            jdtls_launcher_jar_path = str(PurePath(vscode_java_path, dependency["jdtls_launcher_jar_path"]))
            jdtls_readonly_config_path = str(PurePath(vscode_java_path, dependency["jdtls_readonly_config_path"]))
            if not all(
                [
                    os.path.exists(vscode_java_path),
                    os.path.exists(jre_home_path),
                    os.path.exists(jre_path),
                    os.path.exists(lombok_jar_path),
                    os.path.exists(jdtls_launcher_jar_path),
                    os.path.exists(jdtls_readonly_config_path),
                ]
            ):
                FileUtils.download_and_extract_archive(dependency["url"], vscode_java_path, dependency["archiveType"])

            os.chmod(jre_path, 0o755)

            assert os.path.exists(vscode_java_path)
            assert os.path.exists(jre_home_path)
            assert os.path.exists(jre_path)
            assert os.path.exists(lombok_jar_path)
            assert os.path.exists(jdtls_launcher_jar_path)
            assert os.path.exists(jdtls_readonly_config_path)

            dependency = runtime_dependencies["intellicode"]["platform-agnostic"]
            intellicode_directory_path = str(PurePath(ls_resources_dir, dependency["relative_extraction_path"]))
            os.makedirs(intellicode_directory_path, exist_ok=True)
            intellicode_jar_path = str(PurePath(intellicode_directory_path, dependency["intellicode_jar_path"]))
            intellisense_members_path = str(PurePath(intellicode_directory_path, dependency["intellisense_members_path"]))
            if not all(
                [
                    os.path.exists(intellicode_directory_path),
                    os.path.exists(intellicode_jar_path),
                    os.path.exists(intellisense_members_path),
                ]
            ):
                FileUtils.download_and_extract_archive(dependency["url"], intellicode_directory_path, dependency["archiveType"])

            assert os.path.exists(intellicode_directory_path)
            assert os.path.exists(intellicode_jar_path)
            assert os.path.exists(intellisense_members_path)

            return RuntimeDependencyPaths(
                gradle_path=gradle_path,
                lombok_jar_path=lombok_jar_path,
                jre_path=jre_path,
                jre_home_path=jre_home_path,
                jdtls_launcher_jar_path=jdtls_launcher_jar_path,
                jdtls_readonly_config_path=jdtls_readonly_config_path,
                intellicode_jar_path=intellicode_jar_path,
                intellisense_members_path=intellisense_members_path,
            )

        def create_launch_command(self) -> list[str] | str:
            # ws_dir is the workspace directory for the EclipseJDTLS server
            ws_dir = str(
                PurePath(
                    self._solidlsp_settings.ls_resources_dir,
                    "EclipseJDTLS",
                    "workspaces",
                    uuid.uuid4().hex,
                )
            )

            # shared_cache_location is the global cache used by Eclipse JDTLS across all workspaces
            shared_cache_location = str(PurePath(self._solidlsp_settings.ls_resources_dir, "lsp", "EclipseJDTLS", "sharedIndex"))
            os.makedirs(shared_cache_location, exist_ok=True)
            os.makedirs(ws_dir, exist_ok=True)

            jre_path = self.runtime_dependency_paths.jre_path
            lombok_jar_path = self.runtime_dependency_paths.lombok_jar_path

            jdtls_launcher_jar = self.runtime_dependency_paths.jdtls_launcher_jar_path

            data_dir = str(PurePath(ws_dir, "data_dir"))
            jdtls_config_path = str(PurePath(ws_dir, "config_path"))

            jdtls_readonly_config_path = self.runtime_dependency_paths.jdtls_readonly_config_path

            if not os.path.exists(jdtls_config_path):
                shutil.copytree(jdtls_readonly_config_path, jdtls_config_path)

            for static_path in [
                jre_path,
                lombok_jar_path,
                jdtls_launcher_jar,
                jdtls_config_path,
                jdtls_readonly_config_path,
            ]:
                assert os.path.exists(static_path), static_path

            cmd = [
                jre_path,
                "--add-modules=ALL-SYSTEM",
                "--add-opens",
                "java.base/java.util=ALL-UNNAMED",
                "--add-opens",
                "java.base/java.lang=ALL-UNNAMED",
                "--add-opens",
                "java.base/sun.nio.fs=ALL-UNNAMED",
                "-Declipse.application=org.eclipse.jdt.ls.core.id1",
                "-Dosgi.bundles.defaultStartLevel=4",
                "-Declipse.product=org.eclipse.jdt.ls.core.product",
                "-Djava.import.generatesMetadataFilesAtProjectRoot=false",
                "-Dfile.encoding=utf8",
                "-noverify",
                "-XX:+UseParallelGC",
                "-XX:GCTimeRatio=4",
                "-XX:AdaptiveSizePolicyWeight=90",
                "-Dsun.zip.disableMemoryMapping=true",
                "-Djava.lsp.joinOnCompletion=true",
                "-Xmx3G",
                "-Xms100m",
                "-Xlog:disable",
                "-Dlog.level=ALL",
                f"-javaagent:{lombok_jar_path}",
                f"-Djdt.core.sharedIndexLocation={shared_cache_location}",
                "-jar",
                f"{jdtls_launcher_jar}",
                "-configuration",
                f"{jdtls_config_path}",
                "-data",
                f"{data_dir}",
            ]

            return cmd

        def create_launch_command_env(self) -> dict[str, str]:
            return {"syntaxserver": "false", "JAVA_HOME": self.runtime_dependency_paths.jre_home_path}

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize parameters for the EclipseJDTLS server.
        """
        # Look into https://github.com/eclipse/eclipse.jdt.ls/blob/master/org.eclipse.jdt.ls.core/src/org/eclipse/jdt/ls/core/internal/preferences/Preferences.java to understand all the options available

        if not os.path.isabs(repository_absolute_path):
            repository_absolute_path = os.path.abspath(repository_absolute_path)
        repo_uri = pathlib.Path(repository_absolute_path).as_uri()

        # Load user's Maven and Gradle configuration paths from ls_specific_settings["java"]

        # Maven settings: default to ~/.m2/settings.xml
        default_maven_settings_path = os.path.join(os.path.expanduser("~"), ".m2", "settings.xml")
        custom_maven_settings_path = self._custom_settings.get("maven_user_settings")
        if custom_maven_settings_path is not None:
            # User explicitly provided a path
            if not os.path.exists(custom_maven_settings_path):
                error_msg = (
                    f"Provided maven settings file not found: {custom_maven_settings_path}. "
                    f"Fix: create the file, update path in ~/.serena/serena_config.yml (ls_specific_settings -> java -> maven_user_settings), "
                    f"or remove the setting to use default ({default_maven_settings_path})"
                )
                log.error(error_msg)
                raise FileNotFoundError(error_msg)
            maven_settings_path = custom_maven_settings_path
            log.info(f"Using Maven settings from custom location: {maven_settings_path}")
        elif os.path.exists(default_maven_settings_path):
            maven_settings_path = default_maven_settings_path
            log.info(f"Using Maven settings from default location: {maven_settings_path}")
        else:
            maven_settings_path = None
            log.info(f"Maven settings not found at default location ({default_maven_settings_path}), will use JDTLS defaults")

        # Gradle user home: default to ~/.gradle
        default_gradle_home = os.path.join(os.path.expanduser("~"), ".gradle")
        custom_gradle_home = self._custom_settings.get("gradle_user_home")
        if custom_gradle_home is not None:
            # User explicitly provided a path
            if not os.path.exists(custom_gradle_home):
                error_msg = (
                    f"Gradle user home directory not found: {custom_gradle_home}. "
                    f"Fix: create the directory, update path in ~/.serena/serena_config.yml (ls_specific_settings -> java -> gradle_user_home), "
                    f"or remove the setting to use default (~/.gradle)"
                )
                log.error(error_msg)
                raise FileNotFoundError(error_msg)
            gradle_user_home = custom_gradle_home
            log.info(f"Using Gradle user home from custom location: {gradle_user_home}")
        elif os.path.exists(default_gradle_home):
            gradle_user_home = default_gradle_home
            log.info(f"Using Gradle user home from default location: {gradle_user_home}")
        else:
            gradle_user_home = None
            log.info(f"Gradle user home not found at default location ({default_gradle_home}), will use JDTLS defaults")

        initialize_params = {
            "locale": "en",
            "rootPath": repository_absolute_path,
            "rootUri": pathlib.Path(repository_absolute_path).as_uri(),
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
                    # TODO: we have an assert that completion provider is not included in the capabilities at server startup
                    #   Removing this will cause the assert to fail. Investigate why this is the case, simplify config
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
                    },
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                        "hierarchicalDocumentSymbolSupport": True,
                        "tagSupport": {"valueSet": [1]},
                        "labelSupport": True,
                    },
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
                    "typeHierarchy": {"dynamicRegistration": True},
                    "inlineValue": {"dynamicRegistration": True},
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
                    "positionEncodings": ["utf-16"],
                },
                "notebookDocument": {"synchronization": {"dynamicRegistration": True, "executionSummarySupport": True}},
            },
            "initializationOptions": {
                "bundles": ["intellicode-core.jar"],
                "settings": {
                    "java": {
                        "home": None,
                        "jdt": {
                            "ls": {
                                "java": {"home": None},
                                "vmargs": "-XX:+UseParallelGC -XX:GCTimeRatio=4 -XX:AdaptiveSizePolicyWeight=90 -Dsun.zip.disableMemoryMapping=true -Xmx1G -Xms100m -Xlog:disable",
                                "lombokSupport": {"enabled": True},
                                "protobufSupport": {"enabled": True},
                                "androidSupport": {"enabled": True},
                            }
                        },
                        "errors": {"incompleteClasspath": {"severity": "error"}},
                        "configuration": {
                            "checkProjectSettingsExclusions": False,
                            "updateBuildConfiguration": "interactive",
                            "maven": {
                                "userSettings": maven_settings_path,
                                "globalSettings": None,
                                "notCoveredPluginExecutionSeverity": "warning",
                                "defaultMojoExecutionAction": "ignore",
                            },
                            "workspaceCacheLimit": 90,
                            "runtimes": [
                                {"name": "JavaSE-21", "path": "static/vscode-java/extension/jre/21.0.7-linux-x86_64", "default": True}
                            ],
                        },
                        "trace": {"server": "verbose"},
                        "import": {
                            "maven": {
                                "enabled": True,
                                "offline": {"enabled": False},
                                "disableTestClasspathFlag": False,
                            },
                            "gradle": {
                                "enabled": True,
                                "wrapper": {"enabled": False},
                                "version": None,
                                "home": "abs(static/gradle-7.3.3)",
                                "java": {"home": "abs(static/launch_jres/21.0.7-linux-x86_64)"},
                                "offline": {"enabled": False},
                                "arguments": None,
                                "jvmArguments": None,
                                "user": {"home": gradle_user_home},
                                "annotationProcessing": {"enabled": True},
                            },
                            "exclusions": [
                                "**/node_modules/**",
                                "**/.metadata/**",
                                "**/archetype-resources/**",
                                "**/META-INF/maven/**",
                            ],
                            "generatesMetadataFilesAtProjectRoot": False,
                        },
                        # Set updateSnapshots to False to improve performance and avoid unnecessary network calls
                        # Snapshots will only be updated when explicitly requested by the user
                        "maven": {"downloadSources": True, "updateSnapshots": False},
                        "eclipse": {"downloadSources": True},
                        "signatureHelp": {"enabled": True, "description": {"enabled": True}},
                        "hover": {"javadoc": {"enabled": True}},
                        "implementationsCodeLens": {"enabled": True},
                        "format": {
                            "enabled": True,
                            "settings": {"url": None, "profile": None},
                            "comments": {"enabled": True},
                            "onType": {"enabled": True},
                            "insertSpaces": True,
                            "tabSize": 4,
                        },
                        "saveActions": {"organizeImports": False},
                        "project": {
                            "referencedLibraries": ["lib/**/*.jar"],
                            "importOnFirstTimeStartup": "automatic",
                            "importHint": True,
                            "resourceFilters": ["node_modules", "\\.git"],
                            "encoding": "ignore",
                            "exportJar": {"targetPath": "${workspaceFolder}/${workspaceFolderBasename}.jar"},
                        },
                        "contentProvider": {"preferred": None},
                        "autobuild": {"enabled": True},
                        "maxConcurrentBuilds": 1,
                        "selectionRange": {"enabled": True},
                        "showBuildStatusOnStart": {"enabled": "notification"},
                        "server": {"launchMode": "Standard"},
                        "sources": {"organizeImports": {"starThreshold": 99, "staticStarThreshold": 99}},
                        "imports": {"gradle": {"wrapper": {"checksums": []}}},
                        "templates": {"fileHeader": [], "typeComment": []},
                        "references": {"includeAccessors": True, "includeDecompiledSources": True},
                        "typeHierarchy": {"lazyLoad": False},
                        "settings": {"url": None},
                        "symbols": {"includeSourceMethodDeclarations": False},
                        "inlayHints": {"parameterNames": {"enabled": "literals", "exclusions": []}},
                        "codeAction": {"sortMembers": {"avoidVolatileChanges": True}},
                        "compile": {
                            "nullAnalysis": {
                                "nonnull": [
                                    "javax.annotation.Nonnull",
                                    "org.eclipse.jdt.annotation.NonNull",
                                    "org.springframework.lang.NonNull",
                                ],
                                "nullable": [
                                    "javax.annotation.Nullable",
                                    "org.eclipse.jdt.annotation.Nullable",
                                    "org.springframework.lang.Nullable",
                                ],
                                "mode": "automatic",
                            }
                        },
                        "sharedIndexes": {"enabled": "auto", "location": ""},
                        "silentNotification": False,
                        "dependency": {
                            "showMembers": False,
                            "syncWithFolderExplorer": True,
                            "autoRefresh": True,
                            "refreshDelay": 2000,
                            "packagePresentation": "flat",
                        },
                        "help": {"firstView": "auto", "showReleaseNotes": True, "collectErrorLog": False},
                        "test": {"defaultConfig": "", "config": {}},
                    }
                },
            },
            "trace": "verbose",
            "processId": os.getpid(),
            "workspaceFolders": [
                {
                    "uri": repo_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }

        initialize_params["initializationOptions"]["workspaceFolders"] = [repo_uri]  # type: ignore
        bundles = [self.runtime_dependency_paths.intellicode_jar_path]
        initialize_params["initializationOptions"]["bundles"] = bundles  # type: ignore
        initialize_params["initializationOptions"]["settings"]["java"]["configuration"]["runtimes"] = [  # type: ignore
            {"name": "JavaSE-21", "path": self.runtime_dependency_paths.jre_home_path, "default": True}
        ]

        for runtime in initialize_params["initializationOptions"]["settings"]["java"]["configuration"]["runtimes"]:  # type: ignore
            assert "name" in runtime
            assert "path" in runtime
            assert os.path.exists(runtime["path"]), f"Runtime required for eclipse_jdtls at path {runtime['path']} does not exist"

        gradle_settings = initialize_params["initializationOptions"]["settings"]["java"]["import"]["gradle"]  # type: ignore
        gradle_settings["home"] = self.runtime_dependency_paths.gradle_path
        gradle_settings["java"]["home"] = self.runtime_dependency_paths.jre_path
        return cast(InitializeParams, initialize_params)

    def _start_server(self) -> None:
        """
        Starts the Eclipse JDTLS Language Server
        """

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "textDocument/completion":
                    assert registration["registerOptions"]["resolveProvider"] == True
                    assert registration["registerOptions"]["triggerCharacters"] == [
                        ".",
                        "@",
                        "#",
                        "*",
                        " ",
                    ]
                if registration["method"] == "workspace/executeCommand":
                    if "java.intellicode.enable" in registration["registerOptions"]["commands"]:
                        self._intellicode_enable_command_available.set()
            return

        def lang_status_handler(params: dict) -> None:
            log.info("Language status update: %s", params)
            if params["type"] == "ServiceReady" and params["message"] == "ServiceReady":
                self._service_ready_event.set()
            if params["type"] == "ProjectStatus":
                if params["message"] == "OK":
                    self._project_ready_event.set()

        def execute_client_command_handler(params: dict) -> list:
            assert params["command"] == "_java.reloadBundles.command"
            assert params["arguments"] == []
            return []

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("language/status", lang_status_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)

        log.info("Starting EclipseJDTLS server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        assert init_response["capabilities"]["textDocumentSync"]["change"] == 2  # type: ignore
        assert "completionProvider" not in init_response["capabilities"]
        assert "executeCommandProvider" not in init_response["capabilities"]

        self.server.notify.initialized({})

        self.server.notify.workspace_did_change_configuration({"settings": initialize_params["initializationOptions"]["settings"]})  # type: ignore

        self._intellicode_enable_command_available.wait()

        java_intellisense_members_path = self.runtime_dependency_paths.intellisense_members_path
        assert os.path.exists(java_intellisense_members_path)
        intellicode_enable_result = self.server.send.execute_command(
            {
                "command": "java.intellicode.enable",
                "arguments": [True, java_intellisense_members_path],
            }
        )
        assert intellicode_enable_result

        if not self._service_ready_event.is_set():
            log.info("Waiting for service to be ready ...")
            self._service_ready_event.wait()
        log.info("Service is ready")

        if not self._project_ready_event.is_set():
            log.info("Waiting for project to be ready ...")
            project_ready_timeout = 20  # Hotfix: Using timeout until we figure out why sometimes we don't get the project ready event
            if self._project_ready_event.wait(timeout=project_ready_timeout):
                log.info("Project is ready")
            else:
                log.warning("Did not receive project ready status within %d seconds; proceeding anyway", project_ready_timeout)
        else:
            log.info("Project is ready")

        log.info("Startup complete")

    @override
    def _request_hover(self, uri: str, line: int, column: int) -> ls_types.Hover | None:
        # Eclipse JDTLS lazily loads javadocs on first hover request, then caches them.
        # This means the first request often returns incomplete info (just the signature),
        # while subsequent requests return the full javadoc.
        #
        # The response format also differs based on javadoc presence:
        #   - contents: list[...] when javadoc IS present (preferred, richer format)
        #   - contents: {value: info} when javadoc is NOT present
        #
        # There's no LSP signal for "javadoc fully loaded" and no way to request
        # hover with "wait for complete info". The retry approach is the only viable
        # workaround - we keep requesting until we get the richer list format or
        # the content stops growing.
        #
        # The file is kept open by the caller (request_hover), so retries are cheap
        # and don't cause repeated didOpen/didClose cycles.

        def content_score(result: ls_types.Hover | None) -> tuple[int, int]:
            """Return (format_priority, length) for comparison. Higher is better."""
            if result is None:
                return (0, 0)
            contents = result["contents"]
            if isinstance(contents, list):
                return (2, len(contents))  # List format (has javadoc) is best
            elif isinstance(contents, dict):
                return (1, len(contents.get("value", "")))
            else:
                return (1, len(contents))

        max_retries = 5
        best_result = super()._request_hover(uri, line, column)
        best_score = content_score(best_result)

        for _ in range(max_retries):
            sleep(0.05)
            new_result = super()._request_hover(uri, line, column)
            new_score = content_score(new_result)
            if new_score > best_score:
                best_result = new_result
                best_score = new_score

        return best_result

    def _request_document_symbols(
        self, relative_file_path: str, file_data: LSPFileBuffer | None
    ) -> list[SymbolInformation] | list[DocumentSymbol] | None:
        result = super()._request_document_symbols(relative_file_path, file_data=file_data)
        if result is None:
            return None

        # JDTLS sometimes returns symbol names with type information to handle overloads,
        # e.g. "myMethod(int) <T>", but we want overloads to be handled via overload_idx,
        # which requires the name to be just "myMethod".

        def fix_name(symbol: SymbolInformation | DocumentSymbol | UnifiedSymbolInformation) -> None:
            if "(" in symbol["name"]:
                symbol["name"] = symbol["name"][: symbol["name"].index("(")]
            children = symbol.get("children")
            if children:
                for child in children:  # type: ignore
                    fix_name(child)

        for root_symbol in result:
            fix_name(root_symbol)

        return result
