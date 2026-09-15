"""
End-to-end test for language server file synchronisation as a result of externally-made file changes.

Exercises all three ``FileChangeType`` branches against a real pyright backend:
Created (new caller file), Changed (append a second caller), Deleted (remove the caller file).
Also covers a Roslyn-specific Created regression (test_new_csharp_file_is_folded_into_compilation).
"""

import json
import os
import shutil

import pytest

from serena.agent import SerenaAgent
from serena.project import Project
from serena.tools import FindReferencingSymbolsTool, FindSymbolTool
from solidlsp.ls_config import LanguageServerId
from test.conftest import agent_for_project_context, get_repo_path

pytestmark = pytest.mark.python


class FileSystemSyncTestCase:
    """
    Tests the language server file system synchronisation behaviour, using a reference search
    as an example of a feature that generally depends on the synchronisation.

    It supports two modes:
      * using Serena's tools (where an explicit sync is not needed because it builds on find_symbol)
      * a low-level mode that uses LS methods directly and therefore needs the sync
    """

    # A method that already has a call site in the fixture, so its baseline reference set is non-empty.
    _TARGET_FILE = os.path.join("test_repo", "services.py")
    _TARGET_SYMBOL = "create_user"

    _CALLER_REL_PATH = os.path.join("test_repo", "external_caller.py")
    _CALLER_ONE = "external_caller_one"
    _CALLER_TWO = "external_caller_two"

    def __init__(self, use_serena_tool: bool, tool_use_relative_path: bool = True):
        """
        :param use_serena_tool: whether to use the Serena tool, which does not need an explicit FS sync
        """
        self._use_serena_tool = use_serena_tool
        self._tool_use_relative_path = tool_use_relative_path

    def _caller_source(self, *function_names: str) -> str:
        body = "\n\n".join(
            f"def {name}() -> User:\n    return UserService().{self._TARGET_SYMBOL}('x', 'y', 'z@example.com')" for name in function_names
        )
        return "from test_repo.models import User\nfrom test_repo.services import UserService\n\n\n" + body + "\n"

    def _referencing_symbol_names(self, agent: SerenaAgent) -> list[str]:
        """Names of the symbols that reference ``_TARGET_SYMBOL``, per the warm language server."""
        if self._use_serena_tool:
            tool = agent.get_tool(FindReferencingSymbolsTool)
            with tool.symbol_dict_grouper.disabled_context():
                relative_path = self._TARGET_FILE if self._tool_use_relative_path else ""
                response = tool.apply(name_path=self._TARGET_SYMBOL, relative_path=relative_path)
                ref_symbols = json.loads(response)
                symbol_names = [ref["name_path"].split("/")[-1] for ref in ref_symbols]
                return symbol_names
        else:
            ls = next(iter(agent.get_active_project_or_raise().language_server_manager.iter_language_servers()))
            document_symbols = ls.request_document_symbols(self._TARGET_FILE).get_all_symbols_and_roots()
            target = next((s for s in document_symbols[0] if s.get("name") == self._TARGET_SYMBOL), None)
            assert target is not None and "selectionRange" in target, f"{self._TARGET_SYMBOL} not found in {self._TARGET_FILE}"
            start = target["selectionRange"]["start"]
            references = ls.request_referencing_symbols(self._TARGET_FILE, start["line"], start["character"])
            return [ref.symbol["name"] for ref in references]

    def run(self, tmp_path):
        # Work on an isolated copy so we can freely create/edit/delete files under the project root.
        repo_root = tmp_path / "repo"
        shutil.copytree(get_repo_path(LanguageServerId.PYTHON), repo_root)
        caller_abs = repo_root / self._CALLER_REL_PATH

        with agent_for_project_context(LanguageServerId.PYTHON, str(repo_root)) as agent:
            project = agent.get_active_project_or_raise()

            # Warm the reference index, then establish the freshness baseline (first poll never notifies).
            self._referencing_symbol_names(agent)
            self._sync_fs(project, 0, "<baseline>")

            # --- Created -------------------------------------------------------------------------------
            caller_abs.write_text(self._caller_source(self._CALLER_ONE), encoding="utf-8")

            if not self._use_serena_tool:
                # Adversarial: without the poll, the warm server has never seen the new file -> stale.
                assert self._CALLER_ONE not in self._referencing_symbol_names(agent), "expected the new caller to be invisible before poll"

            self._sync_fs(project, 1, "Created")
            assert self._CALLER_ONE in self._referencing_symbol_names(agent), "new caller must be visible after poll"

            # --- Changed -------------------------------------------------------------------------------
            caller_abs.write_text(self._caller_source(self._CALLER_ONE, self._CALLER_TWO), encoding="utf-8")
            self._sync_fs(project, 1, "Changed")
            names_after_change = self._referencing_symbol_names(agent)
            assert self._CALLER_TWO in names_after_change, "appended caller must be visible after poll"
            assert self._CALLER_ONE in names_after_change

            # --- Deleted -------------------------------------------------------------------------------
            caller_abs.unlink()
            self._sync_fs(project, 1, "Deleted")
            names_after_delete = self._referencing_symbol_names(agent)
            assert self._CALLER_ONE not in names_after_delete, "deleted caller must disappear after poll"
            assert self._CALLER_TWO not in names_after_delete

    def _sync_fs(self, project: Project, num_expected_events: int, event_type: str):
        # apply sync only if Serena's tool is not being used
        if not self._use_serena_tool:
            assert project.ls_sync_file_system_changes() == num_expected_events, f"expected {num_expected_events} {event_type} event(s)"


def test_find_referencing_symbol_tool_handles_sync_with_relative_path(tmp_path):
    """
    Tests that the FindReferencingSymbolsTool handles file system synchronisation correctly when passed a relative path.
    """
    FileSystemSyncTestCase(use_serena_tool=True, tool_use_relative_path=True).run(tmp_path)


def test_find_referencing_symbol_tool_handles_sync_without_relative_path(tmp_path):
    """
    Tests that the FindReferencingSymbolsTool handles file system synchronisation correctly when no relative path is provided.
    """
    FileSystemSyncTestCase(use_serena_tool=True, tool_use_relative_path=False).run(tmp_path)


def test_ls_low_level_find_references_with_explicit_sync(tmp_path):
    """
    Tests that requesting references directly from the LS works if synchronisation is explicitly requested after external file changes.
    """
    FileSystemSyncTestCase(use_serena_tool=False).run(tmp_path)


class SymbolPositionStaleAfterExternalEditTestCase:
    """
    Tests that a Changed (not Created/Deleted) external edit to a file that already has an open
    buffer in the language server session is reflected in symbol positions returned by
    FindSymbolTool. This exercises SolidLanguageServer.resync_open_buffer, which is needed in
    addition to workspace/didChangeWatchedFiles: once a document is open, a server may treat the
    client (not the filesystem) as authoritative for its content and silently ignore watched-file
    notifications for it (observed with pyright).
    """

    _TARGET_FILE = os.path.join("test_repo", "services.py")
    _TARGET_SYMBOL = "create_user"
    _PAD_LINES = 5

    def _find(self, tool: FindSymbolTool) -> dict:
        with tool.symbol_dict_grouper.disabled_context():
            response = tool.apply(name_path_pattern=self._TARGET_SYMBOL, relative_path=self._TARGET_FILE)
        symbols = json.loads(response)
        assert len(symbols) == 1, f"expected exactly one match for {self._TARGET_SYMBOL}, got {symbols}"
        return symbols[0]

    def run(self, tmp_path):
        repo_root = tmp_path / "repo"
        shutil.copytree(get_repo_path(LanguageServerId.PYTHON), repo_root)
        target_abs = repo_root / self._TARGET_FILE

        with agent_for_project_context(LanguageServerId.PYTHON, str(repo_root)) as agent:
            project = agent.get_active_project_or_raise()
            ls = next(iter(project.language_server_manager.iter_language_servers()))
            tool = agent.get_tool(FindSymbolTool)

            # Hold the file's buffer open across the external edit, mirroring the state left
            # behind by a multi-step editing sequence that keeps a buffer open between calls.
            with ls.open_file(self._TARGET_FILE):
                baseline_start_line = self._find(tool)["body_location"]["start_line"]

                original = target_abs.read_text(encoding="utf-8")
                target_abs.write_text(("# pad\n" * self._PAD_LINES) + original, encoding="utf-8")

                after_start_line = self._find(tool)["body_location"]["start_line"]

        assert after_start_line == baseline_start_line + self._PAD_LINES, (
            f"expected {self._TARGET_SYMBOL} to have shifted by {self._PAD_LINES} lines after the "
            f"external edit ({baseline_start_line} -> {baseline_start_line + self._PAD_LINES}), "
            f"but FindSymbolTool reported {after_start_line}"
        )


def test_find_symbol_tool_reflects_external_change_to_open_buffer(tmp_path):
    """
    Regression test for oraios/serena#1593: find_symbol returned a stale position for a symbol
    in a file that was already open in the language server session and was then edited outside
    of Serena's own edit tools.
    """
    SymbolPositionStaleAfterExternalEditTestCase().run(tmp_path)


@pytest.mark.csharp
def test_new_csharp_file_is_folded_into_compilation(tmp_path):
    """
    Regression test for oraios/serena#1961: a .cs file created after the project has already
    been indexed used to stay a standalone Miscellaneous Files document to Roslyn, since the
    generic didChangeWatchedFiles/open-close cycle that poll_and_notify sends for every backend
    is not enough to make Roslyn's project system re-evaluate which files belong to the already-
    loaded .csproj. The tell is a phantom 'Using directive is unnecessary' (IDE0005) on a using
    the new file genuinely needs, since Roslyn cannot resolve the type it imports.
    """
    repo_root = tmp_path / "repo"
    shutil.copytree(get_repo_path(LanguageServerId.CSHARP), repo_root)
    new_file_rel = "UsesPerson.cs"
    new_file_abs = repo_root / new_file_rel

    with agent_for_project_context(LanguageServerId.CSHARP, str(repo_root)) as agent:
        project = agent.get_active_project_or_raise()
        ls = next(iter(project.language_server_manager.iter_language_servers()))

        new_file_abs.write_text(
            "using TestProject.Models;\n\n"
            "namespace TestProject;\n\n"
            "public class UsesPerson\n"
            "{\n"
            "    public Person Get() => new Person();\n"
            "}\n",
            encoding="utf-8",
        )
        assert project.ls_sync_file_system_changes() == 1, "expected exactly one Created event"

        diagnostics = ls.request_text_document_diagnostics(new_file_rel, min_severity=4)
        messages = [d["message"] for d in diagnostics]

        assert not any("unnecessary" in m.lower() for m in messages), (
            f"new file was analyzed as a standalone document instead of being folded into the "
            f"already-loaded project (phantom 'using directive is unnecessary'): {messages}"
        )
        assert any("Person" in m and "name" in m for m in messages), (
            f"expected the real compiler diagnostic for the missing Person(name, age, email) "
            f"argument, which only fires once the file is actually part of the compilation: {messages}"
        )
