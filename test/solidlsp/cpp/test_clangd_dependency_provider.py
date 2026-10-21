from pathlib import Path
from typing import Any

import pytest

from solidlsp.language_servers.clangd_language_server import ClangdLanguageServer
from solidlsp.settings import SolidLSPSettings


def _launch_command(tmp_path: Path, settings: dict[str, Any]) -> list[str]:
    provider = ClangdLanguageServer.DependencyProvider(
        SolidLSPSettings.CustomLSSettings({"ls_path": "/opt/clangd", **settings}),
        str(tmp_path / "language-server-resources"),
    )
    return provider.create_launch_command()


def _reference_limit_args(command: list[str]) -> list[str]:
    return [arg for arg in command if arg.lstrip("-").startswith("limit-references")]


def test_launch_command_returns_all_references(tmp_path: Path) -> None:
    command = _launch_command(tmp_path, {})

    assert command[0] == "/opt/clangd"
    assert _reference_limit_args(command) == ["--limit-references=0"]


@pytest.mark.parametrize("user_arg", ["--limit-references=5", "-limit-references=5"])
def test_user_reference_limit_is_the_only_one(tmp_path: Path, user_arg: str) -> None:
    command = _launch_command(tmp_path, {"ls_extra_args": [user_arg]})

    assert _reference_limit_args(command) == [user_arg]
