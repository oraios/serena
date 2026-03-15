"""
Integration tests for documentSymbol support with a custom ansible-language-server build.

These tests require a custom build of ansible-language-server that supports
``textDocument/documentSymbol``. Set the ``ANSIBLE_LS_PATH`` environment variable
to point to the custom binary before running::

    ANSIBLE_LS_PATH=/path/to/bin/ansible-language-server uv run poe test -m ansible -v

The custom server returns hierarchical ``DocumentSymbol[]`` with:

- Play → ``SymbolKind.Struct`` (23)
- Section (tasks, handlers, roles) → ``SymbolKind.Field`` (8)
- Task → ``SymbolKind.Function`` (12)
- Block → ``SymbolKind.Namespace`` (3)
- Role → ``SymbolKind.Package`` (4)
"""

import os
from pathlib import Path

import pytest

from serena.constants import SERENA_MANAGED_DIR_NAME
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_types import SymbolKind
from solidlsp.settings import SolidLSPSettings

ANSIBLE_LS_PATH_ENV = "ANSIBLE_LS_PATH"
TEST_REPO_PATH = Path(__file__).parent.parent.parent / "resources" / "repos" / "ansible" / "test_repo"


@pytest.mark.ansible
class TestAnsibleDocumentSymbols:
    """Integration tests for documentSymbol with a custom ansible-language-server."""

    language_server: SolidLanguageServer | None = None

    @classmethod
    def setup_class(cls) -> None:
        ls_path = os.environ.get(ANSIBLE_LS_PATH_ENV)
        if not ls_path or not os.path.exists(ls_path):
            pytest.skip(
                f"Custom ansible-language-server not found. " f"Set {ANSIBLE_LS_PATH_ENV} to run documentSymbol tests.",
                allow_module_level=True,
            )

        repo_path = str(TEST_REPO_PATH)
        config = LanguageServerConfig(
            code_language=Language.ANSIBLE,
            ignored_paths=[],
            trace_lsp_communication=False,
        )
        project_data_path = os.path.join(repo_path, SERENA_MANAGED_DIR_NAME)
        solidlsp_settings = SolidLSPSettings(
            solidlsp_dir=str(Path.home() / ".serena"),
            project_data_path=project_data_path,
            ls_specific_settings={Language.ANSIBLE: {"ls_path": ls_path}},
        )

        cls.language_server = SolidLanguageServer.create(config, repo_path, solidlsp_settings=solidlsp_settings)
        cls.language_server.start()

    @classmethod
    def teardown_class(cls) -> None:
        if cls.language_server is not None:
            cls.language_server.stop()

    # -- helpers --

    def _get_ls(self) -> SolidLanguageServer:
        assert self.language_server is not None
        return self.language_server

    def _get_play_symbol(self) -> dict:
        """Return the root Play symbol from playbook.yml."""
        ls = self._get_ls()
        _, root_syms = ls.request_document_symbols("playbook.yml").get_all_symbols_and_roots()
        play = next((s for s in root_syms if "Configure web servers" in s.get("name", "")), None)
        assert play is not None, f"Play 'Configure web servers' not found. Root symbols: {[s.get('name') for s in root_syms]}"
        return play

    def _get_section(self, section_name: str) -> dict:
        """Return a named section (tasks, handlers) from the Play symbol."""
        play = self._get_play_symbol()
        children = play.get("children", [])
        section = next((c for c in children if c.get("name", "").lower() == section_name), None)
        assert section is not None, f"Section '{section_name}' not found in play children: {[c.get('name') for c in children]}"
        return section

    # -- test cases --

    def test_playbook_returns_symbols(self) -> None:
        """request_document_symbols returns non-empty result for playbook.yml."""
        ls = self._get_ls()
        doc_symbols = ls.request_document_symbols("playbook.yml")
        all_syms, root_syms = doc_symbols.get_all_symbols_and_roots()
        assert root_syms, "Expected at least one root symbol in playbook.yml"
        assert all_syms, "Expected at least one symbol (flat) in playbook.yml"

    def test_playbook_play_is_root_struct(self) -> None:
        """Play 'Configure web servers' is a root symbol with kind=Struct."""
        play = self._get_play_symbol()
        assert play.get("kind") == SymbolKind.Struct, f"Expected Play kind=Struct({SymbolKind.Struct}), got {play.get('kind')}"

    def test_playbook_has_tasks_section(self) -> None:
        """Play contains a 'tasks' child with kind=Field."""
        section = self._get_section("tasks")
        assert section.get("kind") == SymbolKind.Field, f"Expected tasks section kind=Field({SymbolKind.Field}), got {section.get('kind')}"

    def test_playbook_has_handlers_section(self) -> None:
        """Play contains a 'handlers' child with kind=Field."""
        section = self._get_section("handlers")
        assert (
            section.get("kind") == SymbolKind.Field
        ), f"Expected handlers section kind=Field({SymbolKind.Field}), got {section.get('kind')}"

    def test_playbook_tasks_are_functions(self) -> None:
        """Tasks 'Install nginx', 'Start nginx service', 'Copy config file' have kind=Function."""
        ls = self._get_ls()
        all_syms, _ = ls.request_document_symbols("playbook.yml").get_all_symbols_and_roots()
        expected_tasks = {"Install nginx", "Start nginx service", "Copy config file"}
        found_functions = {s.get("name") for s in all_syms if s.get("kind") == SymbolKind.Function}
        for task_name in expected_tasks:
            assert task_name in found_functions, f"Task '{task_name}' not found as Function symbol. Found: {found_functions}"

    def test_playbook_handler_is_function(self) -> None:
        """'Restart nginx' in handlers section has kind=Function."""
        section = self._get_section("handlers")
        handler_children = section.get("children", [])
        handler_names = [h.get("name") for h in handler_children]
        assert "Restart nginx" in handler_names, f"Handler 'Restart nginx' not found. Got: {handler_names}"
        handler = next(h for h in handler_children if h.get("name") == "Restart nginx")
        assert handler.get("kind") == SymbolKind.Function

    def test_hierarchy_play_tasks_task(self) -> None:
        """Verify 3-level hierarchy: Play (Struct) → tasks (Field) → task (Function)."""
        play = self._get_play_symbol()
        assert play.get("kind") == SymbolKind.Struct

        tasks_section = self._get_section("tasks")
        assert tasks_section.get("kind") == SymbolKind.Field

        task_children = tasks_section.get("children", [])
        assert task_children, "tasks section must have task children"
        assert task_children[0].get("kind") == SymbolKind.Function

    def test_roles_file_returns_task_symbols(self) -> None:
        """roles/common/tasks/main.yml returns 3 Function symbols at root level."""
        ls = self._get_ls()
        roles_file = os.path.join("roles", "common", "tasks", "main.yml")
        all_syms, root_syms = ls.request_document_symbols(roles_file).get_all_symbols_and_roots()
        assert all_syms, f"Expected symbols in {roles_file}"

        # roles task file has tasks at root level (no play wrapper)
        task_syms = [s for s in root_syms if s.get("kind") == SymbolKind.Function]
        assert len(task_syms) >= 3, f"Expected at least 3 task symbols, got {len(task_syms)}"

        task_names = {s.get("name") for s in task_syms}
        for expected in ("Update package cache", "Install common packages", "Create deploy user"):
            assert expected in task_names, f"Task '{expected}' not found. Got: {task_names}"
