from types import SimpleNamespace

from click.testing import CliRunner

from serena.cli import TopLevelCommands
from solidlsp.ls_config import LanguageServerId


def _patch_config(monkeypatch, ls_specific_settings: dict | None = None) -> None:
    """Make the command read deterministic settings without creating a user config file."""
    monkeypatch.setattr(
        "serena.cli.SerenaConfig.from_config_file",
        classmethod(lambda cls, generate_if_missing=True: SimpleNamespace(ls_specific_settings=ls_specific_settings or {})),
    )


def test_download_ls_dependencies_downloads_named_language_servers(monkeypatch) -> None:
    downloaded: list[LanguageServerId] = []
    _patch_config(monkeypatch)
    monkeypatch.setattr("serena.cli._download_ls_dependencies", lambda ls_id, settings, root: downloaded.append(ls_id))

    result = CliRunner().invoke(TopLevelCommands.download_ls_dependencies, ["python", "LUA"])

    assert result.exit_code == 0, result.output
    assert downloaded == [LanguageServerId.PYTHON, LanguageServerId.LUA]
    assert "Successfully downloaded dependencies for 2 language server(s)." in result.output


def test_download_ls_dependencies_all_excludes_experimental_by_default(monkeypatch) -> None:
    downloaded: list[LanguageServerId] = []
    _patch_config(monkeypatch)
    monkeypatch.setattr("serena.cli._download_ls_dependencies", lambda ls_id, settings, root: downloaded.append(ls_id))

    result = CliRunner().invoke(TopLevelCommands.download_ls_dependencies, ["--all"])

    assert result.exit_code == 0, result.output
    assert downloaded == list(LanguageServerId.iter_all(include_experimental=False))
    assert not any(ls_id.is_experimental() for ls_id in downloaded)


def test_download_ls_dependencies_all_can_include_experimental(monkeypatch) -> None:
    downloaded: list[LanguageServerId] = []
    _patch_config(monkeypatch)
    monkeypatch.setattr("serena.cli._download_ls_dependencies", lambda ls_id, settings, root: downloaded.append(ls_id))

    result = CliRunner().invoke(TopLevelCommands.download_ls_dependencies, ["--all", "--include-experimental"])

    assert result.exit_code == 0, result.output
    assert downloaded == list(LanguageServerId.iter_all(include_experimental=True))
    assert any(ls_id.is_experimental() for ls_id in downloaded)


def test_download_ls_dependencies_continues_after_failure_and_exits_one(monkeypatch) -> None:
    downloaded: list[LanguageServerId] = []
    _patch_config(monkeypatch)

    def fake_download(ls_id: LanguageServerId, settings: dict, root: str) -> None:
        if ls_id is LanguageServerId.GO:
            raise RuntimeError("Go is not installed")
        downloaded.append(ls_id)

    monkeypatch.setattr("serena.cli._download_ls_dependencies", fake_download)
    result = CliRunner().invoke(TopLevelCommands.download_ls_dependencies, ["go", "python"])

    assert result.exit_code == 1
    assert downloaded == [LanguageServerId.PYTHON]
    assert "go: Go is not installed" in result.output


def test_download_ls_dependencies_rejects_unknown_language_server() -> None:
    result = CliRunner().invoke(TopLevelCommands.download_ls_dependencies, ["pythonn"])

    assert result.exit_code == 2
    assert "Unknown language server 'pythonn'" in result.output


def test_download_ls_dependencies_requires_language_server_or_all() -> None:
    result = CliRunner().invoke(TopLevelCommands.download_ls_dependencies, [])

    assert result.exit_code == 2
    assert "Pass at least one language server name or use `--all`." in result.output


def test_download_ls_dependencies_rejects_all_with_explicit_language_server() -> None:
    result = CliRunner().invoke(TopLevelCommands.download_ls_dependencies, ["--all", "python"])

    assert result.exit_code == 2
    assert "Cannot combine explicitly named language servers with `--all`." in result.output


def test_download_ls_dependencies_rejects_include_experimental_without_all() -> None:
    result = CliRunner().invoke(TopLevelCommands.download_ls_dependencies, ["--include-experimental", "python"])

    assert result.exit_code == 2
    assert "`--include-experimental` is applicable only in conjunction with `--all`." in result.output
