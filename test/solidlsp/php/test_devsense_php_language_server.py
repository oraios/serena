from pathlib import Path
from unittest.mock import patch

from solidlsp.language_servers.devsense_php_language_server import (
    DEFAULT_DEVSENSE_PHP_LS_VERSION,
    DevsensePHPLanguageServer,
)
from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.settings import SolidLSPSettings


def _custom_settings(values: dict | None = None) -> SolidLSPSettings.CustomLSSettings:
    return SolidLSPSettings.CustomLSSettings(values)


class TestDevsensePHPDependencyProvider:
    def test_create_launch_command_uses_stdio(self, tmp_path: Path) -> None:
        provider = DevsensePHPLanguageServer.DependencyProvider(_custom_settings(), str(tmp_path))

        assert provider._create_launch_command("/opt/devsense-php-ls") == ["/opt/devsense-php-ls", "--stdio"]

    def test_ls_path_override_bypasses_managed_install(self, tmp_path: Path) -> None:
        provider = DevsensePHPLanguageServer.DependencyProvider(_custom_settings({"ls_path": "/custom/devsense-php-ls"}), str(tmp_path))

        with patch.object(provider, "_get_or_install_core_dependency") as get_dependency:
            assert provider.create_launch_command() == ["/custom/devsense-php-ls", "--stdio"]
            get_dependency.assert_not_called()

    def test_platform_binary_path_uses_official_layout(self, tmp_path: Path) -> None:
        install_dir = str(tmp_path / "devsense-php-ls")
        assert DevsensePHPLanguageServer.DependencyProvider._platform_binary_path(install_dir, PlatformId.LINUX_x64) == str(
            tmp_path / "devsense-php-ls" / "node_modules" / "devsense-php-ls-linux-x64" / "dist" / "devsense.php.ls"
        )
        assert DevsensePHPLanguageServer.DependencyProvider._platform_binary_path(install_dir, PlatformId.WIN_x64) == str(
            tmp_path / "devsense-php-ls" / "node_modules" / "devsense-php-ls-win32-x64" / "dist" / "devsense.php.ls.exe"
        )

    def test_managed_install_uses_pinned_npm_package(self, tmp_path: Path) -> None:
        provider = DevsensePHPLanguageServer.DependencyProvider(_custom_settings(), str(tmp_path))
        commands: list[str | list[str]] = []

        def fake_run(command: str | list[str], cwd: str) -> None:
            commands.append(command)
            installed = Path(provider._platform_binary_path(cwd, PlatformUtils.get_platform_id()))
            installed.parent.mkdir(parents=True)
            installed.touch()

        with (
            patch("solidlsp.language_servers.devsense_php_language_server.shutil.which", return_value="/usr/bin/node"),
            patch(
                "solidlsp.language_servers.devsense_php_language_server.RuntimeDependencyCollection._run_command",
                side_effect=fake_run,
            ),
        ):
            result = provider._get_or_install_core_dependency()

        expected = provider._platform_binary_path(str(tmp_path / "devsense-php-ls"), PlatformUtils.get_platform_id())
        assert result == expected
        assert len(commands) == 1
        assert commands[0] == ["npm", "install", "--prefix", "./", "devsense-php-ls@1.0.19197"]
        assert DEFAULT_DEVSENSE_PHP_LS_VERSION == "1.0.19197"


class TestDevsensePHPLanguageServer:
    def _server_without_init(self, settings: dict | None = None) -> DevsensePHPLanguageServer:
        server = DevsensePHPLanguageServer.__new__(DevsensePHPLanguageServer)
        server._custom_settings = _custom_settings(settings)
        return server

    def test_initialization_options_are_empty_without_license(self, monkeypatch) -> None:
        monkeypatch.delenv("DEVSENSE_PHP_LS_LICENSE", raising=False)

        params = self._server_without_init()._create_base_initialize_params()

        assert params["initializationOptions"] == {}

    def test_license_and_php_version_are_forwarded(self, monkeypatch) -> None:
        monkeypatch.setenv("DEVSENSE_PHP_LS_LICENSE", "license-token")

        params = self._server_without_init({"php_version": "8.3"})._create_base_initialize_params()

        assert params["initializationOptions"] == {"0": "license-token", "php.version": "8.3"}
        assert params["capabilities"]["textDocument"]["hover"]["contentFormat"] == ["markdown", "plaintext"]


def test_devsense_registry_is_experimental_and_uses_php_extensions() -> None:
    language_id = LanguageServerId.PHP_DEVSENSE

    assert language_id.is_experimental()
    matcher = language_id.get_source_fn_matcher()
    assert matcher.is_relevant_filename("index.php")
    assert matcher.is_relevant_filename("template.phtml")
    assert language_id.get_ls_class() is DevsensePHPLanguageServer
