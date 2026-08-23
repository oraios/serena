from pathlib import Path

import pytest

from solidlsp.language_servers.erlang_language_server import (
    ELP_ASSET_PLATFORM_BY_ID,
    ELP_OTP_BUILD,
    ELP_SHA256_BY_ASSET,
    ErlangLanguageServer,
)
from solidlsp.ls_utils import PlatformId
from solidlsp.settings import SolidLSPSettings


@pytest.fixture
def provider(tmp_path: Path) -> ErlangLanguageServer.DependencyProvider:
    return ErlangLanguageServer.DependencyProvider(
        SolidLSPSettings.CustomLSSettings({}),
        str(tmp_path / "language-server-resources"),
    )


def test_path_elp_is_preferred_over_managed_download(
    monkeypatch: pytest.MonkeyPatch, provider: ErlangLanguageServer.DependencyProvider
) -> None:
    monkeypatch.setattr("solidlsp.language_servers.erlang_language_server.shutil.which", lambda name: "/usr/local/bin/elp")

    assert provider._get_or_install_core_dependency() == "/usr/local/bin/elp"


def test_launch_command_uses_elp_server(provider: ErlangLanguageServer.DependencyProvider) -> None:
    assert provider._create_launch_command("/tmp/elp") == ["/tmp/elp", "server"]


def test_ls_path_override_bypasses_download(tmp_path: Path) -> None:
    custom_provider = ErlangLanguageServer.DependencyProvider(
        SolidLSPSettings.CustomLSSettings({"ls_path": "/opt/elp"}),
        str(tmp_path / "language-server-resources"),
    )

    assert custom_provider.create_launch_command() == ["/opt/elp", "server"]


@pytest.mark.parametrize(
    ("platform_id", "asset_platform", "binary_name"),
    [
        (PlatformId.LINUX_x64, "linux-x86_64-unknown-linux-gnu", "elp"),
        (PlatformId.LINUX_arm64, "linux-aarch64-unknown-linux-gnu", "elp"),
        (PlatformId.OSX_x64, "macos-x86_64-apple-darwin", "elp"),
        (PlatformId.OSX_arm64, "macos-aarch64-apple-darwin", "elp"),
        (PlatformId.WIN_x64, "windows-x86_64-pc-windows-msvc", "elp.exe"),
    ],
)
def test_runtime_dependency_matches_official_release_assets(platform_id: PlatformId, asset_platform: str, binary_name: str) -> None:
    dependency = ErlangLanguageServer.DependencyProvider._runtime_dependency(platform_id)
    asset_name = f"elp-{asset_platform}-otp-{ELP_OTP_BUILD}.tar.gz"

    assert dependency.binary_name == binary_name
    assert dependency.url == f"https://github.com/WhatsApp/erlang-language-platform/releases/download/2026-08-10/{asset_name}"
    assert dependency.sha256 == ELP_SHA256_BY_ASSET[asset_name]
    assert ELP_ASSET_PLATFORM_BY_ID[platform_id] == asset_platform
    assert dependency.allowed_hosts == (
        "github.com",
        "release-assets.githubusercontent.com",
        "objects.githubusercontent.com",
    )
