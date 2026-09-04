"""Tests for Erlang Language Server dependency resolution and installation."""

from pathlib import Path
from unittest.mock import patch

import pytest

from solidlsp.language_servers.erlang_language_server import (
    ELP_ASSET_PLATFORM_BY_ID,
    ELP_EXECUTABLE_NAME_BY_PLATFORM_ID,
    ELP_OTP_BUILD,
    ELP_VERSION,
    ErlangLanguageServer,
)
from solidlsp.ls_utils import PlatformId
from solidlsp.settings import SolidLSPSettings

ELP_ALLOWED_HOSTS = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")

# SHA256 of the pinned release assets, kept in src/solidlsp/resources/downloaded_dependency_hashes.json
ELP_ASSET_SHA256_BY_PLATFORM_ID: dict[PlatformId, str] = {
    PlatformId.LINUX_x64: "c0e672a8381b5ea787e94a872847567b10d9b4d0053ca1148f4b236f61af3c63",
    PlatformId.LINUX_arm64: "0af71bd62e95998b7e57edd2083141b60edab51d0a2da988e6e71abb88cd3f34",
    PlatformId.OSX_x64: "d7c739a6b23ba7bfc0fc8481619ec55e41257d08cb7aa8b16499fb4c4f5e38e2",
    PlatformId.OSX_arm64: "7317a9934edc411e94392d5cc720f2e0c18112e7959060678aaef4d6dacdd9f2",
    PlatformId.WIN_x64: "6c4ed9ab76c9cbb2f6ae7b3a8dc06121a4ac6eda94d13bf7a638d3cb111b7f4e",
}


@pytest.fixture
def provider(tmp_path: Path) -> ErlangLanguageServer.DependencyProvider:
    return ErlangLanguageServer.DependencyProvider(
        SolidLSPSettings.CustomLSSettings({}),
        str(tmp_path / "language-server-resources"),
    )


def test_launch_command_uses_elp_server(provider: ErlangLanguageServer.DependencyProvider) -> None:
    assert provider._create_launch_command("/tmp/elp") == ["/tmp/elp", "server"]


def test_ls_path_override_bypasses_download(tmp_path: Path) -> None:
    custom_provider = ErlangLanguageServer.DependencyProvider(
        SolidLSPSettings.CustomLSSettings({"ls_path": "/opt/elp"}),
        str(tmp_path / "language-server-resources"),
    )

    assert custom_provider.create_launch_command() == ["/opt/elp", "server"]


@pytest.mark.parametrize(
    ("platform_id", "asset_platform", "executable_name"),
    [
        (PlatformId.LINUX_x64, "linux-x86_64-unknown-linux-gnu", "elp"),
        (PlatformId.LINUX_arm64, "linux-aarch64-unknown-linux-gnu", "elp"),
        (PlatformId.OSX_x64, "macos-x86_64-apple-darwin", "elp"),
        (PlatformId.OSX_arm64, "macos-aarch64-apple-darwin", "elp"),
        (PlatformId.WIN_x64, "windows-x86_64-pc-windows-msvc", "elp.exe"),
    ],
)
def test_managed_download_uses_pinned_verified_release_asset(
    tmp_path: Path, platform_id: PlatformId, asset_platform: str, executable_name: str
) -> None:
    dependency = ErlangLanguageServer.DependencyProvider._create_dep_elp(platform_id)
    asset_name = f"elp-{asset_platform}-otp-{ELP_OTP_BUILD}.tar.gz"
    url = f"https://github.com/WhatsApp/erlang-language-platform/releases/download/{ELP_VERSION}/{asset_name}"

    with patch("solidlsp.dependency_provider.FileUtils.download_and_extract_archive_verified") as download:
        dependency.download_to(tmp_path)

    download.assert_called_once_with(
        url,
        str(tmp_path),
        archive_type="gztar",
        expected_sha256=ELP_ASSET_SHA256_BY_PLATFORM_ID[platform_id],
        allowed_hosts=ELP_ALLOWED_HOSTS,
    )
    assert ELP_ASSET_PLATFORM_BY_ID[platform_id] == asset_platform
    assert ELP_EXECUTABLE_NAME_BY_PLATFORM_ID[platform_id] == executable_name
