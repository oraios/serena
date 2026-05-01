"""Tests for ClangdLanguageServer.DependencyProvider launch command construction."""

from pathlib import Path
from unittest.mock import patch

import pytest

from solidlsp.language_servers.clangd_language_server import ClangdLanguageServer
from solidlsp.settings import SolidLSPSettings


def _make_provider(
    tmp_path: Path,
    custom_settings: dict | None = None,
) -> ClangdLanguageServer.DependencyProvider:
    return ClangdLanguageServer.DependencyProvider(
        custom_settings=SolidLSPSettings.CustomLSSettings(custom_settings or {}),
        ls_resources_dir=str(tmp_path),
    )


@pytest.mark.cpp
class TestClangdDependencyProvider:
    def test_default_args(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path)
        with patch.object(provider, "_get_or_install_core_dependency", return_value="/usr/bin/clangd"):
            cmd = provider.create_launch_command()
        assert cmd == ["/usr/bin/clangd", "--background-index"]

    def test_ls_extra_args_appended_to_defaults(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path, {"ls_extra_args": ["--query-driver=/usr/bin/gcc", "--log=verbose"]})
        with patch.object(provider, "_get_or_install_core_dependency", return_value="/usr/bin/clangd"):
            cmd = provider.create_launch_command()
        assert cmd == ["/usr/bin/clangd", "--background-index", "--query-driver=/usr/bin/gcc", "--log=verbose"]

    def test_ls_args_replaces_default_args(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path, {"ls_args": ["--log=verbose"]})
        with patch.object(provider, "_get_or_install_core_dependency", return_value="/usr/bin/clangd"):
            cmd = provider.create_launch_command()
        assert cmd == ["/usr/bin/clangd", "--log=verbose"]

    def test_ls_args_empty_list_removes_all_default_args(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path, {"ls_args": []})
        with patch.object(provider, "_get_or_install_core_dependency", return_value="/usr/bin/clangd"):
            cmd = provider.create_launch_command()
        assert cmd == ["/usr/bin/clangd"]

    def test_ls_path_overrides_executable(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path, {"ls_path": "/custom/clangd"})
        with patch.object(
            provider,
            "_get_or_install_core_dependency",
            side_effect=AssertionError("should not be called when ls_path is set"),
        ):
            cmd = provider.create_launch_command()
        assert cmd[0] == "/custom/clangd"
        assert "--background-index" in cmd

    def test_ls_path_with_ls_extra_args(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path, {"ls_path": "/custom/clangd", "ls_extra_args": ["--query-driver=/usr/bin/arm-gcc"]})
        with patch.object(provider, "_get_or_install_core_dependency", side_effect=AssertionError("should not be called")):
            cmd = provider.create_launch_command()
        assert cmd == ["/custom/clangd", "--background-index", "--query-driver=/usr/bin/arm-gcc"]

    def test_ls_path_with_ls_args(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path, {"ls_path": "/custom/clangd", "ls_args": ["--log=error"]})
        with patch.object(provider, "_get_or_install_core_dependency", side_effect=AssertionError("should not be called")):
            cmd = provider.create_launch_command()
        assert cmd == ["/custom/clangd", "--log=error"]
