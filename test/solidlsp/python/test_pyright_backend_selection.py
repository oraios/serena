from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from solidlsp.dependency_provider import LanguageServerDependencyProviderUvx
from solidlsp.language_servers.pyright_server import BASEDPYRIGHT_VERSION, PYRIGHT_VERSION, PyrightServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.settings import SolidLSPSettings


def _make_server(tmp_path: Path, custom_settings: dict[str, object] | None = None) -> PyrightServer:
    settings = SolidLSPSettings(
        solidlsp_dir=str(tmp_path / "global"),
        project_data_path=str(tmp_path / "project"),
        ls_specific_settings={Language.PYTHON: custom_settings or {}},
    )
    server_interface = Mock()
    with patch.object(PyrightServer, "_create_language_server_interface", return_value=server_interface):
        return PyrightServer(LanguageServerConfig(code_language=Language.PYTHON), str(tmp_path), settings)


@pytest.mark.parametrize(
    ("custom_settings", "backend_name", "display_name", "package", "entrypoint", "version", "version_key"),
    [
        ({}, "pyright", "Pyright", "pyright", "pyright-langserver", PYRIGHT_VERSION, "pyright_version"),
        (
            {"language_server": "basedpyright"},
            "basedpyright",
            "BasedPyright",
            "basedpyright",
            "basedpyright-langserver",
            BASEDPYRIGHT_VERSION,
            "basedpyright_version",
        ),
    ],
)
def test_backend_selection_uses_expected_profile(
    tmp_path: Path,
    custom_settings: dict[str, object],
    backend_name: str,
    display_name: str,
    package: str,
    entrypoint: str,
    version: str,
    version_key: str,
) -> None:
    server = _make_server(tmp_path, custom_settings)
    provider = server._create_dependency_provider()

    assert isinstance(provider, LanguageServerDependencyProviderUvx)
    assert server._backend.name == backend_name
    assert server._backend.display_name == display_name
    assert provider._package == package
    assert provider._entrypoint == entrypoint
    assert provider._default_version == version
    assert provider._version_setting_key == version_key


@pytest.mark.parametrize(
    ("language_server", "version_key", "custom_version", "package", "entrypoint"),
    [
        ("pyright", "pyright_version", "1.1.999", "pyright", "pyright-langserver"),
        ("basedpyright", "basedpyright_version", "1.99.0", "basedpyright", "basedpyright-langserver"),
    ],
)
def test_version_override_builds_uvx_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    language_server: str,
    version_key: str,
    custom_version: str,
    package: str,
    entrypoint: str,
) -> None:
    server = _make_server(tmp_path, {"language_server": language_server, version_key: custom_version})
    provider = server._create_dependency_provider()
    monkeypatch.delenv("UVX", raising=False)

    with patch("solidlsp.dependency_provider.shutil.which", return_value="/opt/bin/uvx"):
        command = provider.create_launch_command()

    assert command == [
        "/opt/bin/uvx",
        "-p",
        "3.13",
        "--from",
        f"{package}=={custom_version}",
        entrypoint,
        "--stdio",
    ]


def test_basedpyright_builds_uv_x_fallback_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server = _make_server(tmp_path, {"language_server": "basedpyright"})
    provider = server._create_dependency_provider()
    monkeypatch.delenv("UVX", raising=False)

    with patch("solidlsp.dependency_provider.shutil.which", side_effect=lambda executable: None if executable == "uvx" else "/opt/bin/uv"):
        command = provider.create_launch_command()

    assert command == [
        "/opt/bin/uv",
        "x",
        "-p",
        "3.13",
        "--from",
        f"basedpyright=={BASEDPYRIGHT_VERSION}",
        "basedpyright-langserver",
        "--stdio",
    ]


def test_ls_path_targets_selected_server_and_preserves_arguments(tmp_path: Path) -> None:
    server = _make_server(
        tmp_path,
        {
            "language_server": "basedpyright",
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
    server = _make_server(
        tmp_path,
        {
            "language_server": "basedpyright",
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


@pytest.mark.parametrize("language_server", ["pylance", "", None, 42, ["basedpyright"]])
def test_invalid_backend_fails_before_server_launch(tmp_path: Path, language_server: object) -> None:
    with pytest.raises(ValueError) as exc_info:
        _make_server(tmp_path, {"language_server": language_server})

    message = str(exc_info.value)
    assert "ls_specific_settings.python.language_server" in message
    assert "'pyright'" in message
    assert "'basedpyright'" in message


def test_backend_identity_separates_raw_symbol_caches(tmp_path: Path) -> None:
    pyright_server = _make_server(tmp_path / "pyright")
    basedpyright_server = _make_server(tmp_path / "basedpyright", {"language_server": "basedpyright"})

    assert pyright_server._ls_specific_raw_document_symbols_cache_version == ("pyright-backend", "pyright")
    assert basedpyright_server._ls_specific_raw_document_symbols_cache_version == ("pyright-backend", "basedpyright")
    assert (
        pyright_server._ls_specific_raw_document_symbols_cache_version
        != basedpyright_server._ls_specific_raw_document_symbols_cache_version
    )
