"""
Shader language server using shader-language-server (antaalt/shader-sense).
Supports HLSL, GLSL, and WGSL shader file formats.
"""

import logging
import os
import pathlib
import shutil
from typing import Any, cast

import psutil
from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)

# GitHub release version to download when not installed locally
_DEFAULT_VERSION = "1.3.0"
_GITHUB_RELEASE_BASE = "https://github.com/antaalt/shader-sense/releases/download"
_HLSL_ALLOWED_HOSTS = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")
_HLSL_SHA256_BY_ASSET = {
    "shader-language-server-x86_64-pc-windows-msvc.zip": "a945b000c296cdeebb9ee2d4452cec2a0f26544dd076bb08bfdcade2278296a6",
    "shader-language-server-x86_64-unknown-linux-gnu.zip": "8c0a7b36f51cc58593762db3592ae13e21ca3cb982b2526cfaaf7c82e92ca089",
    "shader-language-server-aarch64-pc-windows-msvc.zip": "cdbd7b41e71cf6040d5cdb7e211ba4b76671a404ee0f7add281d72d3ab8dfa65",
}


class HlslLanguageServer(SolidLanguageServer):
    """
    Shader language server using shader-language-server.
    Supports .hlsl, .hlsli, .fx, .fxh, .cginc, .compute, .shader, .glsl, .vert, .frag, .geom, .tesc, .tese, .comp, .wgsl files.

    You can pass the following entries in ``ls_specific_settings["hlsl"]``:
        - version: Override the pinned shader-language-server version downloaded
          or built by Serena (default: the bundled Serena version).
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings) -> None:
        super().__init__(config, repository_root_path, None, "hlsl", solidlsp_settings)

    @override
    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            # 1. Check PATH for system-installed binary
            system_binary = shutil.which("shader-language-server")
            if system_binary:
                log.info(f"Using system-installed shader-language-server at {system_binary}")
                return system_binary

            # 2. Try to download pre-built binary from GitHub releases
            version = self._custom_settings.get("version", _DEFAULT_VERSION)
            tag = f"v{version}"
            base_url = f"{_GITHUB_RELEASE_BASE}/{tag}"

            # macOS has no pre-built binaries; build from source via cargo install
            cargo_install_cmd = ["cargo", "install", "shader_language_server", "--version", version, "--root", "."]

            deps = RuntimeDependencyCollection(
                [
                    RuntimeDependency(
                        id="shader-language-server",
                        description="shader-language-server for Windows (x64)",
                        url=f"{base_url}/shader-language-server-x86_64-pc-windows-msvc.zip",
                        platform_id="win-x64",
                        archive_type="zip",
                        binary_name="shader-language-server.exe",
                        sha256=_HLSL_SHA256_BY_ASSET["shader-language-server-x86_64-pc-windows-msvc.zip"]
                        if version == _DEFAULT_VERSION
                        else None,
                        allowed_hosts=_HLSL_ALLOWED_HOSTS,
                    ),
                    RuntimeDependency(
                        id="shader-language-server",
                        description="shader-language-server for Linux (x64)",
                        url=f"{base_url}/shader-language-server-x86_64-unknown-linux-gnu.zip",
                        platform_id="linux-x64",
                        archive_type="zip",
                        binary_name="shader-language-server",
                        sha256=_HLSL_SHA256_BY_ASSET["shader-language-server-x86_64-unknown-linux-gnu.zip"]
                        if version == _DEFAULT_VERSION
                        else None,
                        allowed_hosts=_HLSL_ALLOWED_HOSTS,
                    ),
                    RuntimeDependency(
                        id="shader-language-server",
                        description="shader-language-server for Windows (ARM64)",
                        url=f"{base_url}/shader-language-server-aarch64-pc-windows-msvc.zip",
                        platform_id="win-arm64",
                        archive_type="zip",
                        binary_name="shader-language-server.exe",
                        sha256=_HLSL_SHA256_BY_ASSET["shader-language-server-aarch64-pc-windows-msvc.zip"]
                        if version == _DEFAULT_VERSION
                        else None,
                        allowed_hosts=_HLSL_ALLOWED_HOSTS,
                    ),
                    RuntimeDependency(
                        id="shader-language-server",
                        description="shader-language-server for macOS (x64) - built from source",
                        command=cargo_install_cmd,
                        platform_id="osx-x64",
                        binary_name="bin/shader-language-server",
                    ),
                    RuntimeDependency(
                        id="shader-language-server",
                        description="shader-language-server for macOS (ARM64) - built from source",
                        command=cargo_install_cmd,
                        platform_id="osx-arm64",
                        binary_name="bin/shader-language-server",
                    ),
                ]
            )

            try:
                dep = deps.get_single_dep_for_current_platform()
            except RuntimeError:
                dep = None

            if dep is None:
                raise FileNotFoundError(
                    "shader-language-server is not installed and no auto-install is available for your platform.\n"
                    "Please install it using one of the following methods:\n"
                    "  cargo:   cargo install shader_language_server\n"
                    "  GitHub:  Download from https://github.com/antaalt/shader-sense/releases\n"
                    "On macOS, install the Rust toolchain (https://rustup.rs) and Serena will build from source automatically.\n"
                    "See https://github.com/antaalt/shader-sense for more details."
                )

            install_dir = os.path.join(self._ls_resources_dir, "shader-language-server")
            executable_path = deps.binary_path(install_dir)

            if not os.path.exists(executable_path):
                log.info(f"shader-language-server not found. Downloading from {dep.url}")
                _ = deps.install(install_dir)

            if not os.path.exists(executable_path):
                raise FileNotFoundError(f"shader-language-server not found at {executable_path}")

            os.chmod(executable_path, 0o755)
            return executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "--stdio"]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {"snippetSupport": True},
                    },
                    "definition": {"dynamicRegistration": True},
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"],
                    },
                    "signatureHelp": {
                        "dynamicRegistration": True,
                        "signatureInformation": {
                            "parameterInformation": {"labelOffsetSupport": True},
                        },
                    },
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "formatting": {"dynamicRegistration": True},
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "configuration": True,
                },
            },
            "workspaceFolders": [{"uri": root_uri, "name": os.path.basename(repository_absolute_path)}],
        }
        return cast(InitializeParams, initialize_params)

    @override
    def _start_server(self) -> None:
        def do_nothing(params: Any) -> None:
            return

        def on_log_message(params: Any) -> None:
            message = params.get("message", "") if isinstance(params, dict) else str(params)
            log.info(f"shader-language-server: {message}")

        def on_configuration_request(params: Any) -> list[dict]:
            """Respond to workspace/configuration requests.

            shader-language-server requests config with section 'shader-validator'.
            Return empty config to use defaults.
            """
            items = params.get("items", []) if isinstance(params, dict) else []
            return [{}] * len(items)

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_request("workspace/configuration", on_configuration_request)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("window/logMessage", on_log_message)

        log.info("Starting shader-language-server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request")
        init_response = self.server.send.initialize(initialize_params)

        capabilities = init_response.get("capabilities", {})
        log.info(f"Initialize response capabilities: {list(capabilities.keys())}")
        assert "textDocumentSync" in capabilities, "shader-language-server must support textDocumentSync"
        if "documentSymbolProvider" not in capabilities:
            log.warning("shader-language-server does not advertise documentSymbolProvider")
        if "definitionProvider" not in capabilities:
            log.warning("shader-language-server does not advertise definitionProvider")

        self.server.notify.initialized({})

    @override
    def stop(self, shutdown_timeout: float = 2.0) -> None:
        """Kill the shader-language-server process tree before the standard shutdown.

        The base _shutdown() calls process.terminate() directly on the subprocess,
        which on Windows with shell=True only kills the cmd.exe wrapper, leaving
        the actual shader-language-server binary running as an orphan. We use psutil
        to terminate the full process tree first.
        """
        process = self.server.process if self.server else None
        if process and process.pid and process.returncode is None:
            try:
                parent = psutil.Process(process.pid)
                children = parent.children(recursive=True)
                for child in children:
                    try:
                        child.terminate()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                psutil.wait_procs(children, timeout=2)
                for child in children:
                    try:
                        if child.is_running():
                            child.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            except Exception as e:
                log.debug(f"Error cleaning up shader-language-server process tree: {e}")
        super().stop(shutdown_timeout)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        """Ignore Unity-specific directories that contain no user-authored shaders."""
        return super().is_ignored_dirname(dirname) or dirname in {"Library", "Temp", "Logs", "obj", "Packages"}
