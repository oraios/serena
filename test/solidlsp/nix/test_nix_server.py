"""Unit tests for nixd launch and configuration handling."""

import json
import re
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest

from solidlsp.language_servers.nixd_ls import NixLanguageServer
from solidlsp.ls_config import LanguageServerConfig, LanguageServerId
from solidlsp.settings import SolidLSPSettings


def _make_provider(
    tmp_path: Path,
    custom_settings: dict[str, Any] | None = None,
) -> NixLanguageServer.DependencyProvider:
    return NixLanguageServer.DependencyProvider(
        SolidLSPSettings.CustomLSSettings(custom_settings or {}),
        str(tmp_path),
    )


def _make_server(
    tmp_path: Path,
    custom_settings: dict[str, Any] | None = None,
) -> NixLanguageServer:
    settings = SolidLSPSettings(
        solidlsp_dir=str(tmp_path / "global"),
        project_data_path=str(tmp_path / "project"),
        ls_specific_settings={LanguageServerId.NIX: custom_settings or {}},
    )
    server_interface = Mock()
    with patch.object(NixLanguageServer, "_create_language_server_interface", return_value=server_interface):
        return NixLanguageServer(
            LanguageServerConfig(ls_id=LanguageServerId.NIX),
            str(tmp_path),
            settings,
        )


def test_ls_path_bypasses_managed_dependency_resolution(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path, {"ls_path": "/custom/nixd-project"})

    with patch.object(
        provider,
        "_get_or_install_core_dependency",
        side_effect=AssertionError("managed dependency resolution must not run when ls_path is configured"),
    ) as managed_resolution:
        assert provider.create_launch_command() == ["/custom/nixd-project"]

    managed_resolution.assert_not_called()


def test_default_launch_command_uses_managed_dependency_resolution(tmp_path: Path) -> None:
    provider = _make_provider(tmp_path)

    with patch.object(provider, "_get_or_install_core_dependency", return_value="/usr/bin/nixd") as managed_resolution:
        assert provider.create_launch_command() == ["/usr/bin/nixd"]

    managed_resolution.assert_called_once_with()


def test_default_nixd_settings_preserve_existing_behavior() -> None:
    assert NixLanguageServer._load_nixd_settings(SolidLSPSettings.CustomLSSettings({})) == {
        "nixpkgs": {"expr": "import <nixpkgs> { }"},
        "formatting": {"command": ["nixpkgs-fmt"]},
        "options": {
            "enable": True,
            "target": {"installable": ""},
        },
    }


def test_config_path_loads_bare_nixd_settings_object(tmp_path: Path) -> None:
    config_path = tmp_path / "nixd-settings.json"
    expected = {
        "formatting": {"command": ["alejandra"]},
        "options": {"nixos": {"expr": "flake.nixosConfigurations.host.options"}},
    }
    config_path.write_text(json.dumps(expected), encoding="utf-8")

    settings = SolidLSPSettings.CustomLSSettings({"config_path": str(config_path)})

    assert NixLanguageServer._load_nixd_settings(settings) == expected


@pytest.mark.parametrize("config_path", ["", "relative/nixd-settings.json"])
def test_config_path_must_be_non_empty_and_absolute(config_path: str) -> None:
    settings = SolidLSPSettings.CustomLSSettings({"config_path": config_path})

    with pytest.raises(ValueError, match="config_path must be"):
        NixLanguageServer._load_nixd_settings(settings)


def test_missing_config_path_reports_file(tmp_path: Path) -> None:
    config_path = tmp_path / "missing.json"
    settings = SolidLSPSettings.CustomLSSettings({"config_path": str(config_path)})

    with pytest.raises(RuntimeError, match=re.escape(f"Failed to read nixd configuration file '{config_path}'")):
        NixLanguageServer._load_nixd_settings(settings)


def test_malformed_config_reports_json_location(tmp_path: Path) -> None:
    config_path = tmp_path / "malformed.json"
    config_path.write_text('{"formatting":', encoding="utf-8")
    settings = SolidLSPSettings.CustomLSSettings({"config_path": str(config_path)})

    with pytest.raises(ValueError, match=r"Invalid JSON.*line 1, column 15"):
        NixLanguageServer._load_nixd_settings(settings)


@pytest.mark.parametrize("document", [[], None, "nixd"])
def test_config_document_must_be_an_object(tmp_path: Path, document: object) -> None:
    config_path = tmp_path / "nixd-settings.json"
    config_path.write_text(json.dumps(document), encoding="utf-8")
    settings = SolidLSPSettings.CustomLSSettings({"config_path": str(config_path)})

    with pytest.raises(ValueError, match="expected a JSON object"):
        NixLanguageServer._load_nixd_settings(settings)


def test_workspace_configuration_preserves_order_and_resolves_nested_sections() -> None:
    settings = {
        "formatting": {"command": ["alejandra"]},
        "options": {"nixos": {"expr": "flake.nixosConfigurations.host.options"}},
    }
    params = {
        "items": [
            {"section": "nixd.options.nixos"},
            {"section": "editor"},
            {"section": "nixd.formatting"},
            {"section": "nixd"},
            {"scopeUri": "file:///workspace"},
            "invalid-item",
        ]
    }

    assert NixLanguageServer._get_workspace_configuration(params, settings) == [
        {"expr": "flake.nixosConfigurations.host.options"},
        {},
        {"command": ["alejandra"]},
        settings,
        {},
        {},
    ]


@pytest.mark.parametrize("params", [None, [], {"items": "invalid"}])
def test_workspace_configuration_rejects_malformed_params(params: object) -> None:
    assert NixLanguageServer._get_workspace_configuration(params, {}) == []


def test_initialization_and_workspace_configuration_share_effective_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "nixd-settings.json"
    config_path.write_text(
        json.dumps(
            {
                "formatting": {"command": ["nixpkgs-fmt"]},
                "options": {"nixos": {"expr": "flake.nixosConfigurations.host.options"}},
            }
        ),
        encoding="utf-8",
    )
    server = _make_server(
        tmp_path,
        {
            "config_path": str(config_path),
            "initializationOptions": {
                "formatting": {"command": ["alejandra"]},
                "diagnostic": {"suppress": ["sema-extra-with"]},
            },
        },
    )

    initialize_params = server._create_initialize_params()
    effective_settings = cast(dict[str, Any], initialize_params.get("initializationOptions"))

    assert effective_settings == {
        "formatting": {"command": ["alejandra"]},
        "options": {"nixos": {"expr": "flake.nixosConfigurations.host.options"}},
        "diagnostic": {"suppress": ["sema-extra-with"]},
    }
    assert server._get_workspace_configuration({"items": [{"section": "nixd"}]}, effective_settings) == [effective_settings]


def test_start_registers_configuration_handler_before_start_and_initialize(tmp_path: Path) -> None:
    server = _make_server(tmp_path)
    events: list[str] = []
    request_handlers: dict[str, Any] = {}

    def on_request(method: str, handler: Any) -> None:
        events.append(f"request:{method}")
        request_handlers[method] = handler

    def initialize(_params: object) -> dict[str, Any]:
        events.append("initialize")
        return {
            "capabilities": {
                "textDocumentSync": 1,
                "definitionProvider": True,
                "documentSymbolProvider": True,
                "referencesProvider": True,
            }
        }

    language_server_interface = cast(Any, server.server)
    language_server_interface.on_request.side_effect = on_request
    language_server_interface.start.side_effect = lambda: events.append("start")
    language_server_interface.send.initialize.side_effect = initialize

    server._start_server()

    assert events.index("request:workspace/configuration") < events.index("start") < events.index("initialize")
    assert request_handlers["workspace/configuration"]({"items": [{"section": "nixd.formatting"}]}) == [{"command": ["nixpkgs-fmt"]}]
