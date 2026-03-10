"""Tests for the Luau language server dependency provider."""

import io
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from solidlsp.language_servers.luau_lsp import LuauLanguageServer
from solidlsp.settings import SolidLSPSettings


def _make_provider(
    tmp_path: Path,
    custom_settings: dict[str, str] | None = None,
) -> LuauLanguageServer.DependencyProvider:
    return LuauLanguageServer.DependencyProvider(
        custom_settings=SolidLSPSettings.CustomLSSettings(custom_settings or {}),
        ls_resources_dir=str(tmp_path),
    )


class _FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return

    def iter_content(self, chunk_size: int = 8192):
        yield self.content

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


@pytest.mark.luau
class TestLuauDependencyProvider:
    def test_create_launch_command_uses_ls_path_override_and_adds_roblox_assets(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path, {"ls_path": "/custom/luau-lsp"})

        with patch.object(
            provider,
            "_get_or_install_core_dependency",
            side_effect=AssertionError("_get_or_install_core_dependency should not be called when ls_path is set"),
        ):
            with patch.object(
                provider,
                "_download_roblox_definitions",
                return_value=("/tmp/globalTypes.d.luau", "/tmp/en-us.json"),
            ):
                assert provider.create_launch_command() == [
                    "/custom/luau-lsp",
                    "lsp",
                    "--definitions:@roblox=/tmp/globalTypes.d.luau",
                    "--docs=/tmp/en-us.json",
                ]

    def test_get_or_install_core_dependency_uses_system_binary(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path)

        with patch("solidlsp.language_servers.luau_lsp.shutil.which", return_value="/usr/bin/luau-lsp"):
            with patch.object(
                provider,
                "_download_luau_lsp",
                side_effect=AssertionError("_download_luau_lsp should not be called when luau-lsp is on PATH"),
            ):
                assert provider._get_or_install_core_dependency() == "/usr/bin/luau-lsp"

    def test_download_luau_lsp_extracts_binary_into_ls_resources_dir(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path)

        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zip_file:
            zip_file.writestr("nested/luau-lsp", "#!/bin/sh\n")

        with patch("solidlsp.language_servers.luau_lsp.platform.system", return_value="Linux"):
            with patch("solidlsp.language_servers.luau_lsp.platform.machine", return_value="aarch64"):
                with patch("solidlsp.language_servers.luau_lsp.requests.get", return_value=_FakeResponse(archive.getvalue())):
                    binary_path = provider._download_luau_lsp()

        resolved_binary = Path(binary_path)
        assert resolved_binary.exists()
        assert resolved_binary.name == "luau-lsp"
        assert str(resolved_binary).startswith(str(tmp_path))

    def test_download_roblox_definitions_writes_into_ls_resources_dir(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path)

        with patch(
            "solidlsp.language_servers.luau_lsp.requests.get",
            side_effect=[_FakeResponse(b"types"), _FakeResponse(b"docs")],
        ):
            definitions_path, docs_path = provider._download_roblox_definitions()

        assert definitions_path == str(tmp_path / "globalTypes.d.luau")
        assert docs_path == str(tmp_path / "en-us.json")
        assert (tmp_path / "globalTypes.d.luau").read_bytes() == b"types"
        assert (tmp_path / "en-us.json").read_bytes() == b"docs"
