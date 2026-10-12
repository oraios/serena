from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from serena.cli import TopLevelCommands
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId


class _RecordingLanguageServer:
    """Stand-in for a language server, recording the installation request and optionally failing it."""

    def __init__(self, ls_id: LanguageServerId, installed: list[LanguageServerId]) -> None:
        self._ls_id = ls_id
        self._installed = installed

    def install_dependencies(self) -> None:
        if self._ls_id is LanguageServerId.GO:
            raise RuntimeError("Go is not installed")
        self._installed.append(self._ls_id)


@pytest.fixture
def installed_language_servers(monkeypatch) -> list[LanguageServerId]:
    installed: list[LanguageServerId] = []

    # make the command read deterministic settings without creating a user config file
    monkeypatch.setattr(
        "serena.cli.SerenaConfig.from_config_file",
        classmethod(lambda cls, generate_if_missing=True: SimpleNamespace(ls_specific_settings={})),
    )
    monkeypatch.setattr(
        SolidLanguageServer,
        "create",
        classmethod(lambda cls, config, *args, **kwargs: _RecordingLanguageServer(config.ls_id, installed)),
    )
    return installed


def test_download_ls_dependencies_downloads_named_language_servers(installed_language_servers) -> None:
    result = CliRunner().invoke(TopLevelCommands.download_ls_dependencies, ["python", "LUA"])

    assert result.exit_code == 0, result.output
    assert installed_language_servers == [LanguageServerId.PYTHON, LanguageServerId.LUA]
    assert "Successfully downloaded dependencies for 2 language server(s)." in result.output


def test_download_ls_dependencies_continues_after_failure_and_exits_one(installed_language_servers) -> None:
    result = CliRunner().invoke(TopLevelCommands.download_ls_dependencies, ["go", "python"])

    assert result.exit_code == 1
    assert installed_language_servers == [LanguageServerId.PYTHON]
    assert "go: Go is not installed" in result.output


def test_download_ls_dependencies_rejects_unknown_language_server(installed_language_servers) -> None:
    result = CliRunner().invoke(TopLevelCommands.download_ls_dependencies, ["pythonn"])

    assert result.exit_code == 2
    assert "Unknown language server 'pythonn'" in result.output
    assert installed_language_servers == []
