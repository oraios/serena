"""
Provides BSL (1C:Enterprise) specific instantiation of the LanguageServer class
using bsl-language-server by 1c-syntax. Supports .bsl and .os files.
Requires Java 21+ on PATH (bsl-language-server v0.29.0 is built with
``targetCompatibility = JavaVersion.VERSION_21``).

You can configure the following options in ls_specific_settings (in serena_config.yml):

    ls_specific_settings:
      bsl:
        ls_path: '/path/to/bsl-language-server.jar'  # Custom path to BSL Language Server JAR
        bsl_ls_version: '0.29.0'  # BSL Language Server version (default: current bundled version)
"""

import logging
import os
import pathlib
import re
import shutil
import subprocess
import threading

from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection
from solidlsp.ls import (
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

DEFAULT_BSL_LS_VERSION = "0.29.0"
BSL_LS_JAR_SHA256_BY_VERSION = {
    "0.29.0": "d6fa9ad638ba51855e260b88ad1f8ce4e602385845a4ee43600d148f779bcf0b",
}
BSL_LS_MIN_JAVA_VERSION = 21
"""Minimum Java major version required to run the bundled bsl-language-server JAR.

bsl-language-server v0.29.0 is compiled with ``targetCompatibility = VERSION_21`` and
therefore fails at class-load time on older JDKs (``UnsupportedClassVersionError``),
which manifests as ``LanguageServerTerminatedException`` in Serena. We enforce the
check up front so the user gets an actionable error instead of a dead LSP process.
"""


def _get_java_major_version(java_exe: str) -> int | None:
    """Returns the detected Java major version (e.g. 21) or ``None`` if detection fails.

    :param java_exe: path to the ``java`` executable.
    """
    try:
        result = subprocess.run(
            [java_exe, "-version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("Failed to invoke '%s -version': %s", java_exe, exc)
        return None

    output = (result.stderr or "") + "\n" + (result.stdout or "")
    # modern JDKs print: openjdk version "21.0.2" 2024-01-16
    # legacy JDKs print: java version "1.8.0_402" (major = 8)
    m = re.search(r'version "(\d+)(?:\.(\d+))?', output)
    if not m:
        log.warning("Could not parse Java version from output of '%s -version': %s", java_exe, output.strip()[:200])
        return None

    first = int(m.group(1))
    if first == 1 and m.group(2):
        return int(m.group(2))  # 1.8 -> 8
    return first


def _verify_java_available() -> None:
    """Ensures a suitable ``java`` (>= :data:`BSL_LS_MIN_JAVA_VERSION`) is on ``PATH``.

    :raises RuntimeError: if ``java`` is missing or its major version is too low.
    """
    java_exe = shutil.which("java")
    if java_exe is None:
        raise RuntimeError(f"Java {BSL_LS_MIN_JAVA_VERSION}+ is required for BSL Language Server but 'java' was not found on PATH.")

    major = _get_java_major_version(java_exe)
    if major is None:
        # detection failed; log a warning but let the LSP attempt to start
        log.warning("Could not determine Java version for '%s'; BSL LSP requires Java %d+.", java_exe, BSL_LS_MIN_JAVA_VERSION)
        return

    if major < BSL_LS_MIN_JAVA_VERSION:
        raise RuntimeError(
            f"Java {BSL_LS_MIN_JAVA_VERSION}+ is required for BSL Language Server, but '{java_exe}' is Java {major}. "
            f"Install a newer JDK (e.g. Temurin {BSL_LS_MIN_JAVA_VERSION}) and ensure it appears first on PATH "
            f"or point JAVA_HOME to it."
        )


class BSLLanguageServer(SolidLanguageServer):
    """
    BSL (1C:Enterprise / OneScript) language server integration for Serena.
    """

    def __init__(
        self,
        config: LanguageServerConfig,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
    ):
        super().__init__(
            config,
            repository_root_path,
            None,
            "bsl",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            # resolve target version; custom versions intentionally skip SHA verification below
            bsl_version = self._custom_settings.get("bsl_ls_version", DEFAULT_BSL_LS_VERSION)
            user_overrode_version = bsl_version != DEFAULT_BSL_LS_VERSION

            jar_dir = os.path.join(self._ls_resources_dir, f"bsl-ls-{bsl_version}")
            jar_path = os.path.join(jar_dir, f"bsl-language-server-{bsl_version}-exec.jar")

            # download only when the versioned JAR is missing
            if not os.path.exists(jar_path):
                jar_url = (
                    f"https://github.com/1c-syntax/bsl-language-server/releases/download/"
                    f"v{bsl_version}/bsl-language-server-{bsl_version}-exec.jar"
                )
                expected_sha256 = None if user_overrode_version else BSL_LS_JAR_SHA256_BY_VERSION.get(bsl_version)

                deps = RuntimeDependencyCollection(
                    [
                        RuntimeDependency(
                            id="bsl-language-server",
                            description="BSL Language Server JAR by 1c-syntax",
                            url=jar_url,
                            sha256=expected_sha256,
                            archive_type="binary",
                            binary_name=f"bsl-language-server-{bsl_version}-exec.jar",
                            platform_id="any",
                        ),
                    ]
                )
                deps.install(jar_dir)

            if not os.path.exists(jar_path):
                raise FileNotFoundError(f"BSL Language Server JAR not found at {jar_path} after installation.")

            log.info(f"Using BSL Language Server v{bsl_version} at {jar_path}")
            return jar_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            # Java availability+version is required for both managed installs and user-provided jars (ls_path)
            _verify_java_available()
            return ["java", "-jar", core_path]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        return {  # type: ignore[return-value]
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},  # type: ignore
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},  # type: ignore
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {"uri": root_uri, "name": os.path.basename(repository_absolute_path)},
            ],
        }

    def _start_server(self) -> None:
        def window_log_message(msg: dict) -> None:
            log.info("BSL LSP: %s", msg.get("message", ""))

        def do_nothing(_: dict) -> None:
            return

        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_request(
            "client/registerCapability",
            lambda params: None,
        )

        log.info("Starting BSL language server process")
        self.server.start()

        init_params = self._get_initialize_params(self.repository_root_path)
        init_response = self.server.send.initialize(init_params)
        log.debug("BSL LSP initialize response: %s", init_response)

        assert "capabilities" in init_response, "BSL LSP did not return capabilities"

        self.server.notify.initialized({})
        self.server_ready.set()
