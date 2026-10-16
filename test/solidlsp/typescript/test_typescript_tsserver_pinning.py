"""An untrusted project's own tsserver must not be loaded by typescript-language-server."""

from pathlib import Path

import pytest

from solidlsp.language_servers.typescript_language_server import TypeScriptLanguageServer
from solidlsp.ls_config import LanguageServerConfig, LanguageServerId
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.settings import SolidLSPSettings


def _create_server(resources_dir: Path, is_project_trusted: bool, custom_settings: dict | None = None) -> TypeScriptLanguageServer:
    """Creates a server instance without starting it, to inspect the initialize params it would send."""
    server = object.__new__(TypeScriptLanguageServer)
    server.config = LanguageServerConfig(ls_id=LanguageServerId.TYPESCRIPT, is_project_trusted=is_project_trusted)
    server._custom_settings = SolidLSPSettings.CustomLSSettings(custom_settings or {})
    server._ls_resources_dir = str(resources_dir)
    server.repository_root_path = str(resources_dir / "project")
    return server


def _create_managed_installation(resources_dir: Path, install_dirname: str = "ts-lsp") -> Path:
    tsdk_path = resources_dir / install_dirname / "node_modules" / "typescript" / "lib"
    tsdk_path.mkdir(parents=True)
    (tsdk_path / "tsserver.js").write_text("", encoding="utf-8")
    return tsdk_path


def test_untrusted_project_pins_managed_tsserver(tmp_path: Path) -> None:
    tsdk_path = _create_managed_installation(tmp_path)
    server = _create_server(tmp_path, is_project_trusted=False)

    initialization_options = server._create_base_initialize_params()["initializationOptions"]

    assert initialization_options["tsserver"] == {"path": str(tsdk_path)}
    # the pin must not displace the options that were already being sent
    assert initialization_options["disableAutomaticTypingAcquisition"] is True


def test_untrusted_project_pins_tsserver_of_requested_versions(tmp_path: Path) -> None:
    # versions deliberately differing from DEFAULT_TYPESCRIPT_VERSION/DEFAULT_TYPESCRIPT_LANGUAGE_SERVER_VERSION,
    # which are installed into the legacy unversioned directory
    custom_settings = {"typescript_version": "5.8.2", "typescript_language_server_version": "5.0.0"}
    tsdk_path = _create_managed_installation(tmp_path, install_dirname="ts-lsp-5.8.2-5.0.0")
    server = _create_server(tmp_path, is_project_trusted=False, custom_settings=custom_settings)

    initialization_options = server._create_base_initialize_params()["initializationOptions"]

    assert initialization_options["tsserver"] == {"path": str(tsdk_path)}


def test_untrusted_project_without_managed_installation_fails(tmp_path: Path) -> None:
    """A missing managed installation must fail loudly; falling back would load the project's own tsserver."""
    server = _create_server(tmp_path, is_project_trusted=False)

    with pytest.raises(SolidLSPException, match="Cannot pin tsserver"):
        server._create_base_initialize_params()


def test_trusted_project_keeps_workspace_typescript(tmp_path: Path) -> None:
    """The established behaviour of honouring the project's own TypeScript is retained for trusted projects."""
    _create_managed_installation(tmp_path)
    server = _create_server(tmp_path, is_project_trusted=True)

    initialization_options = server._create_base_initialize_params()["initializationOptions"]

    assert "tsserver" not in initialization_options
    assert initialization_options["disableAutomaticTypingAcquisition"] is True
