"""Erlang Language Server implementation using the Erlang Language Platform (ELP)."""

import logging
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Hashable
from typing import ClassVar

from overrides import override

from solidlsp.dependency_provider import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath
from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection
from solidlsp.ls import RawDocumentSymbol, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_utils import PlatformId, PlatformUtils, is_running_in_ci
from solidlsp.settings import SolidLSPSettings
from solidlsp.util.subprocess_util import subprocess_run

log = logging.getLogger(__name__)

ARITY_SEPARATOR = "#"
"""
The character that replaces the `/` in the `name/arity` identifiers reported by ELP.

`#` was chosen because it cannot occur in an unquoted Erlang atom, so it can never collide with a
real function, type or macro name (unlike `@`, which is a legal atom character).
"""

ELP_VERSION = "2026-08-10"
ELP_OTP_BUILD = "27.3"
ELP_BASE_URL = f"https://github.com/WhatsApp/erlang-language-platform/releases/download/{ELP_VERSION}"
ELP_ALLOWED_HOSTS = (
    "github.com",
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
)

# ELP publishes platform-specific builds. The OTP 27.3 build is the oldest currently available
# release asset and can run on newer Erlang/OTP versions, as documented by ELP.
ELP_ASSET_PLATFORM_BY_ID: dict[PlatformId, str] = {
    PlatformId.LINUX_x64: "linux-x86_64-unknown-linux-gnu",
    PlatformId.LINUX_arm64: "linux-aarch64-unknown-linux-gnu",
    PlatformId.OSX_x64: "macos-x86_64-apple-darwin",
    PlatformId.OSX_arm64: "macos-aarch64-apple-darwin",
    PlatformId.WIN_x64: "windows-x86_64-pc-windows-msvc",
}

ELP_SHA256_BY_ASSET: dict[str, str] = {
    "elp-linux-x86_64-unknown-linux-gnu-otp-27.3.tar.gz": "c0e672a8381b5ea787e94a872847567b10d9b4d0053ca1148f4b236f61af3c63",
    "elp-linux-aarch64-unknown-linux-gnu-otp-27.3.tar.gz": "0af71bd62e95998b7e57edd2083141b60edab51d0a2da988e6e71abb88cd3f34",
    "elp-macos-x86_64-apple-darwin-otp-27.3.tar.gz": "d7c739a6b23ba7bfc0fc8481619ec55e41257d08cb7aa8b16499fb4c4f5e38e2",
    "elp-macos-aarch64-apple-darwin-otp-27.3.tar.gz": "7317a9934edc411e94392d5cc720f2e0c18112e7959060678aaef4d6dacdd9f2",
    "elp-windows-x86_64-pc-windows-msvc-otp-27.3.tar.gz": "6c4ed9ab76c9cbb2f6ae7b3a8dc06121a4ac6eda94d13bf7a638d3cb111b7f4e",
}


class ErlangLanguageServer(SolidLanguageServer):
    """Language server for Erlang using the official Erlang Language Platform."""

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        """Resolves ELP from PATH or downloads the pinned official release asset."""

        _SUPPORTED_PLATFORM_IDS: ClassVar[frozenset[PlatformId]] = frozenset(ELP_ASSET_PLATFORM_BY_ID)

        def _get_or_install_core_dependency(self) -> str:
            """Return an ELP executable, preferring a user-managed executable on PATH."""
            elp_in_path = shutil.which("elp")
            if elp_in_path:
                log.info("Found ELP in PATH: %s", elp_in_path)
                return elp_in_path

            platform_id = PlatformUtils.get_platform_id()
            if platform_id not in self._SUPPORTED_PLATFORM_IDS:
                raise RuntimeError(
                    f"ELP is not available for platform {platform_id}. Install a compatible ELP binary "
                    "from https://github.com/WhatsApp/erlang-language-platform/releases and set "
                    "ls_specific_settings.erlang.ls_path."
                )

            dependency = self._runtime_dependency(platform_id)
            install_dir = os.path.join(self._ls_resources_dir, f"elp-{ELP_VERSION}-{platform_id.value}")
            assert dependency.binary_name is not None
            executable_path = os.path.join(install_dir, dependency.binary_name)

            if not os.path.exists(executable_path):
                log.info("Downloading ELP from %s", dependency.url)
                RuntimeDependencyCollection([dependency]).install(install_dir)

            if not os.path.exists(executable_path):
                raise FileNotFoundError(f"ELP executable not found at {executable_path} after installation")

            if not platform_id.is_windows():
                os.chmod(executable_path, 0o755)

            log.info("ELP binary ready at: %s", executable_path)
            return executable_path

        @staticmethod
        def _runtime_dependency(platform_id: PlatformId) -> RuntimeDependency:
            asset_platform = ELP_ASSET_PLATFORM_BY_ID[platform_id]
            executable_name = "elp.exe" if platform_id.is_windows() else "elp"
            asset_name = f"elp-{asset_platform}-otp-{ELP_OTP_BUILD}.tar.gz"
            return RuntimeDependency(
                id="elp",
                description=f"Erlang Language Platform for {platform_id.value}",
                platform_id=platform_id.value,
                url=f"{ELP_BASE_URL}/{asset_name}",
                archive_type="gztar",
                binary_name=executable_name,
                sha256=ELP_SHA256_BY_ASSET[asset_name],
                allowed_hosts=ELP_ALLOWED_HOSTS,
            )

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "server"]

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates an ErlangLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.

        ELP is taken from PATH when available; otherwise Serena downloads the pinned release asset.
        The ``ls_path`` setting under ``ls_specific_settings.erlang`` can override both choices.
        """
        if not self._check_erlang_installation():
            raise RuntimeError("Erlang/OTP not found. Install from: https://www.erlang.org/downloads")

        super().__init__(
            config,
            repository_root_path,
            None,
            "erlang",
            solidlsp_settings,
        )

        self.server_ready = threading.Event()
        self.set_request_timeout(120.0)

    @override
    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    @override
    def _document_symbols_cache_fingerprint(self) -> Hashable:
        normalize_symbol_name_version = 1
        return normalize_symbol_name_version

    @override
    def _normalize_symbol_name(self, symbol: RawDocumentSymbol, relative_file_path: str) -> str:
        """
        Replaces the `/` in Erlang's `name/arity` identifiers, which would otherwise be interpreted
        as Serena's name path separator.

        ELP names functions, types and parameterised macros `name/arity` (e.g. `create_user/2`).
        Since `/` separates name path components, such a name is parsed as "symbol `2` nested inside
        `create_user`" and can never be matched, not even by the very name path that Serena itself
        reports for the symbol. The arity is not simply dropped because it is part of a function's
        identity in Erlang: `create_user/2` and `create_user/3` are different functions which may
        both be defined in the same module.
        """
        return symbol["name"].replace("/", ARITY_SEPARATOR)

    @staticmethod
    def _check_erlang_installation() -> bool:
        """Check if Erlang/OTP is available."""
        try:
            result = subprocess_run(["erl", "-version"], check=False, capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    @classmethod
    def _get_erlang_version(cls) -> str | None:
        """Get the installed Erlang/OTP version or None if not found."""
        try:
            result = subprocess_run(["erl", "-version"], check=False, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return result.stderr.strip()  # erl -version outputs to stderr
        except (subprocess.SubprocessError, FileNotFoundError):
            return None
        return None

    @classmethod
    def _check_rebar3_available(cls) -> bool:
        """Check if rebar3 build tool is available."""
        try:
            result = subprocess_run(["rebar3", "version"], check=False, capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def _create_base_initialize_params(self) -> dict:
        """
        Returns the base initialize params for ELP.

        processId, rootPath, rootUri, clientInfo and workspaceFolders are added by the builder.
        """
        return {
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True},
                    "completion": {"dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {"dynamicRegistration": True},
                    "hover": {"dynamicRegistration": True},
                }
            },
        }

    def _start_server(self) -> None:
        """Start the ELP server process with LSP initialization."""

        def register_capability_handler(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            """Handle window/logMessage notifications from ELP."""
            message_text = msg.get("message", "")
            log.info("LSP: window/logMessage: %s", message_text)

            readiness_signals = [
                "ELP server",
                "server started",
                "initialized",
                "ready to serve requests",
                "compilation finished",
                "indexing complete",
            ]
            message_lower = message_text.lower()
            if any(signal_text.lower() in message_lower for signal_text in readiness_signals):
                log.info("ELP readiness signal detected: %s", message_text)
                self.server_ready.set()

        def do_nothing(params: dict) -> None:
            return

        def check_server_ready(params: dict) -> None:
            """Handle progress notifications from ELP as a fallback readiness signal."""
            value = params.get("value", {})
            if value.get("kind") == "end":
                message = value.get("message", "")
                if any(word in message.lower() for word in ["initialized", "ready", "complete"]):
                    self.server_ready.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", check_server_ready)
        self.server.on_notification("window/workDoneProgress/create", do_nothing)
        self.server.on_notification("$/workDoneProgress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting ELP server process")
        self.server.start()

        log.info("Sending initialize request to ELP")
        init_response = self.server.send.initialize(self._create_initialize_params())
        if "capabilities" in init_response:
            log.info("ELP capabilities: %s", list(init_response["capabilities"].keys()))

        self.server.notify.initialized({})
        self.server_ready.set()

        # The initialize response means the LSP is ready to receive requests. ELP continues its
        # project indexing asynchronously, so retain a short settling period without the old
        # Erlang-LS-specific readiness timeout.
        is_ci = is_running_in_ci()
        settling_time = 15.0 if is_ci else 5.0
        log.info("ELP initialized; allowing %.1f seconds for indexing to settle", settling_time)
        time.sleep(settling_time)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For Erlang projects, we should ignore:
        # - _build: rebar3 build artifacts
        # - deps: dependencies
        # - ebin: compiled beam files
        # - .rebar3: rebar3 cache
        # - logs: log files
        # - node_modules: if the project has JavaScript components
        return super().is_ignored_dirname(dirname) or dirname in [
            "_build",
            "deps",
            "ebin",
            ".rebar3",
            "logs",
            "node_modules",
            "_checkouts",
            "cover",
        ]

    def is_ignored_filename(self, filename: str) -> bool:
        """Check if a filename should be ignored."""
        if filename.endswith(".beam"):
            return True
        return False
