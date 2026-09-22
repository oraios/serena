# SPDX-License-Identifier: GPL-3.0-or-later
import logging
from typing import TYPE_CHECKING

from overrides import override

from serena.code_editor import JetBrainsCodeEditor
from serena.jetbrains import launch_coordinator
from serena.language_backend import BuiltinLanguageBackend, LanguageBackend

from ..util.file_proxy import FileProxy, LocalProjectFileProxy
from . import jetbrains_types as jb

if TYPE_CHECKING:
    from serena.agent import SerenaAgent
    from serena.code_editor import CodeEditor
    from serena.project import Project
    from serena.repl.facade import ApiScope, Facade
    from serena.tools import Tool

log = logging.getLogger(__name__)


class LanguageBackendJetBrains(LanguageBackend):
    def __init__(self):
        super().__init__(BuiltinLanguageBackend.JETBRAINS.value)

    @override
    def get_lsp_tool_class_replacements(self) -> "dict[type[Tool], type[Tool]]":
        from ..tools import jetbrains_tools, symbol_tools

        return {
            symbol_tools.FindSymbolTool: jetbrains_tools.JetBrainsFindSymbolTool,
            symbol_tools.GetSymbolsOverviewTool: jetbrains_tools.JetBrainsGetSymbolsOverviewTool,
            symbol_tools.FindReferencingSymbolsTool: jetbrains_tools.JetBrainsFindReferencingSymbolsTool,
            symbol_tools.FindImplementationsTool: jetbrains_tools.JetBrainsFindImplementationsTool,
            symbol_tools.FindDeclarationTool: jetbrains_tools.JetBrainsFindDeclarationTool,
            symbol_tools.RenameSymbolTool: jetbrains_tools.JetBrainsRenameTool,
            symbol_tools.SafeDeleteSymbol: jetbrains_tools.JetBrainsSafeDeleteTool,
        }

    @override
    def create_facades(self, agent: "SerenaAgent", api_scope: "ApiScope") -> list["Facade"]:
        from ..repl.api.jb_api import JetBrainsApi
        from ..repl.facade import Facade

        return [Facade.from_api(JetBrainsApi(agent), api_scope)]

    @override
    def init_active_project(self, agent: "SerenaAgent") -> None:
        project = agent.get_active_project_or_raise()
        client = launch_coordinator.find_plugin_server(project)
        if client is not None:
            log.info("Found Serena JetBrains Plugin server: %s", client)
        else:
            log.info("Serena JetBrains Plugin server not found for project %s", project.project_name)
            launch_command = agent.serena_config.jetbrains_launch_command
            if launch_command:
                launch_coordinator.launch_and_wait_for_plugin_server(project, launch_command)

    @override
    def shutdown_active_project(self, project: "Project", timeout: float) -> None:
        pass

    @override
    def create_code_editor(self, project: "Project") -> "CodeEditor":
        return JetBrainsCodeEditor(project)

    @override
    def is_source_file(self, abs_path: str, project: "Project") -> bool:
        # no distinction is made; every file is potentially a source file
        return True

    @override
    def is_external_path(self, relative_path: str) -> bool:
        return relative_path.startswith(jb.JB_EXTERNAL_FILE_PREFIX)

    @override
    def create_file_proxy(self, relative_path: str, project: "Project") -> FileProxy:
        if self.is_external_path(relative_path):
            return JetBrainsFileProxy(relative_path, project)
        return LocalProjectFileProxy(relative_path, project)


class JetBrainsFileProxy(FileProxy):
    """
    Retrieves the contents of a file from the JetBrains plugin via the plugin client, given its relative path,
    which may be an external path (e.g., "<ext:FileUtil.class|472e0a13>")
    """

    def __init__(self, relative_path: str, project: "Project"):
        self._relative_path = relative_path
        self._project = project

    def get_contents(self) -> str:
        from serena.jetbrains.jetbrains_plugin_client import JetBrainsPluginClient

        client = JetBrainsPluginClient.from_project(self._project)
        return client.read_file(self._relative_path)

    def get_relative_path(self) -> str:
        return self._relative_path

    def is_glob_supported(self):
        return False
