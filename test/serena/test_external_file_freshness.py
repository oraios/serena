"""End-to-end test for detecting externally-made file changes.

Reproduces the staleness bug and verifies the fix: a warm language server serves stale symbol
results for files edited outside of Serena's own tools, and ``Project.poll_and_notify_file_changes``
makes those edits visible again by firing ``workspace/didChangeWatchedFiles`` (plus an open/close
cycle for newly created files).

Exercises all three ``FileChangeType`` branches against a real pyright backend:
Created (new caller file), Changed (append a second caller), Deleted (remove the caller file).
"""

import os
import shutil

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.conftest import get_repo_path, project_with_ls_context

pytestmark = pytest.mark.python

# A method that already has a call site in the fixture, so its baseline reference set is non-empty.
_TARGET_FILE = os.path.join("test_repo", "services.py")
_TARGET_SYMBOL = "create_user"

_CALLER_REL_PATH = os.path.join("test_repo", "external_caller.py")
_CALLER_ONE = "external_caller_one"
_CALLER_TWO = "external_caller_two"


def _caller_source(*function_names: str) -> str:
    body = "\n\n".join(
        f"def {name}() -> User:\n    return UserService().{_TARGET_SYMBOL}('x', 'y', 'z@example.com')" for name in function_names
    )
    return "from test_repo.models import User\nfrom test_repo.services import UserService\n\n\n" + body + "\n"


def _referencing_symbol_names(ls: SolidLanguageServer) -> list[str]:
    """Names of the symbols that reference ``_TARGET_SYMBOL``, per the warm language server."""
    document_symbols = ls.request_document_symbols(_TARGET_FILE).get_all_symbols_and_roots()
    target = next((s for s in document_symbols[0] if s.get("name") == _TARGET_SYMBOL), None)
    assert target is not None and "selectionRange" in target, f"{_TARGET_SYMBOL} not found in {_TARGET_FILE}"
    start = target["selectionRange"]["start"]
    references = ls.request_referencing_symbols(_TARGET_FILE, start["line"], start["character"])
    return [ref.symbol["name"] for ref in references]


def test_external_edits_become_visible_after_poll(tmp_path):
    # Work on an isolated copy so we can freely create/edit/delete files under the project root.
    repo_root = tmp_path / "repo"
    shutil.copytree(get_repo_path(Language.PYTHON), repo_root)
    caller_abs = repo_root / _CALLER_REL_PATH

    with project_with_ls_context(Language.PYTHON, str(repo_root)) as project:
        language_server = next(iter(project.language_server_manager.iter_language_servers()))

        # Warm the reference index, then establish the freshness baseline (first poll never notifies).
        _referencing_symbol_names(language_server)
        assert project.poll_and_notify_file_changes() == 0, "first poll must only establish the baseline"

        # --- Created -------------------------------------------------------------------------------
        caller_abs.write_text(_caller_source(_CALLER_ONE), encoding="utf-8")

        # Adversarial: without the poll, the warm server has never seen the new file -> stale.
        assert _CALLER_ONE not in _referencing_symbol_names(language_server), "expected the new caller to be invisible before poll"

        assert project.poll_and_notify_file_changes() == 1, "one Created event expected"
        assert _CALLER_ONE in _referencing_symbol_names(language_server), "new caller must be visible after poll"

        # --- Changed -------------------------------------------------------------------------------
        caller_abs.write_text(_caller_source(_CALLER_ONE, _CALLER_TWO), encoding="utf-8")
        assert project.poll_and_notify_file_changes() == 1, "one Changed event expected"
        names_after_change = _referencing_symbol_names(language_server)
        assert _CALLER_TWO in names_after_change, "appended caller must be visible after poll"
        assert _CALLER_ONE in names_after_change

        # --- Deleted -------------------------------------------------------------------------------
        caller_abs.unlink()
        assert project.poll_and_notify_file_changes() == 1, "one Deleted event expected"
        names_after_delete = _referencing_symbol_names(language_server)
        assert _CALLER_ONE not in names_after_delete, "deleted caller must disappear after poll"
        assert _CALLER_TWO not in names_after_delete


def test_first_poll_is_baseline_only(tmp_path):
    """A newly-loaded project must not report its entire pre-existing file set as changed."""
    repo_root = tmp_path / "repo"
    shutil.copytree(get_repo_path(Language.PYTHON), repo_root)
    with project_with_ls_context(Language.PYTHON, str(repo_root)) as project:
        assert project.poll_and_notify_file_changes() == 0
        # No external edits between the two calls -> still nothing to report.
        assert project.poll_and_notify_file_changes() == 0


# --- Fast wiring tests for Tool._maybe_refresh_project_freshness (no language server needed) --------


class _StubConfig:
    def __init__(self, detect_external_file_changes: bool) -> None:
        self.detect_external_file_changes = detect_external_file_changes


class _StubProject:
    def __init__(self) -> None:
        self.poll_calls = 0

    def poll_and_notify_file_changes(self) -> int:
        self.poll_calls += 1
        return 0


class _StubAgent:
    def __init__(self, *, detect: bool, project) -> None:
        self.serena_config = _StubConfig(detect)
        self._project = project

    def get_active_project(self):
        return self._project


class _StubTool:
    """Minimal stand-in used only to drive Tool._maybe_refresh_project_freshness in isolation."""

    def __init__(self, *, symbolic: bool, detect: bool = True, project=None) -> None:
        self._symbolic = symbolic
        self.agent = _StubAgent(detect=detect, project=project if project is not None else _StubProject())

    def is_symbolic(self) -> bool:
        return self._symbolic


def _refresh(tool: "_StubTool") -> None:
    from serena.tools.tools_base import Tool

    Tool._maybe_refresh_project_freshness(tool)  # type: ignore[arg-type]


def test_refresh_polls_only_for_symbolic_tools_when_enabled():
    symbolic = _StubTool(symbolic=True)
    _refresh(symbolic)
    assert symbolic.agent._project.poll_calls == 1

    non_symbolic = _StubTool(symbolic=False)
    _refresh(non_symbolic)
    assert non_symbolic.agent._project.poll_calls == 0


def test_refresh_is_skipped_when_disabled_by_config():
    tool = _StubTool(symbolic=True, detect=False)
    _refresh(tool)
    assert tool.agent._project.poll_calls == 0


def test_refresh_is_noop_without_active_project():
    tool = _StubTool(symbolic=True, project=None)
    tool.agent._project = None  # type: ignore[assignment]
    _refresh(tool)  # must not raise


def test_refresh_swallows_poll_errors():
    class _Boom(_StubProject):
        def poll_and_notify_file_changes(self) -> int:
            raise RuntimeError("boom")

    tool = _StubTool(symbolic=True, project=_Boom())
    _refresh(tool)  # a poll failure must never break the tool call
