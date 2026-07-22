from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from solidlsp.dependency_provider import LanguageServerDependencyProviderUvx
from solidlsp.language_servers.basedpyright_server import BASEDPYRIGHT_VERSION, BasedPyrightLanguageServer
from solidlsp.language_servers.pyright_server import PyrightServer
from solidlsp.ls_config import LanguageServerConfig, LanguageServerId
from solidlsp.settings import SolidLSPSettings


def _make_basedpyright_server(
    tmp_path: Path,
    custom_settings: dict[str, object] | None = None,
) -> BasedPyrightLanguageServer:
    settings = SolidLSPSettings(
        solidlsp_dir=str(tmp_path / "global"),
        project_data_path=str(tmp_path / "project"),
        ls_specific_settings={LanguageServerId.PYTHON_BASEDPYRIGHT: custom_settings or {}},
    )
    server_interface = Mock()
    with patch.object(BasedPyrightLanguageServer, "_create_language_server_interface", return_value=server_interface):
        return BasedPyrightLanguageServer(
            LanguageServerConfig(ls_id=LanguageServerId.PYTHON_BASEDPYRIGHT),
            str(tmp_path),
            settings,
        )


def _make_pyright_server(tmp_path: Path) -> PyrightServer:
    settings = SolidLSPSettings(
        solidlsp_dir=str(tmp_path / "global"),
        project_data_path=str(tmp_path / "project"),
    )
    server_interface = Mock()
    with patch.object(PyrightServer, "_create_language_server_interface", return_value=server_interface):
        return PyrightServer(LanguageServerConfig(ls_id=LanguageServerId.PYTHON), str(tmp_path), settings)


def test_dependency_provider_uses_basedpyright_profile(tmp_path: Path) -> None:
    server = _make_basedpyright_server(tmp_path)
    provider = server._create_dependency_provider()

    assert isinstance(provider, LanguageServerDependencyProviderUvx)
    assert provider._package == "basedpyright"
    assert provider._entrypoint == "basedpyright-langserver"
    assert provider._default_version == BASEDPYRIGHT_VERSION
    assert provider._version_setting_key == "basedpyright_version"


def test_version_override_builds_uvx_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custom_version = "1.99.0"
    server = _make_basedpyright_server(tmp_path, {"basedpyright_version": custom_version})
    provider = server._create_dependency_provider()
    monkeypatch.delenv("UVX", raising=False)

    with patch("solidlsp.dependency_provider.shutil.which", return_value="/opt/bin/uvx"):
        command = provider.create_launch_command()

    assert command == [
        "/opt/bin/uvx",
        "-p",
        "3.13",
        "--from",
        f"basedpyright=={custom_version}",
        "basedpyright-langserver",
        "--stdio",
    ]


def test_builds_uv_tool_run_fallback_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server = _make_basedpyright_server(tmp_path)
    provider = server._create_dependency_provider()
    monkeypatch.delenv("UVX", raising=False)

    def find_uv(executable: str) -> str | None:
        return None if executable == "uvx" else "/opt/bin/uv"

    with patch("solidlsp.dependency_provider.shutil.which", side_effect=find_uv):
        command = provider.create_launch_command()

    assert command == [
        "/opt/bin/uv",
        "tool",
        "run",
        "-p",
        "3.13",
        "--from",
        f"basedpyright=={BASEDPYRIGHT_VERSION}",
        "basedpyright-langserver",
        "--stdio",
    ]


def test_ls_path_preserves_default_and_extra_arguments(tmp_path: Path) -> None:
    server = _make_basedpyright_server(
        tmp_path,
        {
            "ls_path": "/custom/basedpyright-langserver",
            "ls_extra_args": ["--verbose"],
        },
    )

    assert server._create_dependency_provider().create_launch_command() == [
        "/custom/basedpyright-langserver",
        "--stdio",
        "--verbose",
    ]


def test_base_command_and_args_overrides_are_preserved(tmp_path: Path) -> None:
    server = _make_basedpyright_server(
        tmp_path,
        {
            "ls_base_cmd": ["custom-launcher", "basedpyright-langserver"],
            "ls_args": ["--custom-stdio"],
            "ls_extra_args": ["--verbose"],
        },
    )

    assert server._create_dependency_provider().create_launch_command() == [
        "custom-launcher",
        "basedpyright-langserver",
        "--custom-stdio",
        "--verbose",
    ]


def test_language_registry_uses_separate_server_classes() -> None:
    assert LanguageServerId.PYTHON.get_ls_class() is PyrightServer
    assert LanguageServerId.PYTHON_BASEDPYRIGHT.get_ls_class() is BasedPyrightLanguageServer


def test_language_identity_separates_cache_directories(tmp_path: Path) -> None:
    pyright_server = _make_pyright_server(tmp_path)
    basedpyright_server = _make_basedpyright_server(tmp_path)

    assert pyright_server.ls_id == LanguageServerId.PYTHON
    assert basedpyright_server.ls_id == LanguageServerId.PYTHON_BASEDPYRIGHT
    assert pyright_server.cache_dir != basedpyright_server.cache_dir
