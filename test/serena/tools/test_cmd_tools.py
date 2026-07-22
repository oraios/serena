"""Tests for the shell command tool's default-availability and cwd containment."""

import sys
from pathlib import Path

import pytest

from serena.agent import ToolSet
from serena.config.context_mode import SerenaAgentContext
from serena.tools import ExecuteShellCommandTool, ToolRegistry
from serena.tools.cmd_tools import resolve_cwd_within_project

SHELL_TOOL_NAME = ExecuteShellCommandTool.get_name_from_cls()


class TestShellToolIsOptional:
    """The shell tool must be opt-in (disabled by default)."""

    def test_shell_tool_is_optional_not_default(self) -> None:
        # registry classification: optional, not default-enabled
        registry = ToolRegistry()
        assert SHELL_TOOL_NAME in registry.get_tool_names_optional()
        assert SHELL_TOOL_NAME not in registry.get_tool_names_default_enabled()

    def test_shell_tool_absent_from_default_toolset(self) -> None:
        # a bare default tool set does not contain the shell tool
        assert SHELL_TOOL_NAME not in ToolSet.default().get_tool_names()


class TestShellToolContextResolution:
    """The shell tool must be re-added for the `agent` and `desktop-app` contexts, and remain absent
    for IDE/CLI coding contexts that already excluded it.
    """

    def test_present_for_agent_context(self) -> None:
        toolset = ToolSet.default().apply(SerenaAgentContext.load("agent"))
        assert SHELL_TOOL_NAME in toolset.get_tool_names()

    def test_present_for_desktop_app_context(self) -> None:
        toolset = ToolSet.default().apply(SerenaAgentContext.load("desktop-app"))
        assert SHELL_TOOL_NAME in toolset.get_tool_names()

    def test_absent_for_claude_code_context(self) -> None:
        toolset = ToolSet.default().apply(SerenaAgentContext.load("claude-code"))
        assert SHELL_TOOL_NAME not in toolset.get_tool_names()

    def test_composition_ordering_stable(self) -> None:
        # applying an enabling context then a disabling one leaves the tool absent (subtractive wins).
        # ToolSet.apply is variadic and processes definitions left to right.
        toolset = ToolSet.default().apply(SerenaAgentContext.load("agent"), SerenaAgentContext.load("claude-code"))
        assert SHELL_TOOL_NAME not in toolset.get_tool_names()

    def test_mode_exclusion_is_load_bearing_over_enabling_context(self) -> None:
        # regression guard: the `execute_shell_command` entry in planning/onboarding modes' excluded_tools
        # is NOT dead config. When such a mode composes over a context that enables the shell tool (agent),
        # the mode's exclusion is what removes it again. Removing those entries would leak shell access into
        # read-only planning mode.
        from serena.config.context_mode import SerenaAgentMode

        agent_ctx = SerenaAgentContext.load("agent")
        assert SHELL_TOOL_NAME in ToolSet.default().apply(agent_ctx).get_tool_names()
        for mode_name in ("planning", "onboarding"):
            toolset = ToolSet.default().apply(agent_ctx, SerenaAgentMode.load(mode_name))
            assert SHELL_TOOL_NAME not in toolset.get_tool_names(), f"mode '{mode_name}' must strip the shell tool"


class TestResolveCwdWithinProject:
    """`resolve_cwd_within_project` confines the shell working directory to the project root.

    Note: this is a best-effort ergonomic guard, NOT a security boundary (the shell command string
    itself can reference any path under shell=True). The real control is that the tool is optional.
    """

    @pytest.fixture
    def project_root(self, tmp_path: Path) -> Path:
        # a realpath'd project root with an in-project subdirectory
        root = (tmp_path / "proj").resolve()
        (root / "sub").mkdir(parents=True)
        return root

    def test_none_resolves_to_root(self, project_root: Path) -> None:
        assert resolve_cwd_within_project(None, str(project_root)) == str(project_root)

    def test_dot_resolves_to_root(self, project_root: Path) -> None:
        assert resolve_cwd_within_project(".", str(project_root)) == str(project_root)

    def test_absolute_root_allowed(self, project_root: Path) -> None:
        assert resolve_cwd_within_project(str(project_root), str(project_root)) == str(project_root)

    def test_in_project_relative_subdir_allowed(self, project_root: Path) -> None:
        assert resolve_cwd_within_project("sub", str(project_root)) == str(project_root / "sub")

    def test_absolute_outside_rejected(self, project_root: Path, tmp_path: Path) -> None:
        outside = (tmp_path / "outside").resolve()
        outside.mkdir()
        with pytest.raises(ValueError, match="outside the project root"):
            resolve_cwd_within_project(str(outside), str(project_root))

    def test_relative_climb_rejected(self, project_root: Path) -> None:
        with pytest.raises(ValueError, match="outside the project root"):
            resolve_cwd_within_project("../..", str(project_root))

    def test_path_sibling_rejected(self, tmp_path: Path) -> None:
        # guards the prefix-collision bug: '<root>-evil' must NOT count as inside '<root>'
        root = (tmp_path / "proj").resolve()
        root.mkdir()
        sibling = (tmp_path / "proj-evil").resolve()
        sibling.mkdir()
        with pytest.raises(ValueError, match="outside the project root"):
            resolve_cwd_within_project(str(sibling), str(root))

    def test_symlink_escape_rejected(self, project_root: Path, tmp_path: Path) -> None:
        # a symlink inside the project pointing outside must be rejected (realpath resolves it out)
        outside = (tmp_path / "outside").resolve()
        outside.mkdir()
        link = project_root / "escape"
        link.symlink_to(outside, target_is_directory=True)
        with pytest.raises(ValueError, match="outside the project root"):
            resolve_cwd_within_project("escape", str(project_root))


class TestExecuteShellCommandCwd:
    """End-to-end containment via `ExecuteShellCommandTool.apply`, exercising the full method (not just
    the helper) so the broadened existence check and the resolution branches are covered together.
    """

    @pytest.fixture
    def shell_tool(self, tmp_path: Path) -> ExecuteShellCommandTool:
        # a tool instance whose project root is a temp directory, without constructing a full agent/LSP
        root = (tmp_path / "proj").resolve()
        (root / "sub").mkdir(parents=True)
        tool = ExecuteShellCommandTool.__new__(ExecuteShellCommandTool)
        tool.get_project_root = lambda: str(root)
        return tool

    @staticmethod
    def _reported_cwd(result_json: str) -> Path:
        import json

        return Path(json.loads(result_json)["stdout"].strip()).resolve()

    @staticmethod
    def _echo_cwd_command() -> str:
        # portable "print my cwd" using the current interpreter (bare `python` may be absent in CI)
        return f'{sys.executable} -c "import os;print(os.getcwd())"'

    def test_none_runs_in_project_root(self, shell_tool: ExecuteShellCommandTool) -> None:
        result = shell_tool.apply(self._echo_cwd_command(), cwd=None, max_answer_chars=100_000)
        assert self._reported_cwd(result) == Path(shell_tool.get_project_root()).resolve()

    def test_dot_runs_in_project_root(self, shell_tool: ExecuteShellCommandTool) -> None:
        result = shell_tool.apply(self._echo_cwd_command(), cwd=".", max_answer_chars=100_000)
        assert self._reported_cwd(result) == Path(shell_tool.get_project_root()).resolve()

    def test_absolute_root_runs_in_project_root(self, shell_tool: ExecuteShellCommandTool) -> None:
        result = shell_tool.apply(self._echo_cwd_command(), cwd=shell_tool.get_project_root(), max_answer_chars=100_000)
        assert self._reported_cwd(result) == Path(shell_tool.get_project_root()).resolve()

    def test_in_project_subdir_runs_there(self, shell_tool: ExecuteShellCommandTool) -> None:
        result = shell_tool.apply(self._echo_cwd_command(), cwd="sub", max_answer_chars=100_000)
        assert self._reported_cwd(result) == (Path(shell_tool.get_project_root()) / "sub").resolve()

    def test_outside_cwd_raises_via_apply(self, shell_tool: ExecuteShellCommandTool) -> None:
        with pytest.raises(ValueError, match="outside the project root"):
            shell_tool.apply(self._echo_cwd_command(), cwd="../..")

    def test_nonexistent_in_project_dir_raises_file_not_found(self, shell_tool: ExecuteShellCommandTool) -> None:
        # broadened existence check: a contained-but-missing dir raises before execution
        with pytest.raises(FileNotFoundError):
            shell_tool.apply(self._echo_cwd_command(), cwd="does_not_exist")
