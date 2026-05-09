"""
Unit tests for the offline (upstream) JDTLS resolution helpers in
``solidlsp.language_servers.eclipse_jdtls``.

These tests cover only the path/version/validation logic; they do not start
JDTLS and do not require Java to be installed. Subprocess interactions are
mocked.
"""

from __future__ import annotations

import platform
from pathlib import Path
from unittest.mock import patch

import pytest

_JAVA_EXE_NAME = "java.exe" if platform.system() == "Windows" else "java"

from solidlsp.language_servers.eclipse_jdtls import (
    JDTLS_CONFIG_DIR_BY_PLATFORM,
    JDTLS_MIN_JDK_VERSION,
    EclipseJDTLS,
)
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.settings import SolidLSPSettings


@pytest.fixture
def custom_settings() -> SolidLSPSettings.CustomLSSettings:
    """Empty CustomLSSettings instance for tests that don't need any keys set."""
    return SolidLSPSettings.CustomLSSettings({})


def _make_fake_jdtls_install(
    root: Path, *, with_launcher: bool = True, with_native_fragments: bool = True, with_configs: bool = True
) -> Path:
    """
    Builds a minimal fake upstream JDTLS layout under ``root``: ``plugins/`` with
    a main equinox launcher jar (and optionally native fragments) and
    ``config_<platform>/`` directories. Returns ``root``.
    """
    plugins = root / "plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    if with_launcher:
        (plugins / "org.eclipse.equinox.launcher_1.7.100.v20251111-0406.jar").touch()
    if with_native_fragments:
        (plugins / "org.eclipse.equinox.launcher.cocoa.macosx.aarch64_1.2.0.v20240329-1112.jar").touch()
        (plugins / "org.eclipse.equinox.launcher.gtk.linux.x86_64_1.2.0.v20240329-1112.jar").touch()
        (plugins / "org.eclipse.equinox.launcher.win32.win32.x86_64_1.2.0.v20240329-1112.jar").touch()
    if with_configs:
        for config_name in set(JDTLS_CONFIG_DIR_BY_PLATFORM.values()):
            (root / config_name).mkdir(exist_ok=True)
    return root


# ----------------------------------------------------------------------------
# _resolve_launcher_jar
# ----------------------------------------------------------------------------


class TestResolveLauncherJar:
    def test_picks_main_launcher_excluding_native_fragments(self, tmp_path: Path) -> None:
        plugins = tmp_path / "plugins"
        plugins.mkdir()
        main_jar = plugins / "org.eclipse.equinox.launcher_1.7.100.v20251111-0406.jar"
        main_jar.touch()
        # native fragments should NOT be picked
        (plugins / "org.eclipse.equinox.launcher.cocoa.macosx.aarch64_1.2.0.v20240329-1112.jar").touch()
        (plugins / "org.eclipse.equinox.launcher.gtk.linux.x86_64_1.2.0.v20240329-1112.jar").touch()
        (plugins / "org.eclipse.equinox.launcher.win32.win32.x86_64_1.2.0.v20240329-1112.jar").touch()

        result = EclipseJDTLS.DependencyProvider._resolve_launcher_jar(plugins)
        assert result == main_jar

    def test_picks_highest_version_when_multiple_main_launchers(self, tmp_path: Path) -> None:
        plugins = tmp_path / "plugins"
        plugins.mkdir()
        (plugins / "org.eclipse.equinox.launcher_1.6.500.v20240916-1115.jar").touch()
        newer = plugins / "org.eclipse.equinox.launcher_1.7.100.v20251111-0406.jar"
        newer.touch()
        (plugins / "org.eclipse.equinox.launcher_1.7.0.v20250424-1814.jar").touch()

        result = EclipseJDTLS.DependencyProvider._resolve_launcher_jar(plugins)
        assert result == newer, "Expected the lexicographically highest launcher version to be selected"

    def test_raises_when_no_launcher_present(self, tmp_path: Path) -> None:
        plugins = tmp_path / "plugins"
        plugins.mkdir()
        # only native fragments, no main launcher
        (plugins / "org.eclipse.equinox.launcher.cocoa.macosx.aarch64_1.2.0.v20240329-1112.jar").touch()

        with pytest.raises(SolidLSPException, match="No main Equinox launcher jar found"):
            EclipseJDTLS.DependencyProvider._resolve_launcher_jar(plugins)


# ----------------------------------------------------------------------------
# _resolve_config_dir
# ----------------------------------------------------------------------------


class TestResolveConfigDir:
    @pytest.mark.parametrize(
        "platform_id,expected_dir",
        [
            ("osx-arm64", "config_mac_arm"),
            ("darwin-arm64", "config_mac_arm"),
            ("osx-x64", "config_mac"),
            ("linux-arm64", "config_linux_arm"),
            ("linux-x64", "config_linux"),
            ("win-x64", "config_win"),
        ],
    )
    def test_maps_platform_to_correct_config_dir(self, tmp_path: Path, platform_id: str, expected_dir: str) -> None:
        _make_fake_jdtls_install(tmp_path)
        with patch("solidlsp.language_servers.eclipse_jdtls.PlatformUtils.get_platform_id") as mock_get_pid:
            mock_get_pid.return_value.value = platform_id
            result = EclipseJDTLS.DependencyProvider._resolve_config_dir(tmp_path)
        assert result.name == expected_dir
        assert result.is_dir()

    def test_raises_when_config_dir_missing(self, tmp_path: Path) -> None:
        # plugins/ exists but no config_<platform>/ for current OS
        (tmp_path / "plugins").mkdir()
        with patch("solidlsp.language_servers.eclipse_jdtls.PlatformUtils.get_platform_id") as mock_get_pid:
            mock_get_pid.return_value.value = "linux-x64"
            with pytest.raises(SolidLSPException, match="Config directory .* not found"):
                EclipseJDTLS.DependencyProvider._resolve_config_dir(tmp_path)

    def test_raises_for_unsupported_platform(self, tmp_path: Path) -> None:
        _make_fake_jdtls_install(tmp_path)
        with patch("solidlsp.language_servers.eclipse_jdtls.PlatformUtils.get_platform_id") as mock_get_pid:
            mock_get_pid.return_value.value = "freebsd-riscv64"
            with pytest.raises(SolidLSPException, match="Unsupported platform"):
                EclipseJDTLS.DependencyProvider._resolve_config_dir(tmp_path)


# ----------------------------------------------------------------------------
# _inspect_java
# ----------------------------------------------------------------------------


class TestInspectJava:
    @staticmethod
    def _fake_subprocess_result(stderr: str, stdout: str = "", returncode: int = 0):
        """Build a minimal CompletedProcess-like object."""

        class _Result:
            def __init__(self) -> None:
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        return _Result()

    def test_parses_temurin_21_output(self) -> None:
        # Real Temurin 21.0.10 output (java -XshowSettings:properties -version writes to stderr)
        stderr = (
            "Property settings:\n"
            "    java.home = /Users/me/Library/Java/JavaVirtualMachines/temurin-21.0.10/Contents/Home\n"
            "    java.version = 21.0.10\n"
            'openjdk version "21.0.10" 2026-01-20 LTS\n'
            "OpenJDK Runtime Environment Temurin-21.0.10+7 (build 21.0.10+7-LTS)\n"
        )
        with patch("subprocess.run", return_value=self._fake_subprocess_result(stderr)):
            home, major = EclipseJDTLS.DependencyProvider._inspect_java("/usr/bin/java")
        assert home == "/Users/me/Library/Java/JavaVirtualMachines/temurin-21.0.10/Contents/Home"
        assert major == 21

    def test_parses_openjdk_17_output(self) -> None:
        stderr = 'Property settings:\n    java.home = /usr/lib/jvm/java-17-openjdk-amd64\nopenjdk version "17.0.5" 2023-10-17\n'
        with patch("subprocess.run", return_value=self._fake_subprocess_result(stderr)):
            home, major = EclipseJDTLS.DependencyProvider._inspect_java("/usr/bin/java")
        assert home == "/usr/lib/jvm/java-17-openjdk-amd64"
        assert major == 17

    def test_raises_when_java_home_property_missing(self) -> None:
        stderr = 'java version "21.0.0"\n'
        with patch("subprocess.run", return_value=self._fake_subprocess_result(stderr)):
            with pytest.raises(SolidLSPException, match="Could not parse java.home"):
                EclipseJDTLS.DependencyProvider._inspect_java("/usr/bin/fakejava")

    def test_raises_when_version_string_missing(self) -> None:
        stderr = "    java.home = /opt/jdk\n"
        with patch("subprocess.run", return_value=self._fake_subprocess_result(stderr)):
            with pytest.raises(SolidLSPException, match="Could not parse Java version"):
                EclipseJDTLS.DependencyProvider._inspect_java("/usr/bin/fakejava")

    def test_raises_on_subprocess_error(self) -> None:
        with patch("subprocess.run", side_effect=OSError("permission denied")):
            with pytest.raises(SolidLSPException, match="Failed to run"):
                EclipseJDTLS.DependencyProvider._inspect_java("/nonexistent/java")


# ----------------------------------------------------------------------------
# _resolve_system_jdk
# ----------------------------------------------------------------------------


class TestResolveSystemJdk:
    """Verifies the priority chain: java_home setting > JAVA_HOME env > PATH."""

    @staticmethod
    def _make_jdk_layout(root: Path, java_exe_name: str = _JAVA_EXE_NAME) -> Path:
        bin_dir = root / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        (bin_dir / java_exe_name).touch()
        return root

    def _patch_inspect_java(self, real_home: str, major: int):
        return patch.object(EclipseJDTLS.DependencyProvider, "_inspect_java", return_value=(real_home, major))

    def test_uses_explicit_java_home_setting(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        explicit_jdk = self._make_jdk_layout(tmp_path / "explicit-jdk")
        monkeypatch.delenv("JAVA_HOME", raising=False)

        with self._patch_inspect_java(str(explicit_jdk), 21):
            settings = SolidLSPSettings.CustomLSSettings({"java_home": str(explicit_jdk)})
            home, java_path = EclipseJDTLS.DependencyProvider._resolve_system_jdk(settings)

        assert Path(home) == explicit_jdk
        assert Path(java_path).name == _JAVA_EXE_NAME

    def test_falls_back_to_java_home_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_jdk = self._make_jdk_layout(tmp_path / "env-jdk")
        monkeypatch.setenv("JAVA_HOME", str(env_jdk))

        with self._patch_inspect_java(str(env_jdk), 21):
            settings = SolidLSPSettings.CustomLSSettings({})
            home, _ = EclipseJDTLS.DependencyProvider._resolve_system_jdk(settings)

        assert Path(home) == env_jdk

    def test_falls_back_to_which_java(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, custom_settings: SolidLSPSettings.CustomLSSettings
    ) -> None:
        path_jdk = self._make_jdk_layout(tmp_path / "path-jdk")
        java_path = path_jdk / "bin" / _JAVA_EXE_NAME
        monkeypatch.delenv("JAVA_HOME", raising=False)

        with patch("solidlsp.language_servers.eclipse_jdtls.shutil.which", return_value=str(java_path)):
            with self._patch_inspect_java(str(path_jdk), 21):
                home, _ = EclipseJDTLS.DependencyProvider._resolve_system_jdk(custom_settings)

        assert Path(home) == path_jdk

    def test_raises_when_no_java_anywhere(
        self, monkeypatch: pytest.MonkeyPatch, custom_settings: SolidLSPSettings.CustomLSSettings
    ) -> None:
        monkeypatch.delenv("JAVA_HOME", raising=False)
        with patch("solidlsp.language_servers.eclipse_jdtls.shutil.which", return_value=None):
            with pytest.raises(SolidLSPException, match="Could not locate a Java installation"):
                EclipseJDTLS.DependencyProvider._resolve_system_jdk(custom_settings)

    def test_raises_for_invalid_explicit_java_home(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # path exists but no bin/java
        broken = tmp_path / "broken-jdk"
        broken.mkdir()
        monkeypatch.delenv("JAVA_HOME", raising=False)

        settings = SolidLSPSettings.CustomLSSettings({"java_home": str(broken)})
        with pytest.raises(SolidLSPException, match=r"java_home=.*invalid"):
            EclipseJDTLS.DependencyProvider._resolve_system_jdk(settings)

    def test_raises_for_too_old_jdk(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        old_jdk = self._make_jdk_layout(tmp_path / "jdk-17")
        monkeypatch.setenv("JAVA_HOME", str(old_jdk))

        with self._patch_inspect_java(str(old_jdk), 17):
            settings = SolidLSPSettings.CustomLSSettings({})
            with pytest.raises(SolidLSPException, match=f"requires JDK {JDTLS_MIN_JDK_VERSION}"):
                EclipseJDTLS.DependencyProvider._resolve_system_jdk(settings)

    def test_uses_real_jdk_home_when_locator_is_macos_stub(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, custom_settings: SolidLSPSettings.CustomLSSettings
    ) -> None:
        """
        Simulates the macOS /usr/bin/java stub: the locator points to /usr/bin/java but the JVM's
        java.home is the actual JDK. The resolver should report the real JDK home.
        """
        real_jdk = self._make_jdk_layout(tmp_path / "real-jdk-21")
        macos_stub = tmp_path / "fake-usr" / "bin" / _JAVA_EXE_NAME
        macos_stub.parent.mkdir(parents=True)
        macos_stub.touch()
        monkeypatch.delenv("JAVA_HOME", raising=False)

        with patch("solidlsp.language_servers.eclipse_jdtls.shutil.which", return_value=str(macos_stub)):
            with self._patch_inspect_java(str(real_jdk), 21):
                home, java_path = EclipseJDTLS.DependencyProvider._resolve_system_jdk(custom_settings)

        # the resolver must trust the JVM's reported java.home, not parent.parent of the stub
        assert Path(home) == real_jdk
        # and prefer the real-home java executable over the stub
        assert Path(java_path) == real_jdk / "bin" / _JAVA_EXE_NAME


# ----------------------------------------------------------------------------
# _setup_from_existing_install
# ----------------------------------------------------------------------------


class TestSetupFromExistingInstall:
    @pytest.fixture
    def lombok_jar(self, tmp_path: Path) -> Path:
        jar = tmp_path / "lombok-1.18.44.jar"
        jar.touch()
        return jar

    @pytest.fixture
    def jdtls_root(self, tmp_path: Path) -> Path:
        return _make_fake_jdtls_install(tmp_path / "jdtls")

    def _fake_jdk(self, tmp_path: Path) -> Path:
        jdk = tmp_path / "jdk-21"
        (jdk / "bin").mkdir(parents=True)
        (jdk / "bin" / "java").touch()
        return jdk

    def test_happy_path_returns_runtime_paths_with_no_gradle_and_no_intellicode(
        self, tmp_path: Path, jdtls_root: Path, lombok_jar: Path, custom_settings: SolidLSPSettings.CustomLSSettings
    ) -> None:
        jdk = self._fake_jdk(tmp_path)
        with patch("solidlsp.language_servers.eclipse_jdtls.PlatformUtils.get_platform_id") as mock_pid:
            mock_pid.return_value.value = "linux-x64"
            with patch.object(EclipseJDTLS.DependencyProvider, "_resolve_system_jdk", return_value=(str(jdk), str(jdk / "bin" / "java"))):
                result = EclipseJDTLS.DependencyProvider._setup_from_existing_install(str(jdtls_root), str(lombok_jar), custom_settings)

        assert result.gradle_path is None
        assert result.intellicode_jar_path is None
        assert result.intellisense_members_path is None
        assert result.lombok_jar_path == str(lombok_jar)
        assert result.jre_home_path == str(jdk)
        assert Path(result.jdtls_launcher_jar_path).name.startswith("org.eclipse.equinox.launcher_")
        assert Path(result.jdtls_readonly_config_path).name == "config_linux"

    def test_raises_for_nonexistent_jdtls_path(
        self, tmp_path: Path, lombok_jar: Path, custom_settings: SolidLSPSettings.CustomLSSettings
    ) -> None:
        with pytest.raises(SolidLSPException, match="not an existing directory"):
            EclipseJDTLS.DependencyProvider._setup_from_existing_install(str(tmp_path / "does-not-exist"), str(lombok_jar), custom_settings)

    def test_raises_when_plugins_dir_missing(
        self, tmp_path: Path, lombok_jar: Path, custom_settings: SolidLSPSettings.CustomLSSettings
    ) -> None:
        empty_root = tmp_path / "no-plugins"
        empty_root.mkdir()
        with pytest.raises(SolidLSPException, match="'plugins/' directory not found"):
            EclipseJDTLS.DependencyProvider._setup_from_existing_install(str(empty_root), str(lombok_jar), custom_settings)

    def test_raises_when_lombok_jar_missing(
        self, jdtls_root: Path, tmp_path: Path, custom_settings: SolidLSPSettings.CustomLSSettings
    ) -> None:
        with pytest.raises(SolidLSPException, match="lombok_path .* does not exist"):
            EclipseJDTLS.DependencyProvider._setup_from_existing_install(
                str(jdtls_root), str(tmp_path / "no-such-lombok.jar"), custom_settings
            )


# ----------------------------------------------------------------------------
# _setup_runtime_dependencies (mode-switch logic)
# ----------------------------------------------------------------------------


class TestSetupRuntimeDependenciesModeSwitch:
    """Verifies the activation trigger: both jdtls_path and lombok_path => upstream mode."""

    def test_both_set_invokes_upstream_mode(self) -> None:
        settings = SolidLSPSettings.CustomLSSettings({"jdtls_path": "/x", "lombok_path": "/y"})
        with patch.object(EclipseJDTLS.DependencyProvider, "_setup_from_existing_install", return_value="upstream-result") as mock_upstream:
            result = EclipseJDTLS.DependencyProvider._setup_runtime_dependencies("/ignored", settings)
        mock_upstream.assert_called_once_with("/x", "/y", settings)
        assert result == "upstream-result"

    def test_only_jdtls_path_set_raises(self) -> None:
        settings = SolidLSPSettings.CustomLSSettings({"jdtls_path": "/x"})
        with pytest.raises(SolidLSPException, match="must be set together"):
            EclipseJDTLS.DependencyProvider._setup_runtime_dependencies("/ignored", settings)

    def test_only_lombok_path_set_raises(self) -> None:
        settings = SolidLSPSettings.CustomLSSettings({"lombok_path": "/y"})
        with pytest.raises(SolidLSPException, match="must be set together"):
            EclipseJDTLS.DependencyProvider._setup_runtime_dependencies("/ignored", settings)


# ----------------------------------------------------------------------------
# _compute_workspace_hash
# ----------------------------------------------------------------------------


class TestComputeWorkspaceHash:
    """
    The launcher jar path is mixed into the hash so that switching JDTLS versions
    (default vscode-java VSIX bump or upstream install change) lands in a separate
    ws_dir and avoids stale OSGi configs from the previous version blocking startup.

    Backwards-compatibility carve-out: legacy default-mode users on
    INITIAL_VSCODE_JAVA_VERSION keep the original ``md5(repository_root_path)`` format,
    so existing JDTLS workspaces and project caches are reused without a one-time reindex.
    """

    REPO = "/home/me/projects/widgets"
    DEFAULT_LAUNCHER = "/srv/serena/static/eclipse-jdtls-1.49.0/plugins/org.eclipse.equinox.launcher_1.7.100.jar"
    UPSTREAM_LAUNCHER = "/opt/homebrew/Cellar/jdtls/1.50.0/libexec/plugins/org.eclipse.equinox.launcher_1.7.0.jar"

    def _initial_settings(self) -> "SolidLSPSettings.CustomLSSettings":
        from solidlsp.language_servers.eclipse_jdtls import INITIAL_VSCODE_JAVA_VERSION

        return SolidLSPSettings.CustomLSSettings({"vscode_java_version": INITIAL_VSCODE_JAVA_VERSION})

    def test_initial_default_mode_matches_pre_upstream_format(self) -> None:
        """Legacy carve-out: INITIAL default-mode hash MUST equal md5(repository_root_path)."""
        import hashlib

        expected = hashlib.md5(self.REPO.encode()).hexdigest()
        result = EclipseJDTLS.DependencyProvider._compute_workspace_hash(self.REPO, self.DEFAULT_LAUNCHER, self._initial_settings())
        assert result == expected

    def test_initial_default_mode_ignores_launcher_path(self) -> None:
        """Legacy INITIAL hash must not depend on launcher path (so legacy users keep cache)."""
        s = self._initial_settings()
        h1 = EclipseJDTLS.DependencyProvider._compute_workspace_hash(self.REPO, self.DEFAULT_LAUNCHER, s)
        h2 = EclipseJDTLS.DependencyProvider._compute_workspace_hash(self.REPO, self.UPSTREAM_LAUNCHER, s)
        assert h1 == h2

    def test_default_mode_non_initial_includes_launcher_path(self) -> None:
        """Default mode on a non-INITIAL version must mix in launcher path so version bumps re-init."""
        empty_settings = SolidLSPSettings.CustomLSSettings({})
        h1 = EclipseJDTLS.DependencyProvider._compute_workspace_hash(self.REPO, self.DEFAULT_LAUNCHER, empty_settings)
        h2 = EclipseJDTLS.DependencyProvider._compute_workspace_hash(self.REPO, self.UPSTREAM_LAUNCHER, empty_settings)
        assert h1 != h2

    def test_upstream_mode_includes_launcher_path(self) -> None:
        """When jdtls_path is set, different launcher paths must produce different hashes."""
        settings = SolidLSPSettings.CustomLSSettings({"jdtls_path": "/opt/homebrew/Cellar/jdtls/1.50.0/libexec"})
        h1 = EclipseJDTLS.DependencyProvider._compute_workspace_hash(self.REPO, self.DEFAULT_LAUNCHER, settings)
        h2 = EclipseJDTLS.DependencyProvider._compute_workspace_hash(self.REPO, self.UPSTREAM_LAUNCHER, settings)
        assert h1 != h2

    def test_initial_and_upstream_produce_different_hashes(self) -> None:
        """Same repo + same launcher path but INITIAL-default vs upstream → different ws_dir."""
        initial_h = EclipseJDTLS.DependencyProvider._compute_workspace_hash(self.REPO, self.UPSTREAM_LAUNCHER, self._initial_settings())
        upstream_h = EclipseJDTLS.DependencyProvider._compute_workspace_hash(
            self.REPO,
            self.UPSTREAM_LAUNCHER,
            SolidLSPSettings.CustomLSSettings({"jdtls_path": "/opt/homebrew/Cellar/jdtls/1.50.0/libexec"}),
        )
        assert initial_h != upstream_h

    def test_different_repo_paths_produce_different_hashes(self) -> None:
        empty_settings = SolidLSPSettings.CustomLSSettings({})
        h1 = EclipseJDTLS.DependencyProvider._compute_workspace_hash("/a/repo", self.DEFAULT_LAUNCHER, empty_settings)
        h2 = EclipseJDTLS.DependencyProvider._compute_workspace_hash("/b/repo", self.DEFAULT_LAUNCHER, empty_settings)
        assert h1 != h2
