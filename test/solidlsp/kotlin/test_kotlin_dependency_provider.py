"""Tests for Kotlin Language Server dependency resolution and installation."""

from pathlib import Path
from unittest.mock import patch

import pytest

from solidlsp.language_servers.kotlin_language_server import (
    DEFAULT_KOTLIN_LSP_VERSION,
    INITIAL_KOTLIN_LSP_VERSION,
    KOTLIN_LSP_ALLOWED_HOSTS,
    KotlinLanguageServer,
    _resolve_kotlin_lsp_artifact,
    _uses_kotlin_server_packaging,
)
from solidlsp.ls_utils import PlatformId
from solidlsp.settings import SolidLSPSettings


def _make_provider(
    tmp_path: Path,
    custom_settings: dict[str, str] | None = None,
) -> KotlinLanguageServer.DependencyProvider:
    return KotlinLanguageServer.DependencyProvider(
        custom_settings=SolidLSPSettings.CustomLSSettings(custom_settings or {}),
        ls_resources_dir=str(tmp_path),
        project_cache_dir=str(tmp_path / "project-cache"),
    )


@pytest.mark.kotlin
class TestKotlinDependencyProvider:
    @pytest.mark.parametrize(
        ("platform_id", "asset_suffix", "archive_type", "launcher_parts", "sha256"),
        [
            (
                PlatformId.WIN_x64,
                ".win.zip",
                "zip",
                ("bin", "intellij-server.exe"),
                "f2daaa476f26d99301b406f76de6d87c437d04dc72f06845154619d8f991c51f",
            ),
            (
                PlatformId.WIN_arm64,
                "-aarch64.win.zip",
                "zip",
                ("bin", "intellij-server.exe"),
                "73a552a6a420158622e5ad8d96b53da8aa8ced3f88a24fded01575927a2fd8e7",
            ),
            (
                PlatformId.LINUX_x64,
                ".tar.gz",
                "gztar",
                (f"kotlin-server-{DEFAULT_KOTLIN_LSP_VERSION}", "bin", "intellij-server"),
                "2d99d8e198fbe4aa8f4481e37799724ce94803b4ea12a60b416040e3fcd7cc5e",
            ),
            (
                PlatformId.LINUX_arm64,
                "-aarch64.tar.gz",
                "gztar",
                (f"kotlin-server-{DEFAULT_KOTLIN_LSP_VERSION}", "bin", "intellij-server"),
                "2317831c6e5607d05b7ebc1da655330125ce0e3d66fbf24517dfce442debc14e",
            ),
            (
                PlatformId.OSX_x64,
                ".sit",
                "zip",
                (f"kotlin-server-{DEFAULT_KOTLIN_LSP_VERSION}", "bin", "intellij-server"),
                "17369fda97c85418ac24ab38a9df56b21522a3468dfe193832fe455c13920745",
            ),
            (
                PlatformId.OSX_arm64,
                "-aarch64.sit",
                "zip",
                (f"kotlin-server-{DEFAULT_KOTLIN_LSP_VERSION}", "bin", "intellij-server"),
                "6ba6021a706b21e64cef33f7e2b79f187c0910320722bb2d3ed05ad1115ec43f",
            ),
        ],
    )
    def test_default_artifacts_match_jetbrains_release_matrix(
        self,
        platform_id: PlatformId,
        asset_suffix: str,
        archive_type: str,
        launcher_parts: tuple[str, ...],
        sha256: str,
    ) -> None:
        artifact = _resolve_kotlin_lsp_artifact(DEFAULT_KOTLIN_LSP_VERSION, platform_id)

        asset_name = f"kotlin-server-{DEFAULT_KOTLIN_LSP_VERSION}{asset_suffix}"
        assert artifact.url == (
            f"https://download-cdn.jetbrains.com/language-server/kotlin-server/{DEFAULT_KOTLIN_LSP_VERSION}/{asset_name}"
        )
        assert artifact.archive_type == archive_type
        assert artifact.launcher_parts == launcher_parts
        assert artifact.sha256 == sha256

    def test_packaging_boundary_keeps_older_custom_versions_compatible(self) -> None:
        legacy_version = "262.2310.0"
        first_modern_version = "262.4739.0"

        assert not _uses_kotlin_server_packaging(legacy_version)
        assert _uses_kotlin_server_packaging(first_modern_version)

        legacy_artifact = _resolve_kotlin_lsp_artifact(legacy_version, PlatformId.LINUX_x64)
        assert legacy_artifact.url == (
            f"https://download-cdn.jetbrains.com/kotlin-lsp/{legacy_version}/kotlin-lsp-{legacy_version}-linux-x64.zip"
        )
        assert legacy_artifact.archive_type == "zip"
        assert legacy_artifact.launcher_parts == ("kotlin-lsp.sh",)
        assert legacy_artifact.sha256 is None

        modern_artifact = _resolve_kotlin_lsp_artifact(first_modern_version, PlatformId.LINUX_x64)
        assert modern_artifact.url == (
            f"https://download-cdn.jetbrains.com/kotlin-lsp/{first_modern_version}/kotlin-server-{first_modern_version}.tar.gz"
        )
        assert modern_artifact.archive_type == "gztar"
        assert modern_artifact.launcher_parts == (f"kotlin-server-{first_modern_version}", "bin", "intellij-server")
        assert modern_artifact.sha256 is None

    @pytest.mark.parametrize(
        ("version", "cdn_path"),
        [
            ("262.7569.0", "kotlin-lsp"),
            ("262.8190.0", "language-server/kotlin-server"),
        ],
    )
    def test_cdn_path_boundary_keeps_custom_modern_versions_downloadable(self, version: str, cdn_path: str) -> None:
        artifact = _resolve_kotlin_lsp_artifact(version, PlatformId.OSX_arm64)

        assert artifact.url == (f"https://download-cdn.jetbrains.com/{cdn_path}/{version}/kotlin-server-{version}-aarch64.sit")
        assert artifact.archive_type == "zip"
        assert artifact.launcher_parts == (f"kotlin-server-{version}", "bin", "intellij-server")
        assert artifact.sha256 is None

    def test_initial_version_keeps_unversioned_legacy_install(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path, {"kotlin_lsp_version": INITIAL_KOTLIN_LSP_VERSION})

        def fake_download(
            _url: str,
            target_path: str,
            _archive_type: str,
            expected_sha256: str | None = None,
            allowed_hosts: tuple[str, ...] | list[str] | None = None,
        ) -> None:
            del expected_sha256, allowed_hosts
            launcher = Path(target_path) / "kotlin-lsp.sh"
            launcher.write_text("#!/bin/sh\n", encoding="utf-8")

        with (
            patch(
                "solidlsp.language_servers.kotlin_language_server.PlatformUtils.get_platform_id",
                return_value=PlatformId.LINUX_x64,
            ),
            patch(
                "solidlsp.language_servers.kotlin_language_server.FileUtils.download_and_extract_archive_verified",
                side_effect=fake_download,
            ) as download,
        ):
            launcher_path = provider._get_or_install_core_dependency()

        assert launcher_path == str(tmp_path / "kotlin_language_server" / "kotlin-lsp.sh")
        download.assert_called_once_with(
            f"https://download-cdn.jetbrains.com/kotlin-lsp/{INITIAL_KOTLIN_LSP_VERSION}/"
            f"kotlin-lsp-{INITIAL_KOTLIN_LSP_VERSION}-linux-x64.zip",
            str(tmp_path / "kotlin_language_server"),
            "zip",
            expected_sha256="dc0ed2e70cb0d61fdabb26aefce8299b7a75c0dcfffb9413715e92caec6e83ec",
            allowed_hosts=KOTLIN_LSP_ALLOWED_HOSTS,
        )

    def test_default_version_uses_versioned_modern_install(self, tmp_path: Path) -> None:
        provider = _make_provider(tmp_path)
        artifact = _resolve_kotlin_lsp_artifact(DEFAULT_KOTLIN_LSP_VERSION, PlatformId.LINUX_arm64)

        def fake_download(
            _url: str,
            target_path: str,
            _archive_type: str,
            expected_sha256: str | None = None,
            allowed_hosts: tuple[str, ...] | list[str] | None = None,
        ) -> None:
            del expected_sha256, allowed_hosts
            launcher = Path(target_path).joinpath(*artifact.launcher_parts)
            launcher.parent.mkdir(parents=True, exist_ok=True)
            launcher.write_text("#!/bin/sh\n", encoding="utf-8")

        with (
            patch(
                "solidlsp.language_servers.kotlin_language_server.PlatformUtils.get_platform_id",
                return_value=PlatformId.LINUX_arm64,
            ),
            patch(
                "solidlsp.language_servers.kotlin_language_server.FileUtils.download_and_extract_archive_verified",
                side_effect=fake_download,
            ) as download,
        ):
            launcher_path = provider._get_or_install_core_dependency()

        static_dir = tmp_path / f"kotlin_language_server-{DEFAULT_KOTLIN_LSP_VERSION}"
        assert launcher_path == str(static_dir.joinpath(*artifact.launcher_parts))
        download.assert_called_once_with(
            artifact.url,
            str(static_dir),
            artifact.archive_type,
            expected_sha256=artifact.sha256,
            allowed_hosts=KOTLIN_LSP_ALLOWED_HOSTS,
        )

    def test_launch_command_uses_persistent_system_path_only_for_modern_server(self, tmp_path: Path) -> None:
        modern_provider = _make_provider(tmp_path)
        legacy_provider = _make_provider(tmp_path, {"kotlin_lsp_version": INITIAL_KOTLIN_LSP_VERSION})

        assert modern_provider._create_launch_command("/path/to/intellij-server") == [
            "/path/to/intellij-server",
            "--stdio",
            "--system-path",
            str(tmp_path / "project-cache" / "kotlin-lsp-system"),
        ]
        assert legacy_provider._create_launch_command("/path/to/kotlin-lsp.sh") == [
            "/path/to/kotlin-lsp.sh",
            "--stdio",
        ]

    def test_invalid_version_is_rejected_before_download(self) -> None:
        with pytest.raises(ValueError, match="dot-separated integers"):
            _resolve_kotlin_lsp_artifact("latest", PlatformId.OSX_arm64)

    def test_unsupported_modern_platform_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported platform"):
            _resolve_kotlin_lsp_artifact(DEFAULT_KOTLIN_LSP_VERSION, PlatformId.LINUX_x86)
