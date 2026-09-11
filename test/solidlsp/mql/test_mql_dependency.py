"""Tests for the MQL language server dependency provider (davalillo/mql-language-server).

Covers spec R3: INITIAL/DEFAULT version resolution, versioned cache directories,
the ``mql_version`` custom-setting override (sha256 skipped for arbitrary
versions), allowed-hosts configuration, and the no-re-download cache hit.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from solidlsp.language_servers.mql_language_server import (
    _ASSET_BASENAME_BY_PLATFORM,
    DEFAULT_MQL_SHA256_BY_PLATFORM,
    DEFAULT_MQL_VERSION,
    INITIAL_MQL_SHA256_BY_PLATFORM,
    INITIAL_MQL_VERSION,
    MQL_ALLOWED_HOSTS,
    MqlLanguageServer,
    _mql_sha,
)
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.settings import SolidLSPSettings


def _make_provider(
    tmp_path: Path,
    custom_settings: dict[str, str] | None = None,
) -> MqlLanguageServer.DependencyProvider:
    return MqlLanguageServer.DependencyProvider(
        custom_settings=SolidLSPSettings.CustomLSSettings(custom_settings or {}),
        ls_resources_dir=str(tmp_path),
    )


def _get_platform_id() -> PlatformId:
    return PlatformUtils.get_platform_id()


def _write_fake_binary(executable_path: str) -> None:
    Path(executable_path).parent.mkdir(parents=True, exist_ok=True)
    Path(executable_path).write_bytes(b"#!/bin/sh\n")


@pytest.mark.mql
class TestMqlVersionConstants:
    """Verifies the pinned version/SHA literal scheme (spec R3, design D3)."""

    def test_initial_and_default_versions_are_v2_0_0(self) -> None:
        """At introduction INITIAL and DEFAULT both pin v2.0.0."""
        assert INITIAL_MQL_VERSION == "v2.0.0"
        assert DEFAULT_MQL_VERSION == "v2.0.0"

    def test_initial_and_default_shas_are_identical_at_introduction(self) -> None:
        """Both dicts must carry the same per-platform digests at introduction."""
        assert INITIAL_MQL_SHA256_BY_PLATFORM == DEFAULT_MQL_SHA256_BY_PLATFORM

    def test_sha_dicts_cover_all_release_platforms(self) -> None:
        """Every platform with a release asset has a pinned digest."""
        assert set(INITIAL_MQL_SHA256_BY_PLATFORM) == set(_ASSET_BASENAME_BY_PLATFORM)
        assert set(DEFAULT_MQL_SHA256_BY_PLATFORM) == set(_ASSET_BASENAME_BY_PLATFORM)

    @pytest.mark.parametrize("platform_key", list(_ASSET_BASENAME_BY_PLATFORM))
    def test_sha_dicts_are_64_hex_chars(self, platform_key: str) -> None:
        """Digests are SHA256 hex strings (64 chars)."""
        for sha_dict in (INITIAL_MQL_SHA256_BY_PLATFORM, DEFAULT_MQL_SHA256_BY_PLATFORM):
            sha = sha_dict[platform_key]
            assert len(sha) == 64, platform_key
            int(sha, 16)  # must be pure hex

    def test_asset_basenames_match_published_release_assets(self) -> None:
        """The basenames must match the v2.0.0 release asset names exactly
        (verified against the GitHub release API during batch 1).
        """
        assert _ASSET_BASENAME_BY_PLATFORM == {
            "linux-x64": "mql-lsp-server-linux-x64",
            "osx-x64": "mql-lsp-server-osx-x64",
            "osx-arm64": "mql-lsp-server-osx-arm64",
            "win-x64": "mql-lsp-server-win-x64.exe",
        }


@pytest.mark.mql
class TestMqlShaResolution:
    """Verifies ``_mql_sha`` semantics: pinned versions resolve, arbitrary ones skip."""

    def test_initial_version_resolves_from_initial_dict(self) -> None:
        assert _mql_sha(INITIAL_MQL_VERSION, "linux-x64") == INITIAL_MQL_SHA256_BY_PLATFORM["linux-x64"]

    def test_default_version_resolves_from_default_dict(self) -> None:
        assert _mql_sha(DEFAULT_MQL_VERSION, "linux-x64") == DEFAULT_MQL_SHA256_BY_PLATFORM["linux-x64"]

    def test_arbitrary_version_resolves_to_none(self) -> None:
        """Custom versions have no pinned hash: sha256 verification is skipped."""
        assert _mql_sha("v2.0.1", "linux-x64") is None
        assert _mql_sha("v9.9.9", "win-x64") is None


@pytest.mark.mql
class TestMqlRuntimeDependencies:
    """Verifies the RuntimeDependency entries built per platform (spec R3)."""

    @pytest.mark.parametrize("platform_id", list(PlatformId))
    def test_every_platform_with_assets_has_exactly_one_dependency(self, platform_id: PlatformId) -> None:
        """Only the 4 published platforms carry a dependency; all others fail loudly
        when a single dependency is requested.
        """
        with patch(
            "solidlsp.language_servers.common.PlatformUtils.get_platform_id",
            return_value=platform_id,
        ):
            deps = MqlLanguageServer._runtime_dependencies(DEFAULT_MQL_VERSION)
            if platform_id.value not in _ASSET_BASENAME_BY_PLATFORM:
                with pytest.raises(RuntimeError, match="Expected exactly one runtime dependency"):
                    deps.get_single_dep_for_current_platform()
            else:
                dep = deps.get_single_dep_for_current_platform()
                assert dep.url.endswith(_ASSET_BASENAME_BY_PLATFORM[platform_id.value])

    def test_urls_target_pinned_release_tag(self) -> None:
        """URLs follow the GitHub release-asset scheme for the requested version."""
        deps = MqlLanguageServer._runtime_dependencies("v2.0.1")
        dep = deps.get_dependencies_for_platform("linux-x64")[0]
        assert dep.url == "https://github.com/davalillo/mql-language-server/releases/download/v2.0.1/mql-lsp-server-linux-x64"

    def test_allowed_hosts_follow_ada_tuple(self) -> None:
        """The host tuple must include github.com AND the CDN redirect hosts (not bare github.com)."""
        assert MQL_ALLOWED_HOSTS == (
            "github.com",
            "release-assets.githubusercontent.com",
            "objects.githubusercontent.com",
        )
        deps = MqlLanguageServer._runtime_dependencies(DEFAULT_MQL_VERSION)
        for dep in deps.get_dependencies_for_platform("linux-x64"):
            assert tuple(dep.allowed_hosts) == MQL_ALLOWED_HOSTS

    def test_binary_archive_type_and_names(self) -> None:
        """Assets are bare binaries; the Windows asset carries the .exe suffix."""
        deps = MqlLanguageServer._runtime_dependencies(DEFAULT_MQL_VERSION)
        linux_dep = deps.get_dependencies_for_platform("linux-x64")[0]
        win_dep = deps.get_dependencies_for_platform("win-x64")[0]
        assert linux_dep.archive_type == "binary"
        assert linux_dep.binary_name == "mql-lsp-server"
        assert win_dep.binary_name == "mql-lsp-server.exe"


@pytest.mark.mql
class TestMqlVersionResolution:
    """Verifies install-dir resolution semantics (spec R3 scenarios; design D3 step 2)."""

    def test_initial_version_uses_legacy_unversioned_dir(self, tmp_path: Path) -> None:
        """INITIAL_* resolves into the legacy unversioned ``mql-lsp`` dir."""
        provider = _make_provider(tmp_path, {"mql_version": INITIAL_MQL_VERSION})
        expected = os.path.join(str(tmp_path), "mql-lsp", "mql-lsp-server")
        _write_fake_binary(expected)

        path = provider._get_or_install_core_dependency()

        assert path == expected

    def test_default_version_uses_versioned_dir_after_bump(self, tmp_path: Path) -> None:
        """Once INITIAL and DEFAULT diverge (a real bump), the DEFAULT install
        resolves into ``mql-lsp-{version}`` so bumps never reuse stale dirs.
        """
        bumped_default = "v2.0.1"
        with (
            patch(
                "solidlsp.language_servers.mql_language_server.DEFAULT_MQL_VERSION",
                bumped_default,
            ),
            patch(
                "solidlsp.language_servers.mql_language_server.DEFAULT_MQL_SHA256_BY_PLATFORM",
                dict.fromkeys(_ASSET_BASENAME_BY_PLATFORM, "0" * 64),
            ),
        ):
            provider = _make_provider(tmp_path)
            expected = os.path.join(str(tmp_path), f"mql-lsp-{bumped_default}", "mql-lsp-server")
            _write_fake_binary(expected)

            assert provider._get_or_install_core_dependency() == expected

    def test_default_version_uses_legacy_dir_at_introduction(self, tmp_path: Path) -> None:
        """At introduction INITIAL == DEFAULT, so the default (unpinned) install
        resolves into the legacy unversioned ``mql-lsp`` dir — matching upstream
        marksman behavior at its own introduction (INITIAL checked first).
        """
        provider = _make_provider(tmp_path)
        expected = os.path.join(str(tmp_path), "mql-lsp", "mql-lsp-server")
        _write_fake_binary(expected)

        assert provider._get_or_install_core_dependency() == expected

    def test_override_version_uses_its_own_versioned_dir(self, tmp_path: Path) -> None:
        """An arbitrary ``mql_version`` override gets its own versioned subdir."""
        provider = _make_provider(tmp_path, {"mql_version": "v2.0.1"})
        expected = os.path.join(str(tmp_path), "mql-lsp-v2.0.1", "mql-lsp-server")
        _write_fake_binary(expected)

        path = provider._get_or_install_core_dependency()

        assert path == expected

    def test_default_resolution_when_no_settings(self, tmp_path: Path) -> None:
        """With no custom settings, DEFAULT resolution applies (== INITIAL at
        introduction → the legacy unversioned dir).
        """
        provider = _make_provider(tmp_path)
        expected = os.path.join(str(tmp_path), "mql-lsp", "mql-lsp-server")
        _write_fake_binary(expected)

        assert provider._get_or_install_core_dependency() == expected

    def test_override_version_skips_sha256_verification(self, tmp_path: Path) -> None:
        """Spec R3: for arbitrary versions the URL is used but sha256 is skipped
        (no pinned hash for custom versions).
        """
        provider = _make_provider(tmp_path, {"mql_version": "v2.0.1"})
        _write_fake_binary(os.path.join(str(tmp_path), "mql-lsp-v2.0.1", "mql-lsp-server"))

        with patch("solidlsp.language_servers.common.RuntimeDependencyCollection.install") as install:
            # binary already present: install must not even be attempted
            provider._get_or_install_core_dependency()
            install.assert_not_called()

        # the *dependency object* built for the override carries sha256=None
        deps = MqlLanguageServer._runtime_dependencies("v2.0.1")
        assert deps.get_dependencies_for_platform("linux-x64")[0].sha256 is None
        # while pinned versions carry the digest
        pinned = MqlLanguageServer._runtime_dependencies(DEFAULT_MQL_VERSION)
        assert pinned.get_dependencies_for_platform("linux-x64")[0].sha256 == DEFAULT_MQL_SHA256_BY_PLATFORM["linux-x64"]

    def test_stale_default_dir_is_not_reused_after_bump_simulation(self, tmp_path: Path) -> None:
        """Version-bump simulation (spec R3): a stale ``mql-lsp-v2.0.0`` dir must not
        satisfy a bumped DEFAULT; the provider installs into ``mql-lsp-vX``.

        DEFAULT is patched to a newer tag with an empty SHA dict, mirroring a real
        DEFAULT_MQL_VERSION + DEFAULT_MQL_SHA256_BY_PLATFORM literal edit. The stale
        dir is NOT pre-seeded with a binary: the bumped version's dir differs, so the
        provider must fall through to ``install`` (proving no stale reuse) and then
        the install is mocked to place the binary in the new dir.
        """
        stale_dir = os.path.join(str(tmp_path), f"mql-lsp-{DEFAULT_MQL_VERSION}")
        _write_fake_binary(os.path.join(stale_dir, "mql-lsp-server"))

        bumped_default = "v2.0.1"
        bumped_sha = "0" * 64
        with (
            patch(
                "solidlsp.language_servers.mql_language_server.DEFAULT_MQL_VERSION",
                bumped_default,
            ),
            patch(
                "solidlsp.language_servers.mql_language_server.DEFAULT_MQL_SHA256_BY_PLATFORM",
                dict.fromkeys(_ASSET_BASENAME_BY_PLATFORM, bumped_sha),
            ),
            patch(
                "solidlsp.language_servers.common.RuntimeDependencyCollection.install",
                side_effect=lambda target_dir: _write_fake_binary(os.path.join(target_dir, "mql-lsp-server")) or {},
            ),
        ):
            provider = _make_provider(tmp_path)
            expected = os.path.join(str(tmp_path), f"mql-lsp-{bumped_default}", "mql-lsp-server")

            path = provider._get_or_install_core_dependency()

            assert path == expected
            # the stale dir must not have been reused
            assert path != os.path.join(stale_dir, "mql-lsp-server")

    def test_cache_hit_makes_no_network_request(self, tmp_path: Path) -> None:
        """Cache hit: a second resolution with the binary present must not touch the network."""
        provider = _make_provider(tmp_path)
        _write_fake_binary(os.path.join(str(tmp_path), "mql-lsp", "mql-lsp-server"))

        with patch(
            "solidlsp.language_servers.common.RuntimeDependencyCollection.install",
            side_effect=AssertionError("cache hit must not trigger a download"),
        ):
            provider._get_or_install_core_dependency()

    def test_missing_binary_after_failed_install_raises(self, tmp_path: Path) -> None:
        """If the install does not produce the binary, FileNotFoundError is raised (D3 step 3)."""
        provider = _make_provider(tmp_path)

        with (
            patch(
                "solidlsp.language_servers.common.RuntimeDependencyCollection.install",
                return_value={},
            ),
            pytest.raises(FileNotFoundError, match="Could not find mql-lsp-server executable"),
        ):
            provider._get_or_install_core_dependency()

    def test_launch_command_is_the_core_path_alone(self, tmp_path: Path) -> None:
        """Launch is stdio with no flags: command = [core_path]."""
        provider = _make_provider(tmp_path)
        core = os.path.join(str(tmp_path), "mql-lsp", "mql-lsp-server")
        _write_fake_binary(core)

        with patch(
            "solidlsp.language_servers.common.RuntimeDependencyCollection.install",
            side_effect=AssertionError("no download expected when the binary exists"),
        ):
            provider._get_or_install_core_dependency()

        assert provider._create_launch_command(core) == [core]


@pytest.mark.mql
class TestMqlRealBinaryInstall:
    """Runtime harness: the pinned v2.0.0 asset downloads, passes sha256 verification,
    is installed with exec permission, and resolves to the versioned dir
    (spec R3 'first install' + 'exec permission' scenarios).
    """

    def test_first_install_downloads_and_verifies_real_binary(self, tmp_path: Path) -> None:
        """Real 80MB v2.0.0 asset: downloaded from the pinned release URL, sha256-verified
        against INITIAL/DEFAULT_MQL_SHA256_BY_PLATFORM, installed into the legacy
        unversioned dir (INITIAL-first at introduction), chmod +x.
        """
        provider = _make_provider(tmp_path)

        path = provider._get_or_install_core_dependency()

        expected_dir = os.path.join(str(tmp_path), "mql-lsp")
        assert path == os.path.join(expected_dir, "mql-lsp-server")
        assert os.path.exists(path)
        # exec permission (non-Windows)
        if PlatformUtils.get_platform_id() != PlatformId.WIN_x64:
            assert os.stat(path).st_mode & 0o111, "binary must be executable"
