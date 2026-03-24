"""
Provides Luau specific instantiation of the LanguageServer class using luau-lsp.

Luau is the programming language used by Roblox, derived from Lua 5.1 with
additional features like type annotations, string interpolation, and more.
This uses JohnnyMorganz/luau-lsp as the language server backend.

Requirements:
    - luau-lsp binary must be installed and available in PATH,
      or it will be automatically downloaded from GitHub releases.

Advanced settings via ls_specific_settings["luau"]:
    - platform: "roblox" (default) or "standard"
    - roblox_security_level: "None", "PluginSecurity" (default),
      "LocalUserSecurity", or "RobloxScriptSecurity"

See: https://github.com/JohnnyMorganz/luau-lsp
"""

import logging
import os
import pathlib
import platform
import shutil
import threading
import zipfile
from pathlib import Path

import requests
from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# Pin to a known stable release
LUAU_LSP_VERSION = "1.63.0"

# Luau built-in docs CDN
LUAU_DOCS_URL = "https://luau-lsp.pages.dev/api-docs/luau-en-us.json"

# Roblox type definitions and API docs CDN
ROBLOX_DOCS_URL = "https://luau-lsp.pages.dev/api-docs/en-us.json"
SUPPORTED_PLATFORMS = {"roblox", "standard"}
SUPPORTED_ROBLOX_SECURITY_LEVELS = {
    "None",
    "PluginSecurity",
    "LocalUserSecurity",
    "RobloxScriptSecurity",
}


class LuauLanguageServer(SolidLanguageServer):
    """
    Provides Luau specific instantiation of the LanguageServer class using luau-lsp.
    Luau is the programming language used by Roblox (a typed superset of Lua 5.1).
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",
            "Packages",  # Wally packages
            "DevPackages",  # Wally dev packages
            "roblox_packages",  # Some Rojo projects
            "build",
            "dist",
            ".cache",
        ]

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            luau_lsp_path = shutil.which("luau-lsp")
            if luau_lsp_path is not None:
                return luau_lsp_path
            return self._download_luau_lsp()

        def _create_launch_command(self, core_path: str) -> list[str]:
            definitions_path, docs_path = self._resolve_support_files()

            cmd = [core_path, "lsp"]
            if definitions_path is not None:
                cmd.append(f"--definitions:@roblox={definitions_path}")
            if docs_path is not None:
                cmd.append(f"--docs={docs_path}")
            return cmd

        def _download_luau_lsp(self) -> str:
            install_dir = Path(self._ls_resources_dir)
            install_dir.mkdir(parents=True, exist_ok=True)

            binary_path = self._find_existing_binary(install_dir)
            if binary_path is not None:
                return binary_path

            asset_name = self._get_luau_lsp_asset_name()
            download_url = f"https://github.com/JohnnyMorganz/luau-lsp/releases/download/{LUAU_LSP_VERSION}/{asset_name}"
            download_path = install_dir / asset_name

            log.info("Downloading luau-lsp %s from %s", LUAU_LSP_VERSION, download_url)
            with requests.get(download_url, stream=True, timeout=60) as response:
                response.raise_for_status()
                with open(download_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

            log.info("Extracting luau-lsp to %s", install_dir)
            with zipfile.ZipFile(download_path, "r") as zip_ref:
                zip_ref.extractall(install_dir)

            if download_path.exists():
                download_path.unlink()

            binary_path = self._find_existing_binary(install_dir)
            if binary_path is None:
                raise RuntimeError("Failed to find luau-lsp executable after extraction")

            return binary_path

        def _resolve_support_files(self) -> tuple[str | None, str | None]:
            platform_type = LuauLanguageServer._get_platform_type(self._custom_settings)
            if platform_type == "standard":
                return None, self._download_standard_docs()

            security_level = LuauLanguageServer._get_roblox_security_level(self._custom_settings)
            return self._download_roblox_support_files(security_level)

        def _download_standard_docs(self) -> str | None:
            install_dir = Path(self._ls_resources_dir)
            install_dir.mkdir(parents=True, exist_ok=True)

            return self._download_auxiliary_file(
                install_dir / "luau-en-us.json",
                LUAU_DOCS_URL,
                "Luau API docs",
            )

        def _download_roblox_support_files(self, security_level: str) -> tuple[str | None, str | None]:
            install_dir = Path(self._ls_resources_dir)
            install_dir.mkdir(parents=True, exist_ok=True)

            definitions_filename = f"globalTypes.{security_level}.d.luau"
            definitions_path = self._download_auxiliary_file(
                install_dir / definitions_filename,
                f"https://luau-lsp.pages.dev/type-definitions/{definitions_filename}",
                "Roblox type definitions",
            )
            docs_path = self._download_auxiliary_file(
                install_dir / "en-us.json",
                ROBLOX_DOCS_URL,
                "Roblox API docs",
            )

            return definitions_path, docs_path

        @staticmethod
        def _download_auxiliary_file(path: Path, url: str, description: str) -> str | None:
            if path.exists():
                return str(path)

            try:
                log.info("Downloading %s from %s", description, url)
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                path.write_bytes(response.content)
                return str(path)
            except Exception as exc:
                log.warning("Failed to download %s: %s", description, exc)
                return None

        @classmethod
        def _find_existing_binary(cls, install_dir: Path) -> str | None:
            binary_name = cls._get_binary_name()
            direct_path = install_dir / binary_name
            if direct_path.exists():
                cls._ensure_executable_bit(direct_path)
                return str(direct_path)

            for candidate in install_dir.rglob(binary_name):
                if candidate.is_file():
                    cls._ensure_executable_bit(candidate)
                    return str(candidate)

            return None

        @staticmethod
        def _ensure_executable_bit(binary_path: Path) -> None:
            if platform.system() != "Windows":
                binary_path.chmod(0o755)

        @staticmethod
        def _get_binary_name() -> str:
            return "luau-lsp.exe" if platform.system() == "Windows" else "luau-lsp"

        @staticmethod
        def _get_luau_lsp_asset_name() -> str:
            system = platform.system()
            machine = platform.machine().lower()

            if system == "Linux":
                if machine in ["x86_64", "amd64"]:
                    return "luau-lsp-linux-x86_64.zip"
                if machine in ["aarch64", "arm64"]:
                    return "luau-lsp-linux-arm64.zip"
                raise RuntimeError(
                    f"Unsupported Linux architecture: {machine}. "
                    "luau-lsp only provides linux-x86_64 and linux-arm64 binaries. "
                    "Please build from source: https://github.com/JohnnyMorganz/luau-lsp"
                )
            if system == "Darwin":
                return "luau-lsp-macos.zip"
            if system == "Windows":
                return "luau-lsp-win64.zip"
            raise RuntimeError(f"Unsupported operating system: {system}")

    @staticmethod
    def _get_platform_type(custom_settings: SolidLSPSettings.CustomLSSettings) -> str:
        platform_type = custom_settings.get("platform", "roblox")
        if platform_type not in SUPPORTED_PLATFORMS:
            raise ValueError(f"Unsupported Luau platform: {platform_type}. Expected one of: {', '.join(sorted(SUPPORTED_PLATFORMS))}")
        return platform_type

    @staticmethod
    def _get_roblox_security_level(custom_settings: SolidLSPSettings.CustomLSSettings) -> str:
        security_level = custom_settings.get("roblox_security_level", "PluginSecurity")
        if security_level not in SUPPORTED_ROBLOX_SECURITY_LEVELS:
            raise ValueError(
                f"Unsupported Luau Roblox security level: {security_level}. "
                f"Expected one of: {', '.join(sorted(SUPPORTED_ROBLOX_SECURITY_LEVELS))}"
            )
        return security_level

    @classmethod
    def _get_workspace_configuration(cls, custom_settings: SolidLSPSettings.CustomLSSettings) -> dict[str, dict[str, str]]:
        return {"platform": {"type": cls._get_platform_type(custom_settings)}}

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(config, repository_root_path, None, "luau", solidlsp_settings)
        self.server_ready = threading.Event()

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Luau Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "deprecatedSupport": True,
                            "preselectSupport": True,
                        },
                    },
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"],
                    },
                    "signatureHelp": {
                        "dynamicRegistration": True,
                        "signatureInformation": {
                            "documentationFormat": ["markdown", "plaintext"],
                            "parameterInformation": {"labelOffsetSupport": True},
                        },
                    },
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                    "callHierarchy": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "configuration": True,
                    "symbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
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
            # luau-lsp initialization options
            # These can be overridden via .luaurc in the project root
            "initializationOptions": {},
        }
        return initialize_params  # type: ignore[return-value]

    def _start_server(self) -> None:
        """Start Luau Language Server process"""

        def register_capability_handler(params: dict) -> None:
            return

        def workspace_configuration_handler(params: dict) -> list:
            items = params.get("items", [])
            config = self._get_workspace_configuration(self._custom_settings)
            return [config for _ in items]

        def window_log_message(msg: dict) -> None:
            message_text = msg.get("message", "")
            log.info("LSP: window/logMessage: %s", message_text)
            if "workspace ready" in message_text.lower() or "initialized" in message_text.lower():
                log.info("Luau language server signaled readiness")
                self.server_ready.set()

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("workspace/configuration", workspace_configuration_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Luau Language Server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]
        assert "documentSymbolProvider" in init_response["capabilities"]
        assert "referencesProvider" in init_response["capabilities"]

        self.server.notify.initialized({})

        # Wait for luau-lsp to complete initial setup
        log.info("Waiting for Luau language server to become ready...")
        if self.server_ready.wait(timeout=5.0):
            log.info("Luau language server ready")
        else:
            log.warning("Timeout waiting for Luau language server readiness, proceeding anyway")
            self.server_ready.set()
