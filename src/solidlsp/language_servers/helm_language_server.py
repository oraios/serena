"""Helm language-server adapter.

``helm-ls`` is a small native server which delegates YAML/template intelligence to
Red Hat's ``yaml-language-server``.  Serena manages both executables when they are
not already available on ``PATH``.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import shutil
from typing import Any

from solidlsp.dependency_provider import DownloadedDependency, DownloadedDependencyHashDatabase
from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.settings import SolidLSPSettings

from .yaml_language_server import YamlLanguageServer

log = logging.getLogger(__name__)

DEFAULT_HELM_LS_VERSION = "0.5.4"
HELM_LS_ALLOWED_HOSTS = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")

HELM_LS_ASSETS: dict[PlatformId, str] = {
    PlatformId.OSX_x64: "helm_ls_darwin_amd64",
    PlatformId.OSX_arm64: "helm_ls_darwin_arm64",
    PlatformId.LINUX_x64: "helm_ls_linux_amd64",
    PlatformId.LINUX_arm64: "helm_ls_linux_arm64",
    PlatformId.WIN_x64: "helm_ls_windows_amd64.exe",
}
HELM_LS_ASSET_BY_PLATFORM: dict[PlatformId, str] = {
    **HELM_LS_ASSETS,
    PlatformId.LINUX_MUSL_x64: HELM_LS_ASSETS[PlatformId.LINUX_x64],
    PlatformId.LINUX_MUSL_arm64: HELM_LS_ASSETS[PlatformId.LINUX_arm64],
}

DEFAULT_HELM_SETTINGS: dict[str, Any] = {
    "logLevel": "info",
    "valuesFiles": {
        "mainValuesFile": "values.yaml",
        "lintOverlayValuesFile": "values.lint.yaml",
        "additionalValuesFilesGlobPattern": "values*.yaml",
    },
    "helmLint": {"enabled": True, "ignoredMessages": []},
    "yamlls": {
        "enabled": True,
        "enabledForFilesGlob": "*.{yaml,yml}",
        "diagnosticsLimit": 50,
        "showDiagnosticsDirectly": False,
        "path": "yaml-language-server",
        "initTimeoutSeconds": 3,
        "config": {"schemas": {"kubernetes": "templates/**"}, "completion": True, "hover": True},
    },
}


class HelmLanguageServer(SolidLanguageServer):
    """Language-server adapter for Helm chart YAML and Go-template files."""

    @staticmethod
    def _merge_settings(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(base)
        for key, value in override.items():
            if isinstance(result.get(key), dict) and isinstance(value, dict):
                result[key] = HelmLanguageServer._merge_settings(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        custom = solidlsp_settings.get_ls_specific_settings(config.ls_id)
        helm_settings = custom.get("helm_settings", {})
        if helm_settings is None:
            helm_settings = {}
        if not isinstance(helm_settings, dict):
            raise TypeError("ls_specific_settings.helm.helm_settings must be a dictionary")
        self._helm_settings = self._merge_settings(DEFAULT_HELM_SETTINGS, helm_settings)
        super().__init__(config, repository_root_path, None, "helm", solidlsp_settings)

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        @classmethod
        def _create_dependency(cls, version: str, platform_id: PlatformId) -> DownloadedDependency:
            normalized_version = version.removeprefix("v")
            asset = HELM_LS_ASSET_BY_PLATFORM.get(platform_id)
            if asset is None:
                raise RuntimeError(f"helm-ls has no binary release for platform {platform_id.value}")
            return DownloadedDependency(
                url=f"https://github.com/mrjosh/helm-ls/releases/download/v{normalized_version}/{asset}",
                allowed_hosts=HELM_LS_ALLOWED_HOSTS,
                verified=normalized_version == DEFAULT_HELM_LS_VERSION,
            )

        @classmethod
        def update_dep_hashes(cls) -> None:
            dependencies = [cls._create_dependency(DEFAULT_HELM_LS_VERSION, platform_id) for platform_id in HELM_LS_ASSETS]
            with DownloadedDependencyHashDatabase.get_instance().update_context() as database:
                for dependency in dependencies:
                    database.update(dependency)

        def _get_or_install_core_dependency(self) -> str:
            system_path = shutil.which("helm_ls")
            if system_path:
                log.info("Using system-installed helm-ls at %s", system_path)
                return system_path

            version = str(self._custom_settings.get("helm_ls_version", DEFAULT_HELM_LS_VERSION))
            platform_id = PlatformUtils.get_platform_id()
            asset = HELM_LS_ASSET_BY_PLATFORM.get(platform_id)
            if asset is None:
                raise RuntimeError(f"helm-ls has no binary release for platform {platform_id.value}")
            install_dir = os.path.join(self._ls_resources_dir, f"helm-ls-{version.removeprefix('v')}")
            os.makedirs(install_dir, exist_ok=True)
            executable_path = os.path.join(install_dir, asset)
            if not os.path.exists(executable_path):
                self._create_dependency(version, platform_id).download_to(executable_path)
            if not os.path.exists(executable_path):
                raise FileNotFoundError(f"helm-ls executable not found at {executable_path}")
            if os.name != "nt":
                os.chmod(executable_path, os.stat(executable_path).st_mode | 0o111)
            return executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "serve"]

    def _resolve_yaml_language_server_path(self) -> str | list[str]:
        configured = self._helm_settings["yamlls"].get("path")
        if configured != "yaml-language-server":
            return configured
        env_path = os.environ.get("YAMLLS_PATH")
        if env_path:
            try:
                parsed = json.loads(env_path)
            except json.JSONDecodeError:
                parsed = env_path
            if isinstance(parsed, str | list):
                return parsed
        system_path = shutil.which("yaml-language-server")
        if system_path:
            return system_path
        yaml_settings = {}
        for key in ("yaml_language_server_version", "npm_registry"):
            value = self._custom_settings.get(key)
            if value is not None:
                yaml_settings[key] = value
        provider = YamlLanguageServer.DependencyProvider(
            SolidLSPSettings.CustomLSSettings(yaml_settings),
            os.path.join(self._ls_resources_dir, "yaml-language-server"),
        )
        return provider.create_launch_command()[0]

    def _create_base_initialize_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "locale": "en",
            "capabilities": {
                "workspace": {"workspaceFolders": True, "configuration": True, "didChangeConfiguration": {"dynamicRegistration": True}},
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "documentSymbol": {"dynamicRegistration": True, "hierarchicalDocumentSymbolSupport": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                },
            },
        }
        return params

    def _workspace_configuration(self, params: Any) -> list[dict[str, Any]]:
        settings = copy.deepcopy(self._helm_settings)
        yamlls = settings.setdefault("yamlls", {})
        if isinstance(yamlls, dict) and yamlls.get("path") == "yaml-language-server":
            yamlls["path"] = self._resolve_yaml_language_server_path()
        items = params.get("items", []) if isinstance(params, dict) else []
        if not items:
            return [settings]
        result: list[dict[str, Any]] = []
        for item in items:
            section = item.get("section") if isinstance(item, dict) else None
            result.append(settings if section == "helm-ls" else {})
        return result

    def _start_server(self) -> None:
        self.server.on_request("client/registerCapability", lambda _params: None)
        self.server.on_request("workspace/configuration", self._workspace_configuration)
        self.server.on_notification("window/logMessage", lambda msg: log.info("LSP: window/logMessage: %s", msg))
        self.server.on_notification("$/progress", lambda _params: None)
        self.server.on_notification("textDocument/publishDiagnostics", lambda _params: None)

        self.server.start()
        init_response = self.server.send.initialize(self._create_initialize_params())
        capabilities = init_response.get("capabilities", {})
        required = ("documentSymbolProvider", "definitionProvider", "referencesProvider")
        missing = [name for name in required if not capabilities.get(name)]
        if missing:
            raise RuntimeError(f"helm-ls does not advertise required capabilities: {', '.join(missing)}")
        self.server.notify.initialized({})
