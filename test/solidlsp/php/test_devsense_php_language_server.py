from pathlib import Path
from unittest.mock import patch

from solidlsp.language_servers.devsense_php_language_server import (
    DEFAULT_DEVSENSE_PHP_LS_VERSION,
    DevsensePHPLanguageServer,
)
from solidlsp.ls_config import LanguageServerId
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

    def test_system_path_is_preferred(self, tmp_path: Path) -> None:
        provider = DevsensePHPLanguageServer.DependencyProvider(_custom_settings(), str(tmp_path))

        with patch(
            "solidlsp.language_servers.devsense_php_language_server.shutil.which", return_value="/usr/local/bin/devsense-php-ls"
        ) as which:
            assert provider._get_or_install_core_dependency() == "/usr/local/bin/devsense-php-ls"
            which.assert_called_once_with("devsense-php-ls")

    def test_managed_install_uses_pinned_npm_package(self, tmp_path: Path) -> None:
        provider = DevsensePHPLanguageServer.DependencyProvider(_custom_settings(), str(tmp_path))
        installed = tmp_path / "devsense-php-ls" / "node_modules" / ".bin" / "devsense-php-ls"
        commands: list[str | list[str]] = []

        def fake_install(target_dir: str) -> dict[str, str]:
            installed.parent.mkdir(parents=True)
            installed.touch()
            return {"devsense-php-ls": str(installed)}

        def fake_which(name: str) -> str | None:
            return None if name == "devsense-php-ls" else f"/usr/bin/{name}"

        with (
            patch("solidlsp.language_servers.devsense_php_language_server.shutil.which", side_effect=fake_which),
            patch(
                "solidlsp.language_servers.devsense_php_language_server.RuntimeDependencyCollection._run_command",
                side_effect=lambda command, cwd: commands.append(command),
            ),
            patch("solidlsp.language_servers.devsense_php_language_server.RuntimeDependencyCollection.install", side_effect=fake_install),
        ):
            result = provider._get_or_install_core_dependency()

        assert result == str(installed)
        assert commands == []
        # The default remains pinned and the target is versioned through the provider's install layout.
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
