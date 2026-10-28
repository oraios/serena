"""
Provides BSL (1C:Enterprise) specific instantiation of the LanguageServer class
using bsl-language-server by 1c-syntax. Supports .bsl and .os files.
Requires Java 21+ on PATH (bsl-language-server v1.0.7 is built with
``targetCompatibility = JavaVersion.VERSION_21``).

You can configure the following options in ls_specific_settings (in serena_config.yml):

    ls_specific_settings:
      bsl:
        ls_path: '/path/to/bsl-language-server.jar'  # Custom path to BSL Language Server JAR
        bsl_ls_version: '1.0.7'  # Version to download (non-default versions are not hash-verified)
        jvm_options: ['-Xmx1g']  # JVM arguments before -jar (default: [])
"""
# SPDX-License-Identifier: MIT

import logging
import os
import re
import shutil
import subprocess
import threading
import time

from solidlsp.dependency_provider import DownloadedDependency, DownloadedDependencyHashDatabase
from solidlsp.ls import (
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.settings import SolidLSPSettings
from solidlsp.util.subprocess_util import subprocess_run

log = logging.getLogger(__name__)

BSL_LS_ALLOWED_HOSTS = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")

# NOTE: after bumping this, re-run scripts/update_downloaded_dependency_hashes.py and commit the
# updated src/solidlsp/resources/downloaded_dependency_hashes.json.
DEFAULT_BSL_LS_VERSION = "1.0.7"
BSL_LS_MIN_JAVA_VERSION = 21
"""Minimum Java major version required to run the bundled bsl-language-server JAR.

bsl-language-server v1.0.7 is compiled with ``targetCompatibility = VERSION_21`` and
therefore fails at class-load time on older JDKs (``UnsupportedClassVersionError``),
which manifests as ``LanguageServerTerminatedException`` in Serena. We enforce the
check up front so the user gets an actionable error instead of a dead LSP process.
"""


def _get_java_major_version(java_exe: str) -> int | None:
    """Returns the detected Java major version (e.g. 21) or ``None`` if detection fails.

    :param java_exe: path to the ``java`` executable.
    """
    try:
        result = subprocess_run(
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

    class _StartupProgressTracker:
        """Tracks startup progress cycles and waits for a quiet interval after initialization."""

        def __init__(self) -> None:
            self._condition = threading.Condition()
            self._active_tokens: set[str | int] = set()
            self._initialized_at: float | None = None
            self._last_activity = time.monotonic()
            self._completed_cycle = False
            self._ready = False

        def create(self, params: dict) -> None:
            """Registers a work-done token before its first progress notification."""
            self._update(params["token"], "create")

        def progress(self, params: dict) -> None:
            """Records work-done notifications, ignoring partial-result progress."""
            value = params.get("value")
            if isinstance(value, dict) and value.get("kind") in {"begin", "report", "end"}:
                self._update(params["token"], value["kind"])

        def _update(self, token: str | int, kind: str) -> None:
            with self._condition:
                self._last_activity = time.monotonic()
                if kind in {"create", "begin"}:
                    self._active_tokens.add(token)
                    self._ready = False
                elif kind == "end":
                    if token in self._active_tokens and self._initialized_at is not None:
                        self._completed_cycle = True
                    self._active_tokens.discard(token)
                self._condition.notify_all()

        def initialized(self) -> None:
            """Starts the post-initialization observation window."""
            with self._condition:
                self._initialized_at = time.monotonic()
                self._completed_cycle = False
                self._ready = False

        def is_ready(self) -> bool:
            """Whether progress confirmed that startup has settled."""
            with self._condition:
                return self._ready

        def wait(self, timeout: float = 120.0, grace: float = 2.0, settle: float = 0.5) -> None:
            """Waits for settled progress, falling back if no progress is supported.

            :param timeout: maximum time to wait after initialization, in seconds.
            :param grace: observation window without post-initialization activity, in seconds.
            :param settle: quiet interval after completed progress, in seconds.
            """
            with self._condition:
                if self._initialized_at is None:
                    raise RuntimeError("BSL startup progress observation requires initialized")
                deadline = self._initialized_at + timeout
                while True:
                    now = time.monotonic()
                    if self._completed_cycle and not self._active_tokens:
                        quiet_until = max(self._last_activity, self._initialized_at) + settle
                        if now >= quiet_until:
                            self._ready = True
                            log.info("BSL LSP startup progress complete")
                            return
                        wake_at = quiet_until
                    elif self._last_activity < self._initialized_at and not self._active_tokens:
                        wake_at = self._initialized_at + grace
                        if now >= wake_at:
                            log.info("BSL LSP sent no startup progress; using fallback readiness")
                            return
                    else:
                        wake_at = deadline
                    if now >= deadline:
                        log.warning("BSL LSP startup progress did not complete within %.0fs; proceeding anyway", timeout)
                        return
                    self._condition.wait(max(0.0, min(wake_at, deadline) - now))

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
        self._startup_progress = self._StartupProgressTracker()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        @classmethod
        def _create_dep_language_server(cls, version: str | None = None) -> DownloadedDependency:
            version = version or DEFAULT_BSL_LS_VERSION
            return DownloadedDependency(
                url=(
                    f"https://github.com/1c-syntax/bsl-language-server/releases/download/v{version}/bsl-language-server-{version}-exec.jar"
                ),
                allowed_hosts=BSL_LS_ALLOWED_HOSTS,
                verified=version == DEFAULT_BSL_LS_VERSION,
            )

        @classmethod
        def update_dep_hashes(cls) -> None:
            with DownloadedDependencyHashDatabase.get_instance().update_context() as db:
                db.update(cls._create_dep_language_server())

        def _get_or_install_core_dependency(self) -> str:
            version = self._custom_settings.get("bsl_ls_version", DEFAULT_BSL_LS_VERSION)
            jar_dir = os.path.join(self._ls_resources_dir, f"bsl-ls-{version}")
            jar_path = os.path.join(jar_dir, f"bsl-language-server-{version}-exec.jar")

            # reuse an existing versioned JAR or download the selected release
            if not os.path.exists(jar_path):
                os.makedirs(jar_dir, exist_ok=True)
                self._create_dep_language_server(version).download_to(jar_path)
            if not os.path.exists(jar_path):
                raise FileNotFoundError(f"BSL Language Server JAR not found at {jar_path} after installation.")

            log.info("Using BSL Language Server v%s at %s", version, jar_path)
            return jar_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            jvm_options = self._custom_settings.get("jvm_options", [])
            if jvm_options is None:
                jvm_options = []
            if not isinstance(jvm_options, list) or not all(isinstance(option, str) for option in jvm_options):
                raise ValueError("ls_specific_settings.bsl.jvm_options must be a list of strings")
            _verify_java_available()
            return ["java", *jvm_options, "-jar", core_path]

    def _create_base_initialize_params(self) -> dict:
        return {
            "locale": "en",
            "capabilities": {
                "window": {"workDoneProgress": True},
                "general": {"positionEncodings": ["utf-16"]},
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeWatchedFiles": {"dynamicRegistration": True},
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
        }

    def _start_server(self) -> None:
        """Starts the server with a fresh progress tracker, resetting readiness on every restart."""

        def window_log_message(msg: dict) -> None:
            log.info("BSL LSP: %s", msg.get("message", ""))

        def do_nothing(_: dict) -> None:
            return

        self.server.on_notification("window/logMessage", window_log_message)
        self._startup_progress = self._StartupProgressTracker()
        self.server.on_request("window/workDoneProgress/create", self._startup_progress.create)
        self.server.on_notification("$/progress", self._startup_progress.progress)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_request(
            "client/registerCapability",
            lambda params: None,
        )

        log.info("Starting BSL language server process")
        self.server.start()

        init_params = self._create_initialize_params()
        init_response = self.server.send.initialize(init_params)
        log.debug("BSL LSP initialize response: %s", init_response)

        if "capabilities" not in init_response:
            raise RuntimeError("BSL LSP did not return capabilities")

        self._startup_progress.initialized()
        self.server.notify.initialized({})
        self._startup_progress.wait()

    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 0.0 if self._startup_progress.is_ready() else super()._get_wait_time_for_cross_file_referencing()
