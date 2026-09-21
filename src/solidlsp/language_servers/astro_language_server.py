"""
Provides Astro-specific instantiation of the LanguageServer class using
@astrojs/language-server.
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import Any

from overrides import override

from solidlsp.language_servers.common import (
    RuntimeDependency,
    RuntimeDependencyCollection,
    build_npm_install_command,
)
from solidlsp.ls import (
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig, LanguageServerId
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)
ASTRO_EXT = frozenset({".astro"})
TS_EXT = frozenset({".ts", ".tsx", ".mts", ".cts"})
JS_EXT = frozenset({".js", ".jsx", ".mjs", ".cjs"})


class AstroLanguageServer(SolidLanguageServer):
    """
    Astro language server using @astrojs/language-server.
    """

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def __init__(
            self,
            custom_settings: SolidLSPSettings.CustomLSSettings,
            ls_resources_dir: str,
            ts_settings: SolidLSPSettings.CustomLSSettings,
        ) -> None:
            super().__init__(custom_settings, ls_resources_dir)
            self._ts_settings = ts_settings

        def _get_or_install_core_dependency(self) -> str:
            if shutil.which("node") is None:
                raise SolidLSPException("node is not installed or isn't in PATH. Please install NodeJS and try again.")
            if shutil.which("npm") is None:
                raise SolidLSPException("npm is not installed or isn't in PATH. Please install npm and try again.")

            package_version = self._custom_settings.get("astro_language_server_version", "2.17.0")
            typescript_version = self._custom_settings.get("typescript_version", self._ts_settings.get("typescript_version", "5.8.2"))
            npm_registry = self._custom_settings.get("npm_registry", self._ts_settings.get("npm_registry"))

            install_dir = os.path.join(self._ls_resources_dir, f"astro-lsp-{package_version}")
            executable_path = os.path.join(install_dir, "node_modules", ".bin", "astro-ls")
            if os.name == "nt":
                executable_path += ".cmd"

            version_file = os.path.join(install_dir, ".installed_version")
            expected_version = f"{package_version}_{typescript_version}"
            needs_install = not os.path.exists(executable_path)
            if not needs_install:
                if os.path.exists(version_file):
                    with open(version_file) as fv:
                        if fv.read().strip() != expected_version:
                            needs_install = True
                else:
                    needs_install = True

            if needs_install:
                log.info(
                    "Installing @astrojs/language-server@%s + typescript@%s ...",
                    package_version,
                    typescript_version,
                )
                runtime_deps = [
                    RuntimeDependency(
                        id="@astrojs/language-server",
                        description="Astro language server",
                        command=build_npm_install_command("@astrojs/language-server", package_version, npm_registry),
                        platform_id="any",
                    ),
                    RuntimeDependency(
                        id="typescript",
                        description="TypeScript language service for Astro TSDK",
                        command=build_npm_install_command("typescript", typescript_version, npm_registry),
                        platform_id="any",
                    ),
                ]
                RuntimeDependencyCollection(runtime_deps).install(install_dir)
                with open(version_file, "w") as fv:
                    fv.write(expected_version)

            if not os.path.exists(executable_path):
                raise FileNotFoundError(
                    f"executable not found at {executable_path}; "
                    f"npm install of @astrojs/language-server@{package_version} did not produce the expected binary."
                )
            return executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "--stdio"]

    def __init__(self, config: LanguageServerConfig, repo_path: str, solidlsp_settings: SolidLSPSettings):
        resolved_root = os.path.abspath(repo_path)
        super().__init__(
            config,
            resolved_root,
            None,
            "astro",
            solidlsp_settings,
        )
        self.repo_path: str = resolved_root
        self._lsp_configuration: dict[str, Any] = {}

    def _get_install_dir(self) -> str:
        version = self._custom_settings.get("astro_language_server_version", "2.17.0")
        return os.path.join(self._ls_resources_dir, f"astro-lsp-{version}")

    @property
    def tsdk_path(self) -> str:
        workspace_tsdk = os.path.join(self.repo_path, "node_modules", "typescript", "lib")
        if os.path.isdir(workspace_tsdk):
            return workspace_tsdk
        install_dir = self._get_install_dir()
        tsdk_candidate = os.path.join(install_dir, "node_modules", "typescript", "lib")
        if not os.path.isdir(tsdk_candidate):
            raise FileNotFoundError(
                f"TypeScript SDK not found at expected path: {tsdk_candidate}. Installation via DependencyProvider failed."
            )
        return tsdk_candidate

    @override
    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        ts_settings = self._solidlsp_settings.get_ls_specific_settings(LanguageServerId.TYPESCRIPT)
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir, ts_settings)

    @override
    def _create_base_initialize_params(self) -> dict:
        lsp_config: dict[str, Any] = {
            "astro": {
                "contentIntellisense": True,
            },
            "typescript": {"tsdk": self.tsdk_path},
            "javascript": {"tsdk": self.tsdk_path},
        }
        for key, val in self._custom_settings.get("initialization_options_configuration", {}).items():
            if key in lsp_config and isinstance(lsp_config[key], dict) and isinstance(val, dict):
                lsp_config[key] = {**lsp_config[key], **val}
            else:
                lsp_config[key] = val

        self._lsp_configuration = lsp_config

        initialize_params: dict = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "signatureHelp": {"dynamicRegistration": True},
                    "codeAction": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                    "implementation": {"dynamicRegistration": True},
                    "typeDefinition": {"dynamicRegistration": True},
                    "diagnostic": {"dynamicRegistration": True},
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {
                    "applyEdit": True,
                    "configuration": True,
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {"dynamicRegistration": True, "relativePatternSupport": True},
                    "symbol": {"dynamicRegistration": True},
                    "diagnostics": {"refreshSupport": True},
                    "fileOperations": {"didRename": True},
                },
            },
            "initializationOptions": {
                "typescript": {
                    "tsdk": self.tsdk_path,
                },
                "configuration": lsp_config,
            },
        }
        return initialize_params

    def _start_server(self) -> None:
        def window_log_message(msg: dict) -> None:
            log.info("Astro LSP log: %s", msg.get("message"))

        def register_capability_handler(_params: dict) -> None:
            return

        def configuration_handler(_params: dict) -> list[Any]:
            items = _params.get("items", [])
            results = []
            for item in items:
                section = item.get("section")
                if not section:
                    results.append(None)
                    continue
                # Support nested dot notation, e.g. "html.customData", "astro.contentIntellisense"
                parts = section.split(".")
                curr: Any = self._lsp_configuration
                found = True
                for p in parts:
                    if isinstance(curr, dict) and p in curr:
                        curr = curr[p]
                    else:
                        found = False
                        break
                if found:
                    results.append(curr)
                elif section.endswith(".customData"):
                    results.append([])
                else:
                    results.append(None)
            return results

        def workspace_apply_edit_handler(_params: dict) -> dict[str, Any]:
            return {"applied": False}

        def work_done_progress_create(_params: dict) -> dict:
            return {}

        def do_nothing(_params: dict) -> None:
            pass

        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("window/workDoneProgress/create", work_done_progress_create)
        self.server.on_request("workspace/applyEdit", workspace_apply_edit_handler)
        self.server.on_request("workspace/configuration", configuration_handler)
        self.server.on_request("workspace/diagnostic/refresh", do_nothing)
        self.server.on_request("workspace/inlayHint/refresh", do_nothing)
        self.server.on_request("workspace/semanticTokens/refresh", do_nothing)
        self.server.start()

        init_params = self._create_initialize_params()
        init_response = self.server.send.initialize(init_params)

        capabilities = init_response.get("capabilities", {})
        if "documentSymbolProvider" not in capabilities:
            raise SolidLSPException("Astro LSP did not advertise documentSymbolProvider")
        if "definitionProvider" not in capabilities:
            raise SolidLSPException("Astro LSP did not advertise definitionProvider")

        self.server.notify.initialized({})

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext in ASTRO_EXT:
            return "astro"
        if ext in TS_EXT:
            return "typescript"
        if ext in JS_EXT:
            return "javascript"
        return self.language_id

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["dist", "build", "coverage", ".astro"]
