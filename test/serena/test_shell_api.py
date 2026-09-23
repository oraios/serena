"""
Tests for the shell facade API.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from serena.config.serena_config import SerenaConfig
from serena.project import Project
from serena.repl.api.shell_api import ShellApi
from serena.repl.facade import ApiScope, Facade


@pytest.fixture
def api(tmp_path: Path) -> ShellApi:
    (tmp_path / "sub").mkdir()
    project = Project.load(str(tmp_path), serena_config=SerenaConfig(gui_log_window=False, web_dashboard=False))
    agent = MagicMock()
    agent.get_active_project_or_raise.return_value = project
    agent.serena_config.default_max_tool_answer_chars = 10000
    return ShellApi(agent)


def test_facade_exposes_shell_command_as_editing_operation(api: ShellApi) -> None:
    facade = Facade.from_api(api, ApiScope())
    assert facade.name == "shell"
    assert facade.enabled_method_names == ["execute_shell_command"]
    assert facade.get_method("execute_shell_command").info.can_edit


def test_execute_shell_command(api: ShellApi, tmp_path: Path) -> None:
    print_cwd = "cd" if sys.platform == "win32" else "pwd"

    output = api.execute_shell_command(f"{print_cwd}")
    assert output.return_code == 0
    assert Path(output.stdout.strip()).resolve() == tmp_path.resolve()
    assert '"stdout"' in output.represent() and '"return_code"' in output.represent()

    # a relative working directory is resolved against the project root and must exist
    assert Path(api.execute_shell_command(print_cwd, cwd="sub").stdout.strip()).resolve() == (tmp_path / "sub").resolve()
    with pytest.raises(FileNotFoundError):
        api.execute_shell_command(print_cwd, cwd="missing")
