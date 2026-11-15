"""Tests for SerenaAgent._run_activation_command."""

import logging
import os
import sys
from pathlib import Path

import pytest

from serena.config.serena_config import ProjectConfig, SerenaConfig
from serena.project import Project
from solidlsp.ls_config import LanguageServerId


def _make_project(
    project_root: Path,
    activation_command: str | None = None,
    activation_command_timeout: float = 180.0,
    trusted: bool = True,
) -> Project:
    """Create a minimal Project pointing at project_root with the given activation settings."""
    serena_config = SerenaConfig(
        gui_log_window=False,
        web_dashboard=False,
        trusted_project_path_patterns=["**"] if trusted else [],
    )
    project_config = ProjectConfig(
        project_name="test-activation",
        language_servers=[LanguageServerId.PYTHON],
        activation_command=activation_command,
        activation_command_timeout=activation_command_timeout,
    )
    return Project(
        project_root=str(project_root),
        project_config=project_config,
        serena_config=serena_config,
    )


class TestRunActivationCommand:
    """Unit tests for SerenaAgent._run_activation_command."""

    def _make_agent(self, project: Project):
        from serena.agent import SerenaAgent

        agent = SerenaAgent.__new__(SerenaAgent)
        # wire up only what _run_activation_command needs
        agent.serena_config = project.serena_config
        return agent

    def test_no_command_does_nothing(self, tmp_path: Path, caplog):
        project = _make_project(tmp_path, activation_command=None)
        agent = self._make_agent(project)
        with caplog.at_level(logging.INFO):
            agent._run_project_activation_command(project)
        assert "activation_command" not in caplog.text

    def test_trusted_command_runs_in_project_root(self, tmp_path: Path):
        sentinel = tmp_path / "sentinel.txt"
        # write a sentinel file from within the command to confirm cwd is project_root
        if sys.platform == "win32":
            cmd = "type nul > sentinel.txt"
        else:
            cmd = "touch sentinel.txt"
        project = _make_project(tmp_path, activation_command=cmd, trusted=True)
        agent = self._make_agent(project)
        agent._run_project_activation_command(project)
        assert sentinel.exists(), "Command did not run in project root (sentinel file missing)"

    def test_untrusted_project_skips_command(self, tmp_path: Path, caplog):
        sentinel = tmp_path / "sentinel.txt"
        cmd = "touch sentinel.txt" if sys.platform != "win32" else "type nul > sentinel.txt"
        project = _make_project(tmp_path, activation_command=cmd, trusted=False)
        agent = self._make_agent(project)
        with caplog.at_level(logging.WARNING):
            agent._run_project_activation_command(project)
        assert not sentinel.exists(), "Command must not run for untrusted project"
        assert "not trusted" in caplog.text

    def test_failing_command_logs_error_and_continues(self, tmp_path: Path, caplog):
        cmd = "exit 1" if sys.platform != "win32" else "cmd /c exit 1"
        project = _make_project(tmp_path, activation_command=cmd, trusted=True)
        agent = self._make_agent(project)
        with caplog.at_level(logging.ERROR):
            agent._run_project_activation_command(project)  # must not raise
        assert any("failed" in r.message.lower() for r in caplog.records if r.levelno == logging.ERROR)

    @pytest.mark.slow
    def test_timeout_kills_process_and_continues(self, tmp_path: Path, caplog):
        """A hanging command must be killed and activation must continue."""
        cmd = 'python3 -c "import time; time.sleep(60)"'
        project = _make_project(
            tmp_path,
            activation_command=cmd,
            activation_command_timeout=1.0,  # 1s — fast for the test
            trusted=True,
        )
        agent = self._make_agent(project)
        with caplog.at_level(logging.ERROR):
            agent._run_project_activation_command(project)  # must not hang or raise
        assert any("timed out" in r.message.lower() for r in caplog.records if r.levelno == logging.ERROR)

    def test_command_does_not_inherit_caller_stdin(self, tmp_path: Path, caplog):
        """A command reading stdin must not block on the caller's (MCP) stdin pipe."""
        reader = tmp_path / "read_stdin.py"
        reader.write_text("import sys\nsys.stdin.readline()\n", encoding="utf-8")
        cmd = f'"{sys.executable}" {reader.name}'
        project = _make_project(tmp_path, activation_command=cmd, activation_command_timeout=2.0, trusted=True)
        agent = self._make_agent(project)

        # give the child an open, never-ending stdin pipe, as an MCP stdio harness does
        saved_stdin = os.dup(0)
        read_end, write_end = os.pipe()
        try:
            os.dup2(read_end, 0)
            os.close(read_end)
            with caplog.at_level(logging.ERROR):
                agent._run_project_activation_command(project)
        finally:
            os.dup2(saved_stdin, 0)
            os.close(saved_stdin)
            os.close(write_end)

        assert not any("timed out" in r.message.lower() for r in caplog.records)
