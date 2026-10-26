"""Tests for Kotlin Language Server dependency resolution and installation."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from solidlsp.language_servers.kotlin_language_server import (
    DEFAULT_KOTLIN_LSP_VERSION,
    INITIAL_KOTLIN_LSP_VERSION,
    KOTLIN_LSP_ALLOWED_HOSTS,
    KotlinLanguageServer,
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
    def test_custom_versions_skip_hash_lookup_by_design(self, tmp_path: Path) -> None:
        artifact = KotlinLanguageServer.DependencyProvider._create_artifact("262.8190.1", PlatformId.LINUX_x64)

        with (
            patch(
                "solidlsp.dependency_provider.DownloadedDependencyHashDatabase.get_instance",
                side_effect=AssertionError("custom versions must not consult the pinned hash database"),
            ),
            patch("solidlsp.dependency_provider.FileUtils.download_and_extract_archive_verified") as download,
        ):
            artifact.dependency.download_to(tmp_path)

        download.assert_called_once_with(
            "https://download.jetbrains.com/language-server/kotlin-server/262.8190.1/kotlin-server-262.8190.1.tar.gz",
            str(tmp_path),
            archive_type="gztar",
            expected_sha256=None,
            allowed_hosts=KOTLIN_LSP_ALLOWED_HOSTS,
        )

    @pytest.mark.parametrize(
        ("settings", "platform_id", "relative_launcher", "expected_directory"),
        [
            (
                {"kotlin_lsp_version": INITIAL_KOTLIN_LSP_VERSION},
                PlatformId.LINUX_x64,
                ("kotlin-lsp.sh",),
                "kotlin_language_server",
            ),
        ],
    )
    def test_installs_pinned_versions_in_compatible_directories(
        self,
        tmp_path: Path,
        settings: dict[str, str],
        platform_id: PlatformId,
        relative_launcher: tuple[str, ...],
        expected_directory: str,
    ) -> None:
        provider = _make_provider(tmp_path, settings)

        def fake_download(
            _url: str,
            target_path: str,
            archive_type: str,
            expected_sha256: str | None = None,
            allowed_hosts: tuple[str, ...] | list[str] | None = None,
        ) -> None:
            del archive_type, expected_sha256, allowed_hosts
            launcher = Path(target_path).joinpath(*relative_launcher)
            launcher.parent.mkdir(parents=True, exist_ok=True)
            launcher.write_text("#!/bin/sh\n", encoding="utf-8")

        with (
            patch(
                "solidlsp.language_servers.kotlin_language_server.PlatformUtils.get_platform_id",
                return_value=platform_id,
            ),
            patch(
                "solidlsp.dependency_provider.FileUtils.download_and_extract_archive_verified",
                side_effect=fake_download,
            ),
        ):
            launcher_path = provider._get_or_install_core_dependency()

        assert launcher_path == str((tmp_path / expected_directory).joinpath(*relative_launcher))

    @pytest.mark.parametrize(
        ("platform_id", "modern_launcher", "other_os_launcher"),
        [
            (PlatformId.LINUX_x64, "/path/to/intellij-server", "/path/to/intellij-server.exe"),
            (PlatformId.WIN_x64, "/path/to/intellij-server.exe", "/path/to/intellij-server"),
        ],
    )
    def test_custom_launcher_arguments_use_the_active_os_name(
        self,
        tmp_path: Path,
        platform_id: PlatformId,
        modern_launcher: str,
        other_os_launcher: str,
    ) -> None:
        modern_provider = _make_provider(tmp_path, {"ls_path": modern_launcher})
        other_os_provider = _make_provider(tmp_path, {"ls_path": other_os_launcher})

        with patch(
            "solidlsp.language_servers.kotlin_language_server.PlatformUtils.get_platform_id",
            return_value=platform_id,
        ):
            assert modern_provider.create_launch_command() == [
                modern_launcher,
                "--stdio",
                "--system-path",
                str(tmp_path / "project-cache" / "kotlin-lsp-system"),
            ]
            assert other_os_provider.create_launch_command() == [other_os_launcher, "--stdio"]

    def test_single_instance_keeps_the_deterministic_cache_dir(self, tmp_path: Path) -> None:
        """The common case (one Serena instance, possibly restarted) must keep reusing the
        same on-disk directory, or the Kotlin LSP loses its index cache on every restart.
        """
        provider = _make_provider(tmp_path)

        assert provider.storage_dir == str(tmp_path / "project-cache")

    def test_second_concurrent_instance_gets_its_own_storage_dir(self, tmp_path: Path) -> None:
        """Two Serena instances activating the same project concurrently (oraios/serena#1966)
        must not be handed the same Kotlin LSP storage directory: the second one falls back to
        a directory of its own instead of contending with the first for the same index.
        """
        first = _make_provider(tmp_path)
        second = _make_provider(tmp_path)
        try:
            assert first.storage_dir == str(tmp_path / "project-cache")
            assert second.storage_dir != first.storage_dir
            assert second.storage_dir.startswith(str(tmp_path / "project-cache") + "-instance-")
        finally:
            first.release_storage_lock()
            second.release_storage_lock()

    def test_storage_dir_is_reclaimed_once_the_first_instance_releases_it(self, tmp_path: Path) -> None:
        first = _make_provider(tmp_path)
        first.release_storage_lock()

        second = _make_provider(tmp_path)
        try:
            assert second.storage_dir == str(tmp_path / "project-cache")
        finally:
            second.release_storage_lock()

    def test_fallback_storage_dir_is_removed_on_release(self, tmp_path: Path) -> None:
        """The second instance's fallback directory (oraios/serena#1966) must not survive its
        own release, or every lock collision leaks a multi-MB IntelliJ index directory forever.
        """
        first = _make_provider(tmp_path)
        second = _make_provider(tmp_path)
        try:
            assert os.path.isdir(second.storage_dir)
            second.release_storage_lock()
            assert not os.path.exists(second.storage_dir)
        finally:
            first.release_storage_lock()

    def test_primary_storage_dir_survives_release(self, tmp_path: Path) -> None:
        """The deterministic per-project directory must persist after release: it is the
        index cache a restarted single instance is meant to reuse.
        """
        provider = _make_provider(tmp_path)
        os.makedirs(provider.storage_dir, exist_ok=True)
        index_marker = Path(provider.storage_dir) / "index-marker"
        index_marker.write_text("kotlin lsp index data", encoding="utf-8")

        provider.release_storage_lock()

        assert index_marker.exists()

    def test_concurrent_instances_get_different_system_path_arguments(self, tmp_path: Path) -> None:
        launcher = "/path/to/intellij-server"
        first = _make_provider(tmp_path, {"ls_path": launcher})
        second = _make_provider(tmp_path, {"ls_path": launcher})
        try:
            with patch(
                "solidlsp.language_servers.kotlin_language_server.PlatformUtils.get_platform_id",
                return_value=PlatformId.LINUX_x64,
            ):
                first_cmd = first.create_launch_command()
                second_cmd = second.create_launch_command()

            assert first_cmd == [launcher, "--stdio", "--system-path", str(tmp_path / "project-cache" / "kotlin-lsp-system")]
            assert second_cmd[:2] == [launcher, "--stdio"]
            assert second_cmd[2] == "--system-path"
            assert second_cmd[3] != first_cmd[3]
        finally:
            first.release_storage_lock()
            second.release_storage_lock()

    def test_invalid_version_is_rejected_before_download(self) -> None:
        with pytest.raises(ValueError, match="dot-separated integers"):
            KotlinLanguageServer.DependencyProvider._create_artifact("latest", PlatformId.OSX_arm64)

    def test_unsupported_modern_platform_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported platform"):
            KotlinLanguageServer.DependencyProvider._create_artifact(DEFAULT_KOTLIN_LSP_VERSION, PlatformId.LINUX_x86)
