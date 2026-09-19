"""Tests for the MQL language server dependency provider (davalillo/mql-language-server).

Covers spec R3: INITIAL/DEFAULT version resolution, versioned cache directories,
the ``mql_version`` custom-setting override (sha256 skipped for arbitrary
versions), allowed-hosts configuration, and the no-re-download cache hit.
"""

import os
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from solidlsp.language_servers.common import RuntimeDependencyCollection
from solidlsp.language_servers.mql_language_server import (
    _ASSET_BASENAME_BY_PLATFORM,
    DEFAULT_MQL_SHA256_BY_PLATFORM,
    DEFAULT_MQL_VERSION,
    HISTORICAL_MQL_SHA256_BY_VERSION,
    INITIAL_MQL_SHA256_BY_PLATFORM,
    INITIAL_MQL_VERSION,
    MQL_ALLOWED_HOSTS,
    MqlLanguageServer,
    _fetch_release_checksums,
    _mql_sha,
)
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_utils import FileUtils, PlatformId, PlatformUtils
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


def _expected_binary_name() -> str:
    """Binary filename the provider resolves for the current platform.

    The win-x64 RuntimeDependency carries the ``.exe`` suffix
    (``mql_language_server.py``), so expected paths and pre-seeded fake
    binaries must match it exactly.
    """
    return "mql-lsp-server.exe" if _get_platform_id() == PlatformId.WIN_x64 else "mql-lsp-server"


def _skip_if_real_downloads_disabled() -> None:
    """Skips the calling test when real GitHub downloads are disabled.

    Network-dependent tests validate the pinning end to end and keep running
    in CI; ``MQL_SKIP_REAL_DOWNLOAD_TESTS=1`` is a local escape hatch so flaky
    GitHub/rate-limit conditions cannot break a local batch.
    """
    if os.environ.get("MQL_SKIP_REAL_DOWNLOAD_TESTS") == "1":
        pytest.skip("MQL_SKIP_REAL_DOWNLOAD_TESTS=1 (network-dependent test disabled)")


def _write_fake_binary(executable_path: str) -> None:
    Path(executable_path).parent.mkdir(parents=True, exist_ok=True)
    Path(executable_path).write_bytes(b"#!/bin/sh\n")


@pytest.mark.mql
class TestMqlVersionConstants:
    """Verifies the pinned version/SHA literal scheme (spec R3, design D3)."""

    def test_introduction_pins_v2_3_0_for_both(self) -> None:
        """INITIAL is frozen at the introduction version and DEFAULT starts
        identical to it (v2.3.0 at the time of the PR); the two diverge on the
        first real DEFAULT bump.
        """
        assert INITIAL_MQL_VERSION == "v2.3.0"
        assert DEFAULT_MQL_VERSION == "v2.3.0"

    def test_initial_shas_match_default_shas_at_introduction(self) -> None:
        """INITIAL digests are frozen forever at their introduction values and
        DEFAULT starts out identical to them.
        """
        assert set(INITIAL_MQL_SHA256_BY_PLATFORM) == set(DEFAULT_MQL_SHA256_BY_PLATFORM)

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
        """The basenames must match the published release asset names exactly
        (verified against the GitHub release API; stable across v2.0.x, v2.2.0 and v2.3.0).
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
        """Custom versions have no pinned hash locally; the digest is resolved
        from the release's CHECKSUMS.txt at install time (see
        TestMqlVersionResolution.test_override_version_resolves_digests_via_checksums_txt).
        """
        assert _mql_sha("v2.0.2", "linux-x64") is None
        assert _mql_sha("v9.9.9", "win-x64") is None

    def test_historical_registry_is_empty_at_introduction(self) -> None:
        """No formerly-pinned versions exist at introduction; the registry only
        grows when a future DEFAULT bump supersedes a shipped version.
        """
        assert HISTORICAL_MQL_SHA256_BY_VERSION == {}

    def test_former_default_resolves_from_historical_dict_after_simulated_bump(self, tmp_path: Path) -> None:
        """After a DEFAULT bump, the formerly-pinned version keeps hash verification
        via the historical digest registry, never falling into the unverified path.

        Simulates the first real bump (DEFAULT → v2.3.1) with v2.3.0 moved into the
        historical registry, exactly as the corresponding literal edit would do.
        """
        bumped_default = "v2.3.1"
        with (
            patch(
                "solidlsp.language_servers.mql_language_server.DEFAULT_MQL_VERSION",
                bumped_default,
            ),
            patch(
                "solidlsp.language_servers.mql_language_server.DEFAULT_MQL_SHA256_BY_PLATFORM",
                dict.fromkeys(_ASSET_BASENAME_BY_PLATFORM, "0" * 64),
            ),
            patch.dict(
                "solidlsp.language_servers.mql_language_server.HISTORICAL_MQL_SHA256_BY_VERSION",
                {"v2.3.0": dict(INITIAL_MQL_SHA256_BY_PLATFORM)},
            ),
        ):
            deps = MqlLanguageServer._runtime_dependencies("v2.3.0")
            dep = deps.get_dependencies_for_platform("linux-x64")[0]
            assert dep.sha256 == INITIAL_MQL_SHA256_BY_PLATFORM["linux-x64"]

    def test_fetch_release_checksums_parses_default_file(self) -> None:
        """``_fetch_release_checksums`` parses the real CHECKSUMS.txt format
        (``<sha256>  ./<asset>`` lines, ``#`` comments) into a basename→digest map
        that agrees with the pinned DEFAULT digests.
        """
        _skip_if_real_downloads_disabled()

        checksums = _fetch_release_checksums(DEFAULT_MQL_VERSION)
        for platform_key, basename in _ASSET_BASENAME_BY_PLATFORM.items():
            assert checksums[basename] == DEFAULT_MQL_SHA256_BY_PLATFORM[platform_key], platform_key

    def test_fetch_release_checksums_missing_version_raises(self) -> None:
        """A version without a release/CHECKSUMS.txt is refused, not silently unverified."""
        _skip_if_real_downloads_disabled()

        with pytest.raises(SolidLSPException, match="CHECKSUMS.txt"):
            _fetch_release_checksums("v0.0.0-does-not-exist")


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
                assert dep.url is not None
                assert dep.url.endswith(_ASSET_BASENAME_BY_PLATFORM[platform_id.value])

    def test_urls_target_pinned_release_tag(self) -> None:
        """URLs follow the GitHub release-asset scheme for the requested version."""
        deps = MqlLanguageServer._runtime_dependencies(DEFAULT_MQL_VERSION)
        dep = deps.get_dependencies_for_platform("linux-x64")[0]
        assert dep.url == "https://github.com/davalillo/mql-language-server/releases/download/v2.3.0/mql-lsp-server-linux-x64"

    def test_former_default_resolves_from_historical_dict_after_simulated_bump(self, tmp_path: Path) -> None:
        """After a DEFAULT bump, the formerly-pinned version keeps hash verification
        via the historical digest registry, never falling into the unverified path.

        Simulates the first real bump (DEFAULT → v2.3.1) with v2.3.0 moved into the
        historical registry, exactly as the corresponding literal edit would do.
        """
        bumped_default = "v2.3.1"
        with (
            patch(
                "solidlsp.language_servers.mql_language_server.DEFAULT_MQL_VERSION",
                bumped_default,
            ),
            patch(
                "solidlsp.language_servers.mql_language_server.DEFAULT_MQL_SHA256_BY_PLATFORM",
                dict.fromkeys(_ASSET_BASENAME_BY_PLATFORM, "0" * 64),
            ),
            patch.dict(
                "solidlsp.language_servers.mql_language_server.HISTORICAL_MQL_SHA256_BY_VERSION",
                {"v2.3.0": dict(INITIAL_MQL_SHA256_BY_PLATFORM)},
            ),
        ):
            deps = MqlLanguageServer._runtime_dependencies("v2.3.0")
            dep = deps.get_dependencies_for_platform("linux-x64")[0]
            assert dep.sha256 == INITIAL_MQL_SHA256_BY_PLATFORM["linux-x64"]

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
        expected = os.path.join(str(tmp_path), "mql-lsp", _expected_binary_name())
        _write_fake_binary(expected)

        path = provider._get_or_install_core_dependency()

        assert path == expected

    def test_default_version_uses_versioned_dir_after_bump(self, tmp_path: Path) -> None:
        """Once INITIAL and DEFAULT diverge (a future real bump), the DEFAULT install
        resolves into ``mql-lsp-{version}`` so bumps never reuse stale dirs.
        """
        bumped_default = "v2.3.1"
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
            expected = os.path.join(str(tmp_path), f"mql-lsp-{bumped_default}", _expected_binary_name())
            _write_fake_binary(expected)

            assert provider._get_or_install_core_dependency() == expected

    def test_default_resolution_when_no_settings(self, tmp_path: Path) -> None:
        """With no custom settings, DEFAULT resolution applies; at introduction
        DEFAULT == INITIAL, so the legacy unversioned ``mql-lsp`` dir is used.
        """
        provider = _make_provider(tmp_path)
        expected = os.path.join(str(tmp_path), "mql-lsp", _expected_binary_name())
        _write_fake_binary(expected)

        assert provider._get_or_install_core_dependency() == expected

    def test_override_version_resolves_digests_via_checksums_txt(self, tmp_path: Path) -> None:
        """Spec R3 (post-audit): a custom ``mql_version`` override must resolve its
        digests from the release's own CHECKSUMS.txt before downloading — never
        download unverified.
        """
        provider = _make_provider(tmp_path, {"mql_version": "v2.0.2"})
        digest = "a" * 64

        def fake_install(target_dir: str) -> dict[str, str]:
            _write_fake_binary(os.path.join(target_dir, _expected_binary_name()))
            return {}

        with (
            patch(
                "solidlsp.language_servers.mql_language_server.MqlLanguageServer._resolve_override_digests",
                return_value=dict.fromkeys(_ASSET_BASENAME_BY_PLATFORM, digest),
            ) as resolve,
            patch(
                "solidlsp.language_servers.common.RuntimeDependencyCollection.install",
                side_effect=fake_install,
            ) as install,
        ):
            provider._get_or_install_core_dependency()

            resolve.assert_called_once_with("v2.0.2")
            install.assert_called_once()

        # the install ran against the override's versioned dir with a resolved digest
        assert install.call_args.args[0].endswith("mql-lsp-v2.0.2")

    def test_override_version_refuses_install_when_checksums_unavailable(self, tmp_path: Path) -> None:
        """A custom override whose CHECKSUMS.txt cannot be fetched must refuse the
        install entirely — no unverified binary download may happen.
        """
        provider = _make_provider(tmp_path, {"mql_version": "v2.0.2"})

        with (
            patch(
                "solidlsp.language_servers.mql_language_server._fetch_release_checksums",
                side_effect=SolidLSPException("Could not fetch CHECKSUMS.txt"),
            ),
            patch(
                "solidlsp.language_servers.common.RuntimeDependencyCollection.install",
                side_effect=AssertionError("unverified download must never be attempted"),
            ),
            pytest.raises(SolidLSPException, match="CHECKSUMS"),
        ):
            provider._get_or_install_core_dependency()

        # no install dir may be left behind
        assert not os.path.exists(os.path.join(str(tmp_path), "mql-lsp-v2.0.2"))

    def test_stale_default_dir_is_not_reused_after_bump_simulation(self, tmp_path: Path) -> None:
        """Version-bump simulation: a stale ``mql-lsp-v2.3.0`` dir must not satisfy a
        bumped DEFAULT; the provider installs into ``mql-lsp-vX``.

        DEFAULT is patched to a newer tag with an empty SHA dict, mirroring a real
        DEFAULT_MQL_VERSION + DEFAULT_MQL_SHA256_BY_PLATFORM literal edit. The stale
        dir is NOT pre-seeded with a binary: the bumped version's dir differs, so the
        provider must fall through to ``install`` (proving no stale reuse) and then
        the install is mocked to place the binary in the new dir.
        """
        stale_dir = os.path.join(str(tmp_path), "mql-lsp-v2.3.0")
        _write_fake_binary(os.path.join(stale_dir, _expected_binary_name()))

        bumped_default = "v2.3.1"
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
                side_effect=lambda target_dir: _write_fake_binary(os.path.join(target_dir, _expected_binary_name())) or {},
            ),
        ):
            provider = _make_provider(tmp_path)
            expected = os.path.join(str(tmp_path), f"mql-lsp-{bumped_default}", _expected_binary_name())

            path = provider._get_or_install_core_dependency()

            assert path == expected
            # the stale dir must not have been reused
            assert path != os.path.join(stale_dir, _expected_binary_name())

    def test_cache_hit_makes_no_network_request(self, tmp_path: Path) -> None:
        """Cache hit: a second resolution with the binary present must not touch the network."""
        provider = _make_provider(tmp_path)
        _write_fake_binary(os.path.join(str(tmp_path), "mql-lsp", _expected_binary_name()))

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
        core = os.path.join(str(tmp_path), "mql-lsp", _expected_binary_name())
        _write_fake_binary(core)

        with patch(
            "solidlsp.language_servers.common.RuntimeDependencyCollection.install",
            side_effect=AssertionError("no download expected when the binary exists"),
        ):
            provider._get_or_install_core_dependency()

        assert provider._create_launch_command(core) == [core]


@pytest.mark.mql
class TestMqlSecurityRefusals:
    """Verifies the threat-matrix boundary: the install path must refuse
    tampered targets instead of silently producing a usable binary (design D7
    threat matrix, "Executable download+classification" row).
    """

    def test_url_outside_allowed_hosts_is_refused(self, tmp_path: Path) -> None:
        """Spec R3 host-validation: a dependency URL resolving outside
        MQL_ALLOWED_HOSTS must be refused with an explicit error naming the
        offending host — before any bytes hit the filesystem.
        """
        # build the exact runtime dependency the provider resolves, then tamper
        # its URL host to simulate a hijacked release channel
        deps = MqlLanguageServer._runtime_dependencies(DEFAULT_MQL_VERSION)
        dep = replace(deps.get_single_dep_for_current_platform(), url="https://evil.example.com/mql-lsp-server")

        with pytest.raises(SolidLSPException, match="evil.example.com") as excinfo:
            FileUtils.download_file_verified(
                dep.url,
                str(tmp_path / _expected_binary_name()),
                expected_sha256=dep.sha256,
                allowed_hosts=dep.allowed_hosts,
            )

        # the refusal must come from host validation, not a network error
        assert "allowed hosts" in str(excinfo.value), f"expected host-validation refusal, got: {excinfo.value}"
        assert not (tmp_path / _expected_binary_name()).exists(), "refused download must leave no artifact"

    def test_sha256_mismatch_refuses_install_and_leaves_no_usable_binary(self, tmp_path: Path) -> None:
        """A downloaded asset whose digest differs from the pinned SHA must abort
        the install: no binary may be left usable at the target path.
        """
        wrong_sha = "0" * 64
        deps = MqlLanguageServer._runtime_dependencies(DEFAULT_MQL_VERSION)
        dep = deps.get_single_dep_for_current_platform()
        assert dep.sha256 is not None, "pinned dependency must carry a sha256"

        # real download machinery with a corrupted body. Note: download_file_verified
        # wraps the checksum failure into the generic "Error downloading file."
        # SolidLSPException (the detailed checksum message is only logged); the
        # security property asserted is the refusal + no artifact left behind.
        payload = b"MQLTAMPEREDPAYLOAD"
        with (
            patch(
                "solidlsp.ls_utils.requests.get",
                return_value=_FakeResponse(payload, dep.url),
            ),
            pytest.raises(SolidLSPException),
        ):
            FileUtils.download_file_verified(
                dep.url,
                str(tmp_path / _expected_binary_name()),
                expected_sha256=wrong_sha,
                allowed_hosts=dep.allowed_hosts,
            )

        assert not (tmp_path / _expected_binary_name()).exists(), "refused install must leave no usable binary"

    def test_provider_install_failure_leaves_no_executable_to_launch(self, tmp_path: Path) -> None:
        """End-to-end refusal path: with the real (host+sha enforcing) download
        chain patched to fail at the checksum step, the provider must raise
        FileNotFoundError — i.e. there is no binary to launch — and must not
        leave an executable behind.
        """
        provider = _make_provider(tmp_path)

        with (
            patch(
                "solidlsp.ls_utils.requests.get",
                return_value=_FakeResponse(b"tampered", "https://github.com/final"),
            ),
            pytest.raises((SolidLSPException, FileNotFoundError)),
        ):
            provider._get_or_install_core_dependency()

        for binary_name in ("mql-lsp-server", "mql-lsp-server.exe"):
            binary_path = os.path.join(str(tmp_path), "mql-lsp", binary_name)
            assert not os.path.exists(binary_path), "failed install must leave no usable binary"

    def test_provider_uses_real_download_chain(self) -> None:
        """The MQL install must go through the verified download chain
        (host validation + sha256), not a bypass: RuntimeDependencyCollection._install_from_url
        must receive MQL's pinned sha256 and allowed_hosts.
        """
        with patch(
            "solidlsp.ls_utils.FileUtils.download_and_extract_archive_verified",
            side_effect=lambda *a, **kw: (_ for _ in ()).throw(SolidLSPException("stop")),
        ) as chain:
            deps = MqlLanguageServer._runtime_dependencies(DEFAULT_MQL_VERSION)
            dep = deps.get_single_dep_for_current_platform()
            try:
                RuntimeDependencyCollection._install_from_url(dep, "/tmp/should-not-exist")
            except SolidLSPException:
                pass

        chain.assert_called_once()
        _, kwargs = chain.call_args
        assert kwargs["expected_sha256"] == DEFAULT_MQL_SHA256_BY_PLATFORM[_get_platform_id().value]
        assert tuple(kwargs["allowed_hosts"]) == MQL_ALLOWED_HOSTS

        # and the MQL dependency object must carry the pinned digest + hosts
        assert dep.sha256 == DEFAULT_MQL_SHA256_BY_PLATFORM[_get_platform_id().value]
        assert tuple(dep.allowed_hosts) == MQL_ALLOWED_HOSTS


class _FakeResponse:
    """Minimal requests.Response stand-in for download tests (mirrors test_ls_utils)."""

    def __init__(self, payload: bytes, final_url: str) -> None:
        self.status_code = 200
        self.headers = {}
        self.url = final_url
        self._payload = payload

    def iter_content(self, chunk_size: int = 1):
        for offset in range(0, len(self._payload), chunk_size):
            yield self._payload[offset : offset + chunk_size]

    def close(self) -> None:
        return None


@pytest.mark.mql
class TestMqlRealBinaryInstall:
    """Runtime harness: the pinned DEFAULT asset downloads, passes sha256 verification,
    is installed with exec permission, and resolves to the versioned dir
    (spec R3 'first install' + 'exec permission' scenarios).
    """

    def test_first_install_downloads_and_verifies_real_binary(self, tmp_path: Path) -> None:
        """Real DEFAULT (v2.3.0) asset: downloaded from the pinned release URL, sha256-verified
        against DEFAULT_MQL_SHA256_BY_PLATFORM, installed into the legacy
        ``mql-lsp`` dir (DEFAULT == INITIAL at introduction), chmod +x.

        Network-dependent by design (it validates the pinning end to end).
        Skipped when MQL_SKIP_REAL_DOWNLOAD_TESTS=1 so flaky GitHub/rate-limit
        conditions cannot break the CI batch.
        """
        _skip_if_real_downloads_disabled()

        provider = _make_provider(tmp_path)

        path = provider._get_or_install_core_dependency()

        expected_dir = os.path.join(str(tmp_path), "mql-lsp")
        assert path == os.path.join(expected_dir, _expected_binary_name())
        assert os.path.exists(path)
        # exec permission (non-Windows)
        if PlatformUtils.get_platform_id() != PlatformId.WIN_x64:
            assert os.stat(path).st_mode & 0o111, "binary must be executable"
