# SPDX-License-Identifier: GPL-3.0-or-later
import logging
from typing import TYPE_CHECKING

from overrides import override
from sensai.util.logging import LogTime

from serena.language_backend import BuiltinLanguageBackend, LanguageBackend
from serena.util.file_proxy import FileProxy, LocalProjectFileProxy

if TYPE_CHECKING:
    from serena.agent import SerenaAgent
    from serena.code_editor import LanguageServerCodeEditor
    from serena.project import Project
    from serena.repl.facade import ApiScope, Facade
    from serena.tools import Tool

log = logging.getLogger(__name__)


class LanguageBackendLSP(LanguageBackend):
    def __init__(self):
        super().__init__(BuiltinLanguageBackend.LSP.value)

    @override
    def get_lsp_tool_class_replacements(self) -> "dict[type[Tool], type[Tool]]":
        return {}

    @override
    def create_facades(self, agent: "SerenaAgent", api_scope: "ApiScope") -> list["Facade"]:
        from ..repl.api.lsp_api import LspApi
        from ..repl.facade import Facade

        return [Facade.from_api(LspApi(agent), api_scope)]

    @override
    def init_active_project(self, agent: "SerenaAgent") -> None:
        with LogTime("Language server initialization", logger=log):
            agent.reset_language_server_manager()

    @override
    def shutdown_active_project(self, project: "Project", timeout: float) -> None:
        # nothing to do; the language server manager is already shut down by the project itself
        pass

    @override
    def get_project_activation_statement(self, project: "Project") -> str:
        language_servers_str = ", ".join([ls.get_key() for ls in project.project_config.language_servers])
        return f"Active language servers: {language_servers_str}.\n"

    @override
    def get_config_overview_statement(self, project: "Project") -> str:
        return f"Language server status: {project.get_language_server_manager_status()}\n"

    @override
    def create_code_editor(self, project: "Project") -> "LanguageServerCodeEditor":
        from serena.code_editor import LanguageServerCodeEditor
        from serena.symbol import LanguageServerSymbolRetriever

        symbol_retriever = LanguageServerSymbolRetriever(project)
        return LanguageServerCodeEditor(symbol_retriever)

    @override
    def is_source_file(self, abs_path: str, project: "Project") -> bool:
        # `abs_path` is a path to an existing file, so the path-aware question is the one to ask:
        # it decides an extensionless script by its shebang line, which the name alone cannot.
        return any(language.get_source_fn_matcher().is_relevant_file(abs_path) for language in project.project_config.language_servers)

    @override
    def is_external_path(self, relative_path: str) -> bool:
        # LSP backend currently uses only true project-relative paths
        return False

    @override
    def create_file_proxy(self, relative_path: str, project: "Project") -> FileProxy:
        return LocalProjectFileProxy(relative_path, project)
