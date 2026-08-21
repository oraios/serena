"""Provides InTouch QuickScript support through the external intouch-language server."""

import logging
import os
import shutil

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import FilenameMatcher, LanguageServerConfig, register_ls
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class QuickScriptLanguageServer(SolidLanguageServer):
    """Connect Serena to the native intouch-language QuickScript server."""

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(config, repository_root_path, None, "quickscript", solidlsp_settings)

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            configured_path = self._custom_settings.get("ls_path")
            environment_path = os.environ.get("INTOUCH_LANGUAGE_SERVER_PATH")
            core_path = configured_path or environment_path
            if isinstance(core_path, str) and core_path:
                return core_path
            raise FileNotFoundError(
                "Set ls_specific_settings.quickscript.ls_path or "
                "INTOUCH_LANGUAGE_SERVER_PATH to the intouch-language server entry point."
            )

        def _create_launch_command(self, core_path: str) -> list[str]:
            if not os.path.isfile(core_path):
                raise FileNotFoundError(f"QuickScript language server entry point not found: {core_path}")
            node_path = shutil.which("node")
            if node_path is None:
                raise FileNotFoundError("Node.js is required to launch the QuickScript language server.")
            return [node_path, core_path, "--stdio"]

    def _supports_pull_diagnostics(self) -> bool:
        return False

    def _create_base_initialize_params(self) -> dict:
        return {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {"dynamicRegistration": True, "hierarchicalDocumentSymbolSupport": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                },
                "workspace": {"workspaceFolders": True, "configuration": True},
            },
        }

    def _start_server(self) -> None:
        self.server.start()
        self.server.send.initialize(self._create_initialize_params())
        self.server.notify.initialized({})


QUICKSCRIPT = register_ls(
    id="quickscript",
    matcher=FilenameMatcher(".vbi", ".vi", case_sensitive=False),
    implementation=QuickScriptLanguageServer,
)
