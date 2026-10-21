import logging
from pathlib import Path
from typing import Any

import pytest

from solidlsp.language_servers import clangd_language_server
from solidlsp.language_servers.clangd_language_server import ClangdLanguageServer
from solidlsp.settings import SolidLSPSettings


def _launch_command(tmp_path: Path, settings: dict[str, Any]) -> list[str]:
    provider = ClangdLanguageServer.DependencyProvider(
        SolidLSPSettings.CustomLSSettings({"ls_path": "/opt/clangd", **settings}),
        str(tmp_path / "language-server-resources"),
    )
    return provider.create_launch_command()


def _option_args(command: list[str], option_name: str) -> list[str]:
    return [arg for arg in command if arg.lstrip("-").split("=", 1)[0] == option_name]


def test_launch_command_returns_all_references(tmp_path: Path) -> None:
    command = _launch_command(tmp_path, {})

    assert command[0] == "/opt/clangd"
    assert _option_args(command, "limit-references") == ["--limit-references=0"]


@pytest.mark.parametrize("user_arg", ["--limit-references=5", "-limit-references=5"])
def test_user_reference_limit_is_the_only_one(tmp_path: Path, user_arg: str) -> None:
    command = _launch_command(tmp_path, {"ls_extra_args": [user_arg]})

    assert _option_args(command, "limit-references") == [user_arg]


def test_launch_command_logs_errors_only(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=clangd_language_server.__name__)

    command = _launch_command(tmp_path, {})

    assert _option_args(command, "log") == ["--log=error"]


@pytest.mark.parametrize("user_args", [["--log=verbose"], ["-log=info"], ["--log", "info"]])
def test_user_log_level_is_the_only_one(tmp_path: Path, caplog: pytest.LogCaptureFixture, user_args: list[str]) -> None:
    caplog.set_level(logging.INFO, logger=clangd_language_server.__name__)

    command = _launch_command(tmp_path, {"ls_extra_args": user_args})

    assert _option_args(command, "log") == [user_args[0]]


def test_launch_command_keeps_clangd_log_when_serena_logs_at_debug_level(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=clangd_language_server.__name__)

    command = _launch_command(tmp_path, {})

    assert _option_args(command, "log") == []
