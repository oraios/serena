"""
Provides Java specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Java.
"""

import dataclasses
import hashlib
import logging
import os
import pathlib
import platform
import re
import shutil
import subprocess
import threading
from pathlib import Path, PurePath
from time import sleep
from typing import cast

from overrides import override

from solidlsp import ls_types
from solidlsp.ls import LanguageServerDependencyProvider, LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_types import UnifiedSymbolInformation
from solidlsp.ls_utils import FileUtils, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import DocumentSymbol, InitializeParams, SymbolInformation
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

GRADLE_ALLOWED_HOSTS = ("services.gradle.org", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")
GRADLE_SHA256 = "7197a12f450794931532469d4ff21a59ea2c1cd59a3ec3f89c035c3c420a6999"
VSCODE_JAVA_ALLOWED_HOSTS = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")
INTELLICODE_ALLOWED_HOSTS = (
    "visualstudioexptteam.gallery.vsassets.io",
    "marketplace.visualstudio.com",
    "download.visualstudio.microsoft.com",
)


# Version pinning convention (read this before bumping anything below):
#
#   INITIAL_* — the very first version we shipped runtime-dependency support for, paired with
#       its SHA. NEVER edited. The legacy unversioned install directory (e.g. "vscode-java/")
#       is reserved exclusively for this version, so users who installed under the original
#       layout keep their existing cache forever.
#
#   DEFAULT_* — the version (and matching SHA) used when the user does not override via
#       custom_settings. THIS is what we edit to upgrade: copy the new version + new SHA over
#       the existing DEFAULT_* literals, leave INITIAL_* alone.
#
# Resolution at install time:
#   resolved_version = custom_settings.get("..._version", DEFAULT_*_VERSION)
#   - resolved == INITIAL_*  -> legacy unversioned dir,           SHA = INITIAL_*_SHA256
#   - resolved == DEFAULT_*  -> versioned dir "{name}-{resolved}", SHA = DEFAULT_*_SHA256
#   - any other version      -> versioned dir "{name}-{resolved}", SHA verification skipped
#
# Consequences of this scheme:
#   - Bumping DEFAULT_* makes new installs land in a new versioned subdir => no silent reuse
#     of stale binaries (the bug this scheme exists to fix).
#   - Previously-downloaded versions are not lost: a user can request any past version via
#     custom_settings and the matching cached subdir is picked up without re-downloading.
#   - INITIAL_* and DEFAULT_* hold identical literals when first introduced; they diverge on
#     the first DEFAULT_* bump and stay independent thereafter.
@dataclasses.dataclass(frozen=True)
class VsixResourcePaths:
    """
    Paths to resources inside the vscode-java VSIX archive. These vary between vscode-java
    releases (JRE bundle, Lombok jar, Equinox launcher all have versioned filenames inside
    the VSIX), so we pin them per-version alongside SHA256 — bumping the VSIX version means
    bumping these too. Without this, a user requesting a non-DEFAULT pinned version would
    extract the right archive but then crash on FileNotFoundError trying to find the wrong
    JRE / Lombok / launcher inside it.
    """

    jre_version: str  # e.g. "21.0.7"; expanded to extension/jre/{jre_version}-{platform-suffix}
    lombok_jar_basename: str  # e.g. "lombok-1.18.36.jar"
    equinox_launcher_basename: str  # e.g. "org.eclipse.equinox.launcher_1.7.0.v20250424-1814.jar"


INITIAL_VSCODE_JAVA_VERSION = "1.42.0-561"
INITIAL_VSCODE_JAVA_SHA256_BY_PLATFORM = {
    "osx-arm64": "bc00c2699d4b8d478eb9a1621db9d6d3a12ea0dcc247a9cd8040e8ac19c03933",
    "osx-x64": "03ae1db1a22c15561a620f1b722d6797d35d4faaa7c4666dbe6ca2715089852f",
    "linux-arm64": "e15bc9b2a665d3453203402621b5441062aa41b0ec2d140661f439326fd248c1",
    "linux-x64": "7660b7b527be6fda46a917966b34d828e7416d5cc84287b29b88e7b99c1737f9",
    "win-x64": "ef195b45bd260976ad2e84618f4044b5d7248deed41d647573f0ee22c4233df3",
}
INITIAL_VSCODE_JAVA_PATHS = VsixResourcePaths(
    jre_version="21.0.7",
    lombok_jar_basename="lombok-1.18.36.jar",
    equinox_launcher_basename="org.eclipse.equinox.launcher_1.7.0.v20250424-1814.jar",
)
# Bumped from 1.42.0-561 to surface Lombok-generated methods (#1432); brings JDTLS commit b2d8952
# (java.symbols.includeGeneratedCode), JRE 21.0.10, Lombok 1.18.39 and Equinox launcher 1.7.100.
DEFAULT_VSCODE_JAVA_VERSION = "1.54.0-923"
DEFAULT_VSCODE_JAVA_SHA256_BY_PLATFORM = {
    "osx-arm64": "c54c45cb0d2579d8e0a4ddeb24d4a9dd0b460d07d9366adea2b38a1da22a463c",
    "osx-x64": "dfc98abc4e54165a78372e280242a039671729b1b03420608df3b10c6b629fb6",
    "linux-arm64": "e2bb22c427d90da8dbb1afff72ff1e2dce38d50b76deb02d7bc313a330a1330c",
    "linux-x64": "9d4b15da54e25a0192f9bac073f086c015397d3676623b68dbf83a5dbaf5132b",
    "win-x64": "66f3914987edeccfee8a2558470e0fde4f8c4154232ff4baa5d73373ebc819d4",
}
DEFAULT_VSCODE_JAVA_PATHS = VsixResourcePaths(
    jre_version="21.0.10",
    lombok_jar_basename="lombok-1.18.39-4050.jar",
    equinox_launcher_basename="org.eclipse.equinox.launcher_1.7.100.v20251111-0406.jar",
)

INITIAL_INTELLICODE_VERSION = "1.2.30"
INITIAL_INTELLICODE_SHA256 = "7f61a7f96d101cdf230f96821be3fddd8f890ebfefb3695d18beee43004ae251"
DEFAULT_INTELLICODE_VERSION = "1.2.30"
DEFAULT_INTELLICODE_SHA256 = "7f61a7f96d101cdf230f96821be3fddd8f890ebfefb3695d18beee43004ae251"

# Mapping from Serena's platform identifiers to upstream JDTLS config_<platform> directory names
JDTLS_CONFIG_DIR_BY_PLATFORM = {
    "osx-arm64": "config_mac_arm",
    "darwin-arm64": "config_mac_arm",
    "osx-x64": "config_mac",
    "linux-arm64": "config_linux_arm",
    "linux-x64": "config_linux",
    "win-x64": "config_win",
}

# Minimum supported JDK version for running JDTLS itself
JDTLS_MIN_JDK_VERSION = 21


@dataclasses.dataclass
class RuntimeDependencyPaths:
    """
    Stores the paths to the runtime dependencies of EclipseJDTLS.

    In the default mode (vscode-java VSIX), all paths are populated.
    In the upstream-jdtls mode (when ``jdtls_path`` and ``lombok_path`` are set),
    fields that have no upstream equivalent (gradle distribution, IntelliCode bundle)
    are set to None.
    """

    jre_path: str
    jre_home_path: str
    jdtls_launcher_jar_path: str
    jdtls_readonly_config_path: str
    lombok_jar_path: str
    gradle_path: str | None = None
    intellicode_jar_path: str | None = None
    intellisense_members_path: str | None = None


class EclipseJDTLS(SolidLanguageServer):
    r"""
    The EclipseJDTLS class provides a Java specific implementation of the LanguageServer class

    Two installation modes are supported:

    1. **Default vscode-java VSIX mode** (no extra config required) — Serena downloads the platform-specific
       vscode-java VSIX bundle (~500 MB: JDTLS + bundled JRE 21 + Lombok + IntelliCode), Gradle distribution
       and IntelliCode VSIX from public hosts. Suitable when public network access is available.

    2. **Upstream JDTLS mode** (activated by setting both ``jdtls_path`` and ``lombok_path``) — uses an
       existing JDTLS installation and the system JDK. Nothing is downloaded. Suitable for restricted-network
       environments. Requires JDK 21+ available via ``java_home`` setting / ``JAVA_HOME`` env / PATH.
       Maven projects work out of the box (m2e bundled in JDTLS uses Maven Embedder); Gradle projects
       need ``./gradlew`` in the project or a system-installed Gradle (Buildship default discovery).

    You can configure the following options in ls_specific_settings (in serena_config.yml):
        Upstream JDTLS mode (mutually exclusive group — set both to activate):
        - jdtls_path: Path to upstream JDTLS root (containing plugins/ and config_<platform>/).
                       Get via 'brew install jdtls' or extract jdt-language-server-*.tar.gz from
                       https://download.eclipse.org/jdtls/snapshots/.
        - lombok_path: Path to lombok jar (e.g. ~/.m2/repository/org/projectlombok/lombok/<ver>/lombok-<ver>.jar
                       or download from https://projectlombok.org/downloads/).

        Optional in upstream-jdtls mode:
        - java_home: Path to JDK 21+ home directory. Falls back to JAVA_HOME env, then 'which java'.

        General settings (apply in both modes):
        - maven_user_settings: Path to Maven settings.xml file (default: ~/.m2/settings.xml)
        - gradle_user_home: Path to Gradle user home directory (default: ~/.gradle)
        - gradle_wrapper_enabled: Whether to use the project's Gradle wrapper (default: false)
        - gradle_java_home: Path to JDK for Gradle (default: null, uses bundled JRE)
        - use_system_java_home: Whether to use the system's JAVA_HOME for JDTLS itself (default: false)
        - jdtls_xmx: Maximum heap size for the JDTLS server JVM (default: "3G")
        - jdtls_xms: Initial heap size for the JDTLS server JVM (default: "100m")
        - intellicode_xmx: Maximum heap size for the IntelliCode embedded JVM (default: "1G")
        - intellicode_xms: Initial heap size for the IntelliCode embedded JVM (default: "100m")
        - lombok_show_generated: Show Lombok-generated methods (getX/setX/builder()/...) in document
              symbols by sending java.symbols.includeGeneratedCode=true to JDTLS (default: true).
              Set to false for @Data-heavy projects where the extra getters/setters are noise.
              Requires JDTLS commit b2d8952+ (vscode-java >= 1.53.0); older servers ignore the
              key silently. See eclipse-jdtls/eclipse.jdt.ls#3706 and serena #1432.
        - gradle_version: Override the pinned Gradle distribution version downloaded by Serena
        - vscode_java_version: Override the pinned vscode-java runtime bundle version downloaded by Serena.
              Pinned versions: "1.54.0-923" (default) and "1.42.0-561" (legacy / initial). Other versions
              are not supported in default VSIX mode (the resource paths inside the archive change between
              releases); use upstream-jdtls mode for arbitrary versions.
        - intellicode_version: Override the pinned IntelliCode VSIX version downloaded by Serena

    Example configuration for upstream JDTLS mode (no downloads, suitable for offline/corporate):
    ```yaml
    ls_specific_settings:
      java:
        jdtls_path: "/opt/homebrew/Cellar/jdtls/1.50.0/libexec"  # or extracted tar.gz path
        lombok_path: "/Users/me/.m2/repository/org/projectlombok/lombok/1.18.36/lombok-1.18.36.jar"
        # java_home: "/opt/homebrew/opt/openjdk@21"  # optional, JAVA_HOME env / PATH used otherwise
    ```

    Example configuration for default vscode-java VSIX mode (auto-download):
    ```yaml
    ls_specific_settings:
      java:
        maven_user_settings: "/home/user/.m2/settings.xml"  # Unix/Linux/Mac
        # maven_user_settings: 'C:\\Users\\YourName\\.m2\\settings.xml'  # Windows (use single quotes!)
        gradle_user_home: "/home/user/.gradle"  # Unix/Linux/Mac
        # gradle_user_home: 'C:\\Users\\YourName\\.gradle'  # Windows (use single quotes!)
        gradle_wrapper_enabled: true  # set to true for projects with custom plugins/repositories
        gradle_java_home: "/path/to/jdk"  # set to override Gradle's JDK
        use_system_java_home: true  # set to true to use system JAVA_HOME for JDTLS
        jdtls_xmx: "3G"  # maximum heap size for the JDTLS server JVM
        jdtls_xms: "100m"  # initial heap size for the JDTLS server JVM
        intellicode_xmx: "1G"  # maximum heap size for the IntelliCode embedded JVM
        intellicode_xms: "100m"  # initial heap size for the IntelliCode embedded JVM
        lombok_show_generated: true  # show Lombok-generated methods in document symbols (default true)
        gradle_version: "8.14.2"
        vscode_java_version: "1.54.0-923"  # also accepts pinned legacy "1.42.0-561"
        intellicode_version: "1.2.30"
    ```
    """

    @classmethod
    def supports_implementation_request(cls) -> bool:
        return True

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
            self.runtime_dependency_paths = self._setup_runtime_dependencies(ls_resources_dir, custom_settings)

        @staticmethod
        def _setup_runtime_dependencies(
            ls_resources_dir: str, custom_settings: SolidLSPSettings.CustomLSSettings
        ) -> RuntimeDependencyPaths:
            """
            Setup runtime dependencies for EclipseJDTLS and return the paths.

            Two modes are supported:

            * **Upstream JDTLS mode** (activated when both ``jdtls_path`` and ``lombok_path`` are set
              in ``ls_specific_settings.java``): uses an existing JDTLS installation (e.g. via
              ``brew install jdtls`` or extracted ``jdt-language-server-*.tar.gz``) and the system JDK.
              Nothing is downloaded by Serena. Suitable for restricted-network/corporate environments.
            * **Default vscode-java VSIX mode** (activated otherwise): downloads the platform-specific
              vscode-java VSIX bundle (containing JDTLS, bundled JRE 21, Lombok, IntelliCode), Gradle
              distribution and IntelliCode VSIX from public hosts. Original behaviour, unchanged.
            """
            jdtls_path = custom_settings.get("jdtls_path")
            lombok_path = custom_settings.get("lombok_path")
            if jdtls_path or lombok_path:
                # both must be set together to activate upstream mode
                if not (jdtls_path and lombok_path):
                    raise SolidLSPException(
                        "Both 'jdtls_path' and 'lombok_path' must be set together in "
                        "ls_specific_settings.java to use the upstream JDTLS mode. "
                        "Set both, or remove both to use the default vscode-java VSIX mode."
                    )
                return EclipseJDTLS.DependencyProvider._setup_from_existing_install(str(jdtls_path), str(lombok_path), custom_settings)

            platformId = PlatformUtils.get_platform_id()
            gradle_version = custom_settings.get("gradle_version", "8.14.2")
            vscode_java_version = custom_settings.get("vscode_java_version", DEFAULT_VSCODE_JAVA_VERSION)
            vscode_java_tag = f"v{vscode_java_version.rsplit('-', 1)[0]}"
            intellicode_version = custom_settings.get("intellicode_version", DEFAULT_INTELLICODE_VERSION)
            default_gradle_version = gradle_version == "8.14.2"

            # install-dir name per the version-pinning convention (see module-level block):
            # INITIAL -> legacy unversioned dir; everything else -> "{name}-{resolved}" subdir
            vscode_java_dirname = (
                "vscode-java" if vscode_java_version == INITIAL_VSCODE_JAVA_VERSION else f"vscode-java-{vscode_java_version}"
            )
            intellicode_dirname = (
                "intellicode" if intellicode_version == INITIAL_INTELLICODE_VERSION else f"intellicode-{intellicode_version}"
            )

            # SHA is only known for our two pinned versions (INITIAL and current DEFAULT);
            # for any other user-supplied version we skip verification (returns None)
            def vscode_java_sha(platform_key: str) -> str | None:
                if vscode_java_version == INITIAL_VSCODE_JAVA_VERSION:
                    return INITIAL_VSCODE_JAVA_SHA256_BY_PLATFORM[platform_key]
                if vscode_java_version == DEFAULT_VSCODE_JAVA_VERSION:
                    return DEFAULT_VSCODE_JAVA_SHA256_BY_PLATFORM[platform_key]
                return None

            def intellicode_sha() -> str | None:
                if intellicode_version == INITIAL_INTELLICODE_VERSION:
                    return INITIAL_INTELLICODE_SHA256
                if intellicode_version == DEFAULT_INTELLICODE_VERSION:
                    return DEFAULT_INTELLICODE_SHA256
                return None

            # Resolve internal VSIX paths (JRE / Lombok / launcher filenames). For pinned versions
            # these are known; for any other user-supplied version we bail out — guessing would
            # silently produce broken paths at JDTLS launch time, which is a worse UX than failing
            # fast here with a pointer to upstream-JDTLS mode (which doesn't need pinned paths).
            if vscode_java_version == INITIAL_VSCODE_JAVA_VERSION:
                vsix_paths = INITIAL_VSCODE_JAVA_PATHS
            elif vscode_java_version == DEFAULT_VSCODE_JAVA_VERSION:
                vsix_paths = DEFAULT_VSCODE_JAVA_PATHS
            else:
                raise SolidLSPException(
                    f"Resource paths inside the vscode-java {vscode_java_version} VSIX are not pinned in serena "
                    f"(known: {INITIAL_VSCODE_JAVA_VERSION}, {DEFAULT_VSCODE_JAVA_VERSION}). "
                    f"Either remove the 'vscode_java_version' override (defaults to {DEFAULT_VSCODE_JAVA_VERSION}), "
                    f"or use upstream JDTLS mode by setting both 'jdtls_path' and 'lombok_path' in "
                    f"ls_specific_settings.java (no pinning required)."
                )

            runtime_dependencies: dict[str, dict[str, dict[str, object]]] = {
                "gradle": {
                    "platform-agnostic": {
                        "url": f"https://services.gradle.org/distributions/gradle-{gradle_version}-bin.zip",
                        "archiveType": "zip",
                        "relative_extraction_path": ".",
                        "sha256": GRADLE_SHA256 if default_gradle_version else None,
                        "allowed_hosts": GRADLE_ALLOWED_HOSTS,
                    }
                },
                "vscode-java": {
                    "darwin-arm64": {
                        "url": f"https://github.com/redhat-developer/vscode-java/releases/download/{vscode_java_tag}/java-darwin-arm64-{vscode_java_version}.vsix",
                        "archiveType": "zip",
                        "relative_extraction_path": vscode_java_dirname,
                        "sha256": vscode_java_sha("osx-arm64"),
                        "allowed_hosts": VSCODE_JAVA_ALLOWED_HOSTS,
                    },
                    "osx-arm64": {
                        "url": f"https://github.com/redhat-developer/vscode-java/releases/download/{vscode_java_tag}/java-darwin-arm64-{vscode_java_version}.vsix",
                        "archiveType": "zip",
                        "relative_extraction_path": vscode_java_dirname,
                        "sha256": vscode_java_sha("osx-arm64"),
                        "allowed_hosts": VSCODE_JAVA_ALLOWED_HOSTS,
                        "jre_home_path": f"extension/jre/{vsix_paths.jre_version}-macosx-aarch64",
                        "jre_path": f"extension/jre/{vsix_paths.jre_version}-macosx-aarch64/bin/java",
                        "lombok_jar_path": f"extension/lombok/{vsix_paths.lombok_jar_basename}",
                        "jdtls_launcher_jar_path": f"extension/server/plugins/{vsix_paths.equinox_launcher_basename}",
                        "jdtls_readonly_config_path": "extension/server/config_mac_arm",
                    },
                    "osx-x64": {
                        "url": f"https://github.com/redhat-developer/vscode-java/releases/download/{vscode_java_tag}/java-darwin-x64-{vscode_java_version}.vsix",
                        "archiveType": "zip",
                        "relative_extraction_path": vscode_java_dirname,
                        "sha256": vscode_java_sha("osx-x64"),
                        "allowed_hosts": VSCODE_JAVA_ALLOWED_HOSTS,
                        "jre_home_path": f"extension/jre/{vsix_paths.jre_version}-macosx-x86_64",
                        "jre_path": f"extension/jre/{vsix_paths.jre_version}-macosx-x86_64/bin/java",
                        "lombok_jar_path": f"extension/lombok/{vsix_paths.lombok_jar_basename}",
                        "jdtls_launcher_jar_path": f"extension/server/plugins/{vsix_paths.equinox_launcher_basename}",
                        "jdtls_readonly_config_path": "extension/server/config_mac",
                    },
                    "linux-arm64": {
                        "url": f"https://github.com/redhat-developer/vscode-java/releases/download/{vscode_java_tag}/java-linux-arm64-{vscode_java_version}.vsix",
                        "archiveType": "zip",
                        "relative_extraction_path": vscode_java_dirname,
                        "sha256": vscode_java_sha("linux-arm64"),
                        "allowed_hosts": VSCODE_JAVA_ALLOWED_HOSTS,
                        "jre_home_path": f"extension/jre/{vsix_paths.jre_version}-linux-aarch64",
                        "jre_path": f"extension/jre/{vsix_paths.jre_version}-linux-aarch64/bin/java",
                        "lombok_jar_path": f"extension/lombok/{vsix_paths.lombok_jar_basename}",
                        "jdtls_launcher_jar_path": f"extension/server/plugins/{vsix_paths.equinox_launcher_basename}",
                        "jdtls_readonly_config_path": "extension/server/config_linux_arm",
                    },
                    "linux-x64": {
                        "url": f"https://github.com/redhat-developer/vscode-java/releases/download/{vscode_java_tag}/java-linux-x64-{vscode_java_version}.vsix",
                        "archiveType": "zip",
                        "relative_extraction_path": vscode_java_dirname,
                        "sha256": vscode_java_sha("linux-x64"),
                        "allowed_hosts": VSCODE_JAVA_ALLOWED_HOSTS,
                        "jre_home_path": f"extension/jre/{vsix_paths.jre_version}-linux-x86_64",
                        "jre_path": f"extension/jre/{vsix_paths.jre_version}-linux-x86_64/bin/java",
                        "lombok_jar_path": f"extension/lombok/{vsix_paths.lombok_jar_basename}",
                        "jdtls_launcher_jar_path": f"extension/server/plugins/{vsix_paths.equinox_launcher_basename}",
                        "jdtls_readonly_config_path": "extension/server/config_linux",
                    },
                    "win-x64": {
                        "url": f"https://github.com/redhat-developer/vscode-java/releases/download/{vscode_java_tag}/java-win32-x64-{vscode_java_version}.vsix",
                        "archiveType": "zip",
                        "relative_extraction_path": vscode_java_dirname,
                        "sha256": vscode_java_sha("win-x64"),
                        "allowed_hosts": VSCODE_JAVA_ALLOWED_HOSTS,
                        "jre_home_path": f"extension/jre/{vsix_paths.jre_version}-win32-x86_64",
                        "jre_path": f"extension/jre/{vsix_paths.jre_version}-win32-x86_64/bin/java.exe",
                        "lombok_jar_path": f"extension/lombok/{vsix_paths.lombok_jar_basename}",
                        "jdtls_launcher_jar_path": f"extension/server/plugins/{vsix_paths.equinox_launcher_basename}",
                        "jdtls_readonly_config_path": "extension/server/config_win",
                    },
                },
                "intellicode": {
                    "platform-agnostic": {
                        "url": f"https://VisualStudioExptTeam.gallery.vsassets.io/_apis/public/gallery/publisher/VisualStudioExptTeam/extension/vscodeintellicode/{intellicode_version}/assetbyname/Microsoft.VisualStudio.Services.VSIXPackage",
                        "alternate_url": f"https://marketplace.visualstudio.com/_apis/public/gallery/publishers/VisualStudioExptTeam/vsextensions/vscodeintellicode/{intellicode_version}/vspackage",
                        "archiveType": "zip",
                        "relative_extraction_path": intellicode_dirname,
                        "sha256": intellicode_sha(),
                        "allowed_hosts": INTELLICODE_ALLOWED_HOSTS,
                        "intellicode_jar_path": "extension/dist/com.microsoft.jdtls.intellicode.core-0.7.0.jar",
                        "intellisense_members_path": "extension/dist/bundledModels/java_intellisense-members",
                    }
                },
            }

            gradle_path = str(
                PurePath(
                    ls_resources_dir,
                    f"gradle-{gradle_version}",
                )
            )

            if not os.path.exists(gradle_path):
                gradle_dependency = runtime_dependencies["gradle"]["platform-agnostic"]
                FileUtils.download_and_extract_archive_verified(
                    cast(str, gradle_dependency["url"]),
                    str(PurePath(gradle_path).parent),
                    cast(str, gradle_dependency["archiveType"]),
                    expected_sha256=cast(str | None, gradle_dependency["sha256"]),
                    allowed_hosts=cast(tuple[str, ...], gradle_dependency["allowed_hosts"]),
                )

            assert os.path.exists(gradle_path)

            dependency = runtime_dependencies["vscode-java"][platformId.value]
            vscode_java_path = str(PurePath(ls_resources_dir, cast(str, dependency["relative_extraction_path"])))
            os.makedirs(vscode_java_path, exist_ok=True)
            jre_home_path = str(PurePath(vscode_java_path, cast(str, dependency["jre_home_path"])))
            jre_path = str(PurePath(vscode_java_path, cast(str, dependency["jre_path"])))
            lombok_jar_path = str(PurePath(vscode_java_path, cast(str, dependency["lombok_jar_path"])))
            jdtls_launcher_jar_path = str(PurePath(vscode_java_path, cast(str, dependency["jdtls_launcher_jar_path"])))
            jdtls_readonly_config_path = str(PurePath(vscode_java_path, cast(str, dependency["jdtls_readonly_config_path"])))
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
                FileUtils.download_and_extract_archive_verified(
                    cast(str, dependency["url"]),
                    vscode_java_path,
                    cast(str, dependency["archiveType"]),
                    expected_sha256=cast(str | None, dependency["sha256"]),
                    allowed_hosts=cast(tuple[str, ...], dependency["allowed_hosts"]),
                )

            os.chmod(jre_path, 0o755)

            assert os.path.exists(vscode_java_path)
            assert os.path.exists(jre_home_path)
            assert os.path.exists(jre_path)
            assert os.path.exists(lombok_jar_path)
            assert os.path.exists(jdtls_launcher_jar_path)
            assert os.path.exists(jdtls_readonly_config_path)

            dependency = runtime_dependencies["intellicode"]["platform-agnostic"]
            intellicode_directory_path = str(PurePath(ls_resources_dir, cast(str, dependency["relative_extraction_path"])))
            os.makedirs(intellicode_directory_path, exist_ok=True)
            intellicode_jar_path = str(PurePath(intellicode_directory_path, cast(str, dependency["intellicode_jar_path"])))
            intellisense_members_path = str(PurePath(intellicode_directory_path, cast(str, dependency["intellisense_members_path"])))
            if not all(
                [
                    os.path.exists(intellicode_directory_path),
                    os.path.exists(intellicode_jar_path),
                    os.path.exists(intellisense_members_path),
                ]
            ):
                FileUtils.download_and_extract_archive_verified(
                    cast(str, dependency["url"]),
                    intellicode_directory_path,
                    cast(str, dependency["archiveType"]),
                    expected_sha256=cast(str | None, dependency["sha256"]),
                    allowed_hosts=cast(tuple[str, ...], dependency["allowed_hosts"]),
                )

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

        @staticmethod
        def _setup_from_existing_install(
            jdtls_path: str, lombok_path: str, custom_settings: SolidLSPSettings.CustomLSSettings
        ) -> RuntimeDependencyPaths:
            """
            Builds RuntimeDependencyPaths from an already-installed upstream JDTLS distribution
            and the system-installed JDK. No downloads are performed.

            :param jdtls_path: absolute path to the JDTLS root (containing ``plugins/`` and ``config_<platform>/``)
            :param lombok_path: absolute path to the Lombok jar (mandatory; agent is always attached)
            :param custom_settings: language-server-specific settings from ls_specific_settings.java
            :return: populated RuntimeDependencyPaths with gradle/intellicode fields set to None
            """
            # validate jdtls_path structure (root + plugins dir)
            jdtls_root = Path(jdtls_path)
            if not jdtls_root.is_dir():
                raise SolidLSPException(
                    f"Provided jdtls_path '{jdtls_path}' is not an existing directory.\n"
                    f"Fix: extract jdt-language-server-*.tar.gz from "
                    f"https://download.eclipse.org/jdtls/snapshots/ or run 'brew install jdtls', "
                    f"then set ls_specific_settings.java.jdtls_path to the extracted directory."
                )
            plugins_dir = jdtls_root / "plugins"
            if not plugins_dir.is_dir():
                raise SolidLSPException(
                    f"Invalid jdtls_path '{jdtls_path}': 'plugins/' directory not found.\n"
                    f"Expected upstream JDTLS layout (plugins/, config_<platform>/, features/) at the root. "
                    f"If you pointed at a vscode-java extension, use '<extension>/server' instead."
                )

            # resolve the main equinox launcher jar (excluding platform-specific native fragments)
            launcher_jar = EclipseJDTLS.DependencyProvider._resolve_launcher_jar(plugins_dir)

            # resolve the platform-specific config directory under jdtls_root
            config_dir = EclipseJDTLS.DependencyProvider._resolve_config_dir(jdtls_root)

            # validate lombok jar exists
            if not Path(lombok_path).is_file():
                raise SolidLSPException(
                    f"Provided lombok_path '{lombok_path}' does not exist or is not a file.\n"
                    f"Fix: download lombok jar from https://projectlombok.org/downloads/ or use the one "
                    f"from your local Maven cache (~/.m2/repository/org/projectlombok/lombok/<version>/lombok-<version>.jar)."
                )

            # resolve system JDK (priority: java_home setting -> JAVA_HOME env -> which java),
            # interrogate the JVM for its real java.home and validate version >= 21
            jre_home_path, jre_path = EclipseJDTLS.DependencyProvider._resolve_system_jdk(custom_settings)

            log.info(
                f"Using upstream JDTLS at '{jdtls_path}' with system JDK '{jre_home_path}'. "
                f"Launcher: {launcher_jar.name}; config: {config_dir.name}; lombok: {lombok_path}"
            )

            return RuntimeDependencyPaths(
                jre_path=jre_path,
                jre_home_path=jre_home_path,
                jdtls_launcher_jar_path=str(launcher_jar),
                jdtls_readonly_config_path=str(config_dir),
                lombok_jar_path=lombok_path,
                gradle_path=None,
                intellicode_jar_path=None,
                intellisense_members_path=None,
            )

        @staticmethod
        def _resolve_launcher_jar(plugins_dir: Path) -> Path:
            """
            Locates the main Equinox launcher jar in JDTLS's ``plugins/`` directory, excluding
            platform-specific native fragments like ``org.eclipse.equinox.launcher.cocoa.macosx.*``.

            :return: path to the main launcher jar (e.g. ``org.eclipse.equinox.launcher_1.7.0.v....jar``)
            """
            # main launcher matches: org.eclipse.equinox.launcher_<digit>...jar (single underscore,
            # immediately followed by version digits — fragments have additional dotted segments).
            pattern = re.compile(r"^org\.eclipse\.equinox\.launcher_\d.*\.jar$")
            matches = sorted(p for p in plugins_dir.glob("org.eclipse.equinox.launcher_*.jar") if pattern.match(p.name))
            if not matches:
                raise SolidLSPException(
                    f"No main Equinox launcher jar found in '{plugins_dir}'. "
                    f"Expected file like 'org.eclipse.equinox.launcher_<version>.jar'. "
                    f"Verify the JDTLS extraction is complete and not corrupted."
                )
            # if multiple versions are present (rare), pick the highest by name
            return matches[-1]

        @staticmethod
        def _resolve_config_dir(jdtls_root: Path) -> Path:
            """
            Locates the platform-specific OSGi configuration directory inside the JDTLS root.

            :return: path to ``config_<platform>/`` directory matching the current OS/arch
            """
            platform_id = PlatformUtils.get_platform_id().value
            config_dir_name = JDTLS_CONFIG_DIR_BY_PLATFORM.get(platform_id)
            if config_dir_name is None:
                raise SolidLSPException(
                    f"Unsupported platform '{platform_id}' for upstream JDTLS mode. "
                    f"Supported platforms: {sorted(set(JDTLS_CONFIG_DIR_BY_PLATFORM.values()))}."
                )
            config_dir = jdtls_root / config_dir_name
            if not config_dir.is_dir():
                raise SolidLSPException(
                    f"Config directory '{config_dir}' not found. "
                    f"This JDTLS distribution does not support platform '{platform_id}'. "
                    f"Verify you downloaded the correct tar.gz for your OS/architecture."
                )
            return config_dir

        @staticmethod
        def _resolve_system_jdk(custom_settings: SolidLSPSettings.CustomLSSettings) -> tuple[str, str]:
            """
            Resolves the system-installed JDK home and ``java`` executable, validates the version.

            The ``java`` executable is located by priority: ``java_home`` setting ->
            ``JAVA_HOME`` env var -> ``java`` in PATH. The actual JDK home directory and
            major version are then discovered by querying the JVM itself via
            ``java -XshowSettings:properties -version`` — this is the single source of truth
            and works correctly even when the locator is a system stub (e.g. ``/usr/bin/java``
            on macOS, which delegates to ``/usr/libexec/java_home`` under the hood and does not
            resolve to the real JDK home via simple path traversal).

            :return: (jdk_home_directory, java_executable_path)
            """
            # locate a java executable to interrogate
            java_exe_name = "java.exe" if platform.system() == "Windows" else "java"
            java_exe: str | None = None
            source: str

            if explicit_home := custom_settings.get("java_home"):
                candidate = str(Path(explicit_home) / "bin" / java_exe_name)
                if not os.path.exists(candidate):
                    raise SolidLSPException(
                        f"java_home='{explicit_home}' is invalid: '{candidate}' does not exist. "
                        f"Set ls_specific_settings.java.java_home to a JDK home that contains bin/{java_exe_name}."
                    )
                java_exe = candidate
                source = f"java_home setting ({explicit_home})"
            elif env_home := os.environ.get("JAVA_HOME"):
                candidate = str(Path(env_home) / "bin" / java_exe_name)
                if os.path.exists(candidate):
                    java_exe = candidate
                    source = f"JAVA_HOME env ({env_home})"
                else:
                    log.warning(f"JAVA_HOME='{env_home}' invalid (no '{candidate}'), falling back to PATH.")

            if java_exe is None:
                java_in_path = shutil.which("java")
                if java_in_path is None:
                    raise SolidLSPException(
                        "Could not locate a Java installation for JDTLS. "
                        "Set ls_specific_settings.java.java_home, set JAVA_HOME environment variable, "
                        f"or ensure 'java' is on PATH. Required: JDK {JDTLS_MIN_JDK_VERSION}+."
                    )
                java_exe = java_in_path
                source = f"PATH ({java_in_path})"

            # interrogate the JVM for its real java.home and version (single source of truth)
            real_jdk_home, major_version = EclipseJDTLS.DependencyProvider._inspect_java(java_exe)

            # validate version
            if major_version < JDTLS_MIN_JDK_VERSION:
                raise SolidLSPException(
                    f"JDTLS requires JDK {JDTLS_MIN_JDK_VERSION}+ but '{java_exe}' is JDK {major_version} "
                    f"(located via {source}, java.home={real_jdk_home}). "
                    f"Install a newer JDK and update ls_specific_settings.java.java_home or JAVA_HOME."
                )
            log.info(f"Resolved JDK {major_version} via {source}; java.home={real_jdk_home}; java_exe={java_exe}.")

            # prefer to use bin/java from the *real* JDK home (so JDTLS subprocesses that read JAVA_HOME
            # find a consistent layout); only fall back to the original locator if the real-home variant
            # is missing for some reason.
            real_java = str(Path(real_jdk_home) / "bin" / java_exe_name)
            if os.path.exists(real_java):
                java_exe = real_java

            return real_jdk_home, java_exe

        @staticmethod
        def _inspect_java(java_exe: str) -> tuple[str, int]:
            """
            Runs ``java -XshowSettings:properties -version`` and parses ``java.home`` and the
            major version from the output. This is the most reliable cross-platform way to
            discover the JDK home (works around macOS ``/usr/bin/java`` stub issue).

            :return: (java_home_directory_reported_by_jvm, major_version)
            """
            try:
                # both -XshowSettings:properties and -version write to stderr by convention
                result = subprocess.run(
                    [java_exe, "-XshowSettings:properties", "-version"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise SolidLSPException(f"Failed to run '{java_exe} -XshowSettings:properties -version': {exc}") from exc

            output = (result.stderr or "") + "\n" + (result.stdout or "")

            # parse java.home from "    java.home = /path/to/jdk"
            home_match = re.search(r"java\.home\s*=\s*(.+)", output)
            if not home_match:
                raise SolidLSPException(
                    f"Could not parse java.home from '{java_exe}' output. "
                    f"This usually means '{java_exe}' is not a valid JDK installation. "
                    f"First lines of output: {output.strip().splitlines()[:5]}"
                )
            real_home = home_match.group(1).strip()

            # parse major version from version line: 'openjdk version "21.0.2"' or 'java version "21.0.2"'
            version_match = re.search(r'version "(\d+)(?:\.\d+)*"', output)
            if not version_match:
                raise SolidLSPException(
                    f"Could not parse Java version from '{java_exe}' output. "
                    f"Required: JDK {JDTLS_MIN_JDK_VERSION}+. "
                    f"First lines of output: {output.strip().splitlines()[:5]}"
                )
            major = int(version_match.group(1))
            return real_home, major

        @staticmethod
        def _compute_workspace_hash(
            repository_root_path: str,
            jdtls_launcher_jar_path: str,
            custom_settings: SolidLSPSettings.CustomLSSettings,
        ) -> str:
            """
            Compute the JDTLS workspace directory name.

            The launcher jar path is mixed in so that switching JDTLS versions (default
            vscode-java VSIX bump or upstream install change) lands in a separate ws_dir
            and avoids stale OSGi configs from the previous version blocking startup.

            Exception: legacy default-mode users on INITIAL_VSCODE_JAVA_VERSION keep the
            original ``md5(repository_root_path)`` format. These are users who installed
            under the legacy unversioned ``vscode-java/`` directory (see the version-pinning
            convention at the top of this module) — preserving their hash means existing
            JDTLS workspaces and project caches are reused without a one-time reindex.
            """
            is_legacy_initial = (
                not custom_settings.get("jdtls_path")
                and custom_settings.get("vscode_java_version", DEFAULT_VSCODE_JAVA_VERSION) == INITIAL_VSCODE_JAVA_VERSION
            )
            if is_legacy_initial:
                ws_hash_input = repository_root_path.encode()
            else:
                ws_hash_input = (repository_root_path + "|" + jdtls_launcher_jar_path).encode()
            return hashlib.md5(ws_hash_input).hexdigest()

        def create_launch_command(self) -> list[str]:
            # ws_dir is the workspace directory for the EclipseJDTLS server.
            project_hash = EclipseJDTLS.DependencyProvider._compute_workspace_hash(
                self._repository_root_path,
                self.runtime_dependency_paths.jdtls_launcher_jar_path,
                self._custom_settings,
            )
            ws_dir = str(
                PurePath(
                    self._solidlsp_settings.ls_resources_dir,
                    "EclipseJDTLS",
                    "workspaces",
                    project_hash,
                )
            )

            # shared_cache_location is the global cache used by Eclipse JDTLS across all workspaces
            shared_cache_location = str(PurePath(self._solidlsp_settings.ls_resources_dir, "lsp", "EclipseJDTLS", "sharedIndex"))
            os.makedirs(shared_cache_location, exist_ok=True)
            os.makedirs(ws_dir, exist_ok=True)

            jre_path = self.runtime_dependency_paths.jre_path
            lombok_jar_path = self.runtime_dependency_paths.lombok_jar_path

            jdtls_launcher_jar = self.runtime_dependency_paths.jdtls_launcher_jar_path
            jdtls_xmx = self._custom_settings.get("jdtls_xmx", "3G")
            jdtls_xms = self._custom_settings.get("jdtls_xms", "100m")

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
                f"-Xmx{jdtls_xmx}",
                f"-Xms{jdtls_xms}",
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
            use_system_java_home = self._custom_settings.get("use_system_java_home", False)
            if use_system_java_home:
                system_java_home = os.environ.get("JAVA_HOME")
                if system_java_home:
                    log.info(f"Using system JAVA_HOME for JDTLS: {system_java_home}")
                    return {"syntaxserver": "false", "JAVA_HOME": system_java_home}
                else:
                    log.warning("use_system_java_home is set but JAVA_HOME is not set in environment, falling back to bundled JRE")
            java_home = self.runtime_dependency_paths.jre_home_path
            log.info(f"Using bundled JRE for JDTLS: {java_home}")
            return {"syntaxserver": "false", "JAVA_HOME": java_home}

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

        # IntelliCode JVM settings (used in vmargs for the embedded JVM)
        intellicode_xmx = self._custom_settings.get("intellicode_xmx", "1G")
        intellicode_xms = self._custom_settings.get("intellicode_xms", "100m")

        # Lombok-generated symbols (getX/setX/builder()/equals/hashCode/toString/...): JDTLS filters
        # these out of documentSymbol results by default. Without them, find_symbol/get_symbols_overview
        # return only user-written sources, which breaks navigation around @Data/@Builder/@Getter/@Setter
        # classes. Default to True so agentic workflows can find_symbol -> replace_symbol_body on generated
        # members. Requires JDTLS commit b2d8952 or newer (vscode-java >= 1.53.0, or upstream JDTLS
        # snapshot after 2026-02-24); older servers ignore the unknown preference key silently.
        # See eclipse-jdtls/eclipse.jdt.ls#3706.
        lombok_show_generated = self._custom_settings.get("lombok_show_generated", True)

        # Gradle wrapper: default to False to preserve existing behaviour
        gradle_wrapper_enabled = self._custom_settings.get("gradle_wrapper_enabled", False)
        log.info(
            f"Gradle wrapper {'enabled' if gradle_wrapper_enabled else 'disabled'} (configurable via ls_specific_settings -> java -> gradle_wrapper_enabled)"
        )

        # Gradle Java home: default to None, which means the bundled JRE is used
        gradle_java_home = self._custom_settings.get("gradle_java_home")
        if gradle_java_home is not None:
            if not os.path.exists(gradle_java_home):
                error_msg = (
                    f"Gradle Java home not found: {gradle_java_home}. "
                    f"Fix: update path in ~/.serena/serena_config.yml (ls_specific_settings -> java -> gradle_java_home), "
                    f"or remove the setting to use the bundled JRE"
                )
                log.error(error_msg)
                raise FileNotFoundError(error_msg)
            log.info(f"Using Gradle Java home from custom location: {gradle_java_home}")
        else:
            log.info(f"Using bundled JRE for Gradle: {self.runtime_dependency_paths.jre_path}")

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
                                "vmargs": f"-XX:+UseParallelGC -XX:GCTimeRatio=4 -XX:AdaptiveSizePolicyWeight=90 -Dsun.zip.disableMemoryMapping=true -Xmx{intellicode_xmx} -Xms{intellicode_xms} -Xlog:disable",
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
                            # Placeholder; the real `runtimes` array is overwritten below from
                            # self.runtime_dependency_paths.jre_home_path (works for both default
                            # VSIX mode and upstream-jdtls mode, which uses the system JDK).
                            "runtimes": [],
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
                                "wrapper": {"enabled": gradle_wrapper_enabled},
                                "version": None,
                                "home": "abs(static/gradle-7.3.3)",
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
                        "symbols": {
                            "includeSourceMethodDeclarations": False,
                            # Surface Lombok-generated methods in document symbols (#1432).
                            "includeGeneratedCode": lombok_show_generated,
                        },
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

        # IntelliCode bundle: only attached in default vscode-java VSIX mode.
        # In upstream-jdtls mode (jdtls_path set) we don't ship IntelliCode — agentic Serena workflows
        # don't use completion ranking, so the bundle would be inert dead weight.
        if self.runtime_dependency_paths.intellicode_jar_path is not None:
            initialize_params["initializationOptions"]["bundles"] = [self.runtime_dependency_paths.intellicode_jar_path]  # type: ignore
        else:
            initialize_params["initializationOptions"]["bundles"] = []  # type: ignore

        initialize_params["initializationOptions"]["settings"]["java"]["configuration"]["runtimes"] = [  # type: ignore
            {"name": "JavaSE-21", "path": self.runtime_dependency_paths.jre_home_path, "default": True}
        ]

        for runtime in initialize_params["initializationOptions"]["settings"]["java"]["configuration"]["runtimes"]:  # type: ignore
            assert "name" in runtime
            assert "path" in runtime
            assert os.path.exists(runtime["path"]), f"Runtime required for eclipse_jdtls at path {runtime['path']} does not exist"

        gradle_settings = initialize_params["initializationOptions"]["settings"]["java"]["import"]["gradle"]  # type: ignore
        # In upstream-jdtls mode we don't ship a Gradle distribution — Buildship will use the project's
        # ./gradlew wrapper or a system-installed Gradle via its standard discovery rules.
        if self.runtime_dependency_paths.gradle_path is not None:
            gradle_settings["home"] = self.runtime_dependency_paths.gradle_path
        gradle_settings["java"] = {"home": gradle_java_home if gradle_java_home is not None else self.runtime_dependency_paths.jre_path}
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

        # IntelliCode enablement is only relevant in the default vscode-java VSIX mode where the
        # IntelliCode bundle is shipped. In upstream-jdtls mode it's absent and the
        # 'java.intellicode.enable' command will never be registered, so we skip the wait/call.
        if self.runtime_dependency_paths.intellicode_jar_path is not None:
            self._intellicode_enable_command_available.wait()

            java_intellisense_members_path = self.runtime_dependency_paths.intellisense_members_path
            assert java_intellisense_members_path is not None
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
    def _request_hover(self, file_buffer: LSPFileBuffer, line: int, column: int) -> ls_types.Hover | None:
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
        best_result = super()._request_hover(file_buffer, line, column)
        best_score = content_score(best_result)

        for _ in range(max_retries):
            sleep(0.05)
            new_result = super()._request_hover(file_buffer, line, column)
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
