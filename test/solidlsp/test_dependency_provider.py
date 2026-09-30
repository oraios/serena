import subprocess
from unittest.mock import Mock

import pytest

from solidlsp.dependency_provider import LanguageServerDependencyProviderUvx
from solidlsp.ls import SolidLanguageServer
from solidlsp.settings import SolidLSPSettings


def _create_provider(settings: dict) -> LanguageServerDependencyProviderUvx:
    return LanguageServerDependencyProviderUvx(
        SolidLSPSettings.CustomLSSettings(settings),
        ls_resources_dir=".",
        package="somepackage",
        entrypoint="some-langserver",
        default_version="1.2.3",
        version_setting_key="somepackage_version",
    )


@pytest.fixture
def installation_commands(monkeypatch) -> list[list[str]]:
    commands: list[list[str]] = []

    def fake_subprocess_run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
        commands.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("solidlsp.dependency_provider.subprocess_run", fake_subprocess_run)
    monkeypatch.setattr(LanguageServerDependencyProviderUvx, "_find_uv_executable", staticmethod(lambda: "uv"))
    return commands


def test_install_dependencies_installs_pinned_version(installation_commands) -> None:
    _create_provider({}).install_dependencies()

    assert installation_commands == [["uv", "tool", "install", "-p", "3.13", "somepackage==1.2.3"]]


def test_install_dependencies_respects_configured_version(installation_commands) -> None:
    _create_provider({"somepackage_version": "4.5.6"}).install_dependencies()

    assert installation_commands == [["uv", "tool", "install", "-p", "3.13", "somepackage==4.5.6"]]


@pytest.mark.parametrize("settings", [{"ls_path": "/opt/some-langserver"}, {"ls_base_cmd": ["/opt/some-langserver"]}])
def test_install_dependencies_skips_custom_launch_commands(installation_commands, settings) -> None:
    _create_provider(settings).install_dependencies()

    assert installation_commands == []


def test_install_dependencies_uses_managed_install_for_malformed_base_command(installation_commands) -> None:
    provider = _create_provider({"ls_base_cmd": "/opt/some-langserver"})

    provider.install_dependencies()

    assert installation_commands == [["uv", "tool", "install", "-p", "3.13", "somepackage==1.2.3"]]
    assert provider._get_custom_base_command() is None


def test_language_server_prefetch_creates_lazy_provider() -> None:
    server = Mock()
    server._process_launch_info = None
    provider = server._get_dependency_provider.return_value

    SolidLanguageServer.install_dependencies(server)

    server._get_dependency_provider.assert_called_once_with()
    provider.install_dependencies.assert_called_once_with()


def test_language_server_prefetch_skips_legacy_fixed_command() -> None:
    server = Mock()
    server._process_launch_info = object()

    SolidLanguageServer.install_dependencies(server)

    server._get_dependency_provider.assert_not_called()


def test_install_dependencies_raises_on_failure(monkeypatch) -> None:
    def failing_subprocess_run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="network unreachable")

    monkeypatch.setattr("solidlsp.dependency_provider.subprocess_run", failing_subprocess_run)
    monkeypatch.setattr(LanguageServerDependencyProviderUvx, "_find_uv_executable", staticmethod(lambda: "uv"))

    with pytest.raises(RuntimeError, match="network unreachable"):
        _create_provider({}).install_dependencies()
