"""
Provides Bash specific instantiation of the LanguageServer class using bash-language-server.
Contains various configurations and settings specific to Bash scripting.
"""

import logging
import os
import pathlib
import shutil
import threading

from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command
from solidlsp.ls import (
    DocumentSymbols,
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    LSPFileBuffer,
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_utils import FileUtils, PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


# ShellCheck binary release info; download directly from upstream GitHub releases rather than
# relying on the `shellcheck` npm wrapper (which lazily downloads on first invocation and
# turned the bash LS install into a fragile, network-dependent step).
# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_BASH_LANGUAGE_SERVER_VERSION = "5.6.0"
DEFAULT_BASH_LANGUAGE_SERVER_VERSION = "5.6.0"

# ShellCheck binary path already encodes _SHELLCHECK_VERSION (see _shellcheck_binary_path),
# so version bumps trigger reinstall correctly without further intervention.
_SHELLCHECK_VERSION = "0.10.0"
_SHELLCHECK_RELEASE_BASE = f"https://github.com/koalaman/shellcheck/releases/download/v{_SHELLCHECK_VERSION}"
_SHELLCHECK_ALLOWED_HOSTS = (
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
)
# Per-platform archive metadata: tar.xz on POSIX (extracts to shellcheck-v<ver>/shellcheck),
# zip on Windows (extracts to shellcheck.exe at archive root).
_SHELLCHECK_DEPENDENCIES: dict[PlatformId, dict[str, str]] = {
    PlatformId.LINUX_x64: {
        "url": f"{_SHELLCHECK_RELEASE_BASE}/shellcheck-v{_SHELLCHECK_VERSION}.linux.x86_64.tar.xz",
        "sha256": "6c881ab0698e4e6ea235245f22832860544f17ba386442fe7e9d629f8cbedf87",
    },
    PlatformId.LINUX_arm64: {
        "url": f"{_SHELLCHECK_RELEASE_BASE}/shellcheck-v{_SHELLCHECK_VERSION}.linux.aarch64.tar.xz",
        "sha256": "324a7e89de8fa2aed0d0c28f3dab59cf84c6d74264022c00c22af665ed1a09bb",
    },
    PlatformId.OSX_x64: {
        "url": f"{_SHELLCHECK_RELEASE_BASE}/shellcheck-v{_SHELLCHECK_VERSION}.darwin.x86_64.tar.xz",
        "sha256": "ef27684f23279d112d8ad84e0823642e43f838993bbb8c0963db9b58a90464c2",
    },
    PlatformId.OSX_arm64: {
        "url": f"{_SHELLCHECK_RELEASE_BASE}/shellcheck-v{_SHELLCHECK_VERSION}.darwin.aarch64.tar.xz",
        "sha256": "bbd2f14826328eee7679da7221f2bc3afb011f6a928b848c80c321f6046ddf81",
    },
    PlatformId.WIN_x64: {
        "url": f"{_SHELLCHECK_RELEASE_BASE}/shellcheck-v{_SHELLCHECK_VERSION}.zip",
        "sha256": "eb6cd53a54ea97a56540e9d296ce7e2fa68715aa507ff23574646c1e12b2e143",
    },
}


def _shellcheck_install_dir(bash_ls_dir: str) -> str:
    return os.path.join(bash_ls_dir, "shellcheck")


def _shellcheck_binary_path(bash_ls_dir: str) -> str:
    """
    Returns the path to the extracted ShellCheck binary. POSIX archives extract under
    ``shellcheck-v<ver>/shellcheck``; the Windows zip drops ``shellcheck.exe`` at archive root.
    """
    install_dir = _shellcheck_install_dir(bash_ls_dir)
    if os.name == "nt":
        return os.path.join(install_dir, "shellcheck.exe")
    return os.path.join(install_dir, f"shellcheck-v{_SHELLCHECK_VERSION}", "shellcheck")


class BashLanguageServer(SolidLanguageServer):
    """
    Provides Bash specific instantiation of the LanguageServer class using bash-language-server.
    Contains various configurations and settings specific to Bash scripting.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a BashLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            "bash",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Setup runtime dependencies for Bash Language Server and return the command to start the server.
            """
            # verify node + npm are available for the bash-language-server install
            is_node_installed = shutil.which("node") is not None
            assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
            is_npm_installed = shutil.which("npm") is not None
            assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."
            bash_language_server_version = self._custom_settings.get("bash_language_server_version", DEFAULT_BASH_LANGUAGE_SERVER_VERSION)
            npm_registry = self._custom_settings.get("npm_registry")

            bash_ls_dir = self._resolve_bash_ls_dir(bash_language_server_version)
            managed_bin_dir = os.path.join(bash_ls_dir, "node_modules", ".bin")
            bash_executable_path = os.path.join(managed_bin_dir, "bash-language-server")
            if os.name == "nt":
                bash_executable_path += ".cmd"

            # install bash-language-server via npm
            if not os.path.exists(bash_executable_path):
                bls_deps = RuntimeDependencyCollection(
                    [
                        RuntimeDependency(
                            id="bash-language-server",
                            description="bash-language-server package",
                            command=build_npm_install_command("bash-language-server", bash_language_server_version, npm_registry),
                            platform_id="any",
                        ),
                    ]
                )
                log.info("Installing bash-language-server...")
                bls_deps.install(bash_ls_dir)

            # install ShellCheck binary directly from upstream releases for the current platform
            self._install_shellcheck_if_missing(bash_ls_dir)

            if not os.path.exists(bash_executable_path):
                raise FileNotFoundError(
                    f"bash-language-server executable not found at {bash_executable_path}, something went wrong with the installation."
                )

            return bash_executable_path

        @staticmethod
        def _install_shellcheck_if_missing(bash_ls_dir: str) -> None:
            """
            Downloads and extracts the platform-appropriate ShellCheck release into
            ``${bash_ls_dir}/shellcheck`` if the binary is not already present.
            """
            binary_path = _shellcheck_binary_path(bash_ls_dir)
            if os.path.exists(binary_path):
                return

            install_dir = _shellcheck_install_dir(bash_ls_dir)
            os.makedirs(install_dir, exist_ok=True)

            release = _SHELLCHECK_DEPENDENCIES.get(PlatformUtils.get_platform_id())
            if release is None:
                raise RuntimeError(f"ShellCheck has no upstream binary release for platform {PlatformUtils.get_platform_id().value}")

            archive_type = "zip" if os.name == "nt" else "xztar"
            log.info(f"Downloading ShellCheck v{_SHELLCHECK_VERSION} for {PlatformUtils.get_platform_id().value}")
            FileUtils.download_and_extract_archive_verified(
                release["url"],
                install_dir,
                archive_type,
                expected_sha256=release["sha256"],
                allowed_hosts=_SHELLCHECK_ALLOWED_HOSTS,
            )

            if not os.path.exists(binary_path):
                raise FileNotFoundError(f"ShellCheck binary not found at {binary_path} after extraction; archive layout may have changed.")

            # ensure the binary is executable on POSIX (zip extraction does not preserve perms)
            if os.name != "nt":
                current = os.stat(binary_path).st_mode
                os.chmod(binary_path, current | 0o111)

        def create_launch_command_env(self) -> dict[str, str]:
            bash_language_server_version = self._custom_settings.get("bash_language_server_version", DEFAULT_BASH_LANGUAGE_SERVER_VERSION)
            bash_ls_dir = self._resolve_bash_ls_dir(bash_language_server_version)
            managed_bin_dir = os.path.join(bash_ls_dir, "node_modules", ".bin")
            return {
                "PATH": managed_bin_dir + os.pathsep + os.environ.get("PATH", ""),
                "SHELLCHECK_PATH": _shellcheck_binary_path(bash_ls_dir),
            }

        def _resolve_bash_ls_dir(self, bash_language_server_version: str) -> str:
            # legacy unversioned dir reserved for INITIAL; every other version goes into a versioned subdir
            ls_dirname = (
                "bash-lsp"
                if bash_language_server_version == INITIAL_BASH_LANGUAGE_SERVER_VERSION
                else f"bash-lsp-{bash_language_server_version}"
            )
            return os.path.join(self._ls_resources_dir, ls_dirname)

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "start"]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Bash Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "signatureHelp": {"dynamicRegistration": True},
                    "codeAction": {"dynamicRegistration": True},
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
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }
        return initialize_params  # type: ignore

    def _start_server(self) -> None:
        """
        Starts the Bash Language Server, waits for the server to be ready and yields the LanguageServer instance.
        """

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
            return

        def execute_client_command_handler(params: dict) -> list:
            return []

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")
            # Check for bash-language-server ready signals
            message_text = msg.get("message", "")
            if "Analyzing" in message_text or "analysis complete" in message_text.lower():
                log.info("Bash language server analysis signals detected")
                self.server_ready.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Bash server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response from bash server: {init_response}")

        # Enhanced capability checks for bash-language-server 5.6.0
        assert init_response["capabilities"]["textDocumentSync"] in [1, 2]  # Full or Incremental
        assert "completionProvider" in init_response["capabilities"]

        # Verify document symbol support is available
        if "documentSymbolProvider" in init_response["capabilities"]:
            log.info("Bash server supports document symbols")
        else:
            log.warning("Warning: Bash server does not report document symbol support")

        self.server.notify.initialized({})

        # Wait for server readiness with timeout
        log.info("Waiting for Bash language server to be ready...")
        if not self.server_ready.wait(timeout=3.0):
            # Fallback: assume server is ready after timeout
            # This is common. bash-language-server doesn't always send explicit ready signals. Log as info
            log.info("Timeout waiting for bash server ready signal, proceeding anyway")
            self.server_ready.set()
        else:
            log.info("Bash server initialization complete")

    def request_document_symbols(self, relative_file_path: str, file_buffer: LSPFileBuffer | None = None) -> DocumentSymbols:
        # Uses the standard LSP documentSymbol request which provides reliable function detection
        # for all bash function syntaxes including:
        # - function name() { ... } (with function keyword)
        # - name() { ... } (traditional syntax)
        # - Functions with various indentation levels
        # - Functions with comments before/after/inside

        log.debug(f"Requesting document symbols via LSP for {relative_file_path}")

        # Use the standard LSP approach - bash-language-server handles all function syntaxes correctly
        document_symbols = super().request_document_symbols(relative_file_path, file_buffer=file_buffer)

        # Log detection results for debugging
        functions = [s for s in document_symbols.iter_symbols() if s.get("kind") == 12]
        log.info(f"LSP function detection for {relative_file_path}: Found {len(functions)} functions")

        return document_symbols
