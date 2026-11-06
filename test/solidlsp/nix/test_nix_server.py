"""Unit tests for nixd launch and configuration handling."""

import json
import re
import time
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock, call, patch

import pytest

from solidlsp.language_servers.nixd_ls import NixLanguageServer, _utf16_column_to_index, _utf16_offsets
from solidlsp.ls import DocumentSymbols, SolidLanguageServer
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


def test_default_nixd_settings_use_schema_valid_options_map() -> None:
    settings = NixLanguageServer._load_nixd_settings(SolidLSPSettings.CustomLSSettings({}))

    assert settings == {
        "nixpkgs": {"expr": "import <nixpkgs> { }"},
        "formatting": {"command": ["nixpkgs-fmt"]},
        "options": {},
    }
    assert NixLanguageServer._get_workspace_configuration({"items": [{"section": "nixd.options"}]}, settings) == [{}]


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


def test_hover_retries_transient_empty_response(tmp_path: Path) -> None:
    server = _make_server(tmp_path)
    hover_result = {"contents": {"kind": "markdown", "value": "makeGreeting"}}
    cast(Any, server.server.send.hover).side_effect = [None, hover_result]
    file_buffer = Mock(uri="file:///tmp/default.nix")

    with patch("solidlsp.language_servers.nixd_ls.sleep") as wait:
        result = server._request_hover(file_buffer, 12, 5)

    expected_request = {
        "textDocument": {"uri": "file:///tmp/default.nix"},
        "position": {"line": 12, "character": 5},
    }
    assert result == hover_result
    assert cast(Any, server.server.send.hover).call_args_list == [call(expected_request), call(expected_request)]
    wait.assert_called_once_with(NixLanguageServer._HOVER_RETRY_DELAY_SECONDS)


def test_hover_stops_after_bounded_retries(tmp_path: Path) -> None:
    server = _make_server(tmp_path)
    cast(Any, server.server.send.hover).return_value = None
    file_buffer = Mock(uri="file:///tmp/default.nix")

    with patch("solidlsp.language_servers.nixd_ls.sleep") as wait:
        result = server._request_hover(file_buffer, 12, 5)

    assert result is None
    assert cast(Any, server.server.send.hover).call_count == NixLanguageServer._HOVER_RETRY_COUNT + 1
    assert wait.call_count == NixLanguageServer._HOVER_RETRY_COUNT
    wait.assert_called_with(NixLanguageServer._HOVER_RETRY_DELAY_SECONDS)


def _symbol_for(source: str, range_text: str, name: str) -> dict[str, Any]:
    """A hand-built nixd-style symbol whose range covers `range_text` and whose selectionRange covers its leading `name`."""
    assert range_text.startswith(name)
    start = source.index(range_text)

    def position(offset: int) -> dict[str, int]:
        before = source[:offset]
        column_text = before[before.rfind("\n") + 1 :]
        return {"line": before.count("\n"), "character": len(column_text.encode("utf-16-le")) // 2}

    return {
        "range": {"start": position(start), "end": position(start + len(range_text))},
        "selectionRange": {"start": position(start), "end": position(start + len(name))},
    }


@pytest.mark.parametrize(
    ("source", "range_text", "name", "is_binding"),
    [
        ("{ plain = 1; }", "plain = 1", "plain", True),
        ('{ "é" = { a = 1; }; }', '"é" = { a = 1; }', '"é"', True),
        ('{ "quoted" = 1; }', '"quoted" = 1', '"quoted"', True),
        ('{ ${"dyn"} = 1; }', '${"dyn"} = 1', '${"dyn"}', True),
        ("{ split\n  = 1; }", "split\n  = 1", "split", True),
        ("{ c /* comment */ = 1; }", "c /* comment */ = 1", "c", True),
        ("{ c # comment\n  = 1; }", "c # comment\n  = 1", "c", True),
        ("{ tight=1; }", "tight=1", "tight", True),
        ("{ s\n  =\n  { e = 5; }; }", "s\n  =\n  { e = 5; }", "s", True),
        ('{ "🚀🚀" = { a = 1; }; }', '"🚀🚀" = { a = 1; }', '"🚀🚀"', True),
        ("{ f = x: x; }", "x: x", "x", False),
        ("{ inherit (b) toString; }", "toString", "toString", False),
        ("{ same = a == b; }", "a == b", "a", False),
        # an `=` inside a comment, or a second comment further on, must not make a lambda look like a binding
        ("{ f = x # = note\n: x; }", "x # = note\n: x", "x", False),
        ("{ f = x /* first */ : let y /* second */ = 1; in y; }", "x /* first */ : let y /* second */ = 1; in y", "x", False),
    ],
)
def test_is_nix_binding(source: str, range_text: str, name: str, is_binding: bool) -> None:
    symbol = _symbol_for(source, range_text, name)
    assert NixLanguageServer._is_nix_binding(cast(Any, symbol), source.split("\n")) is is_binding


def test_is_nix_binding_does_not_backtrack_through_long_comments() -> None:
    # A lambda with a comment before its `:` used to take time exponential in the comment's `#` count: each
    # further `#` doubled it, and 25 took over a second. The comment is kept short so that a regression fails
    # here instead of hanging the test run.
    source = "{ pkgs, ... }\n" + "#" * 25 + "\n: { a = 1; }"
    symbol = _symbol_for(source, source, "{ pkgs, ... }")
    started = time.monotonic()
    assert NixLanguageServer._is_nix_binding(cast(Any, symbol), source.split("\n")) is False
    assert time.monotonic() - started < 0.1


@pytest.mark.parametrize("prefix", ["", "\U0001f680"])
def test_utf16_columns_of_a_long_line_are_converted_quickly(prefix: str) -> None:
    # Two conversions run per symbol. Walking the line from its start for each one took minutes on a generated
    # one-line file; a line of 20k characters keeps a regression to seconds rather than hanging the run.
    line = prefix + "{ " + " ".join(f"a{i} = {i};" for i in range(2000)) + " }"
    started = time.monotonic()
    indices = [_utf16_column_to_index(line, column) for column in range(0, len(line), 7)]
    assert time.monotonic() - started < 0.5
    assert indices[1] == (7 if not prefix else 6)


def test_document_symbols_of_a_long_line_are_built_quickly(monkeypatch: pytest.MonkeyPatch) -> None:
    # A generated one-line file with thousands of bindings: the line must be split once per document, not once
    # per symbol, which took 2 s here. The leading astral character keeps the line off the ASCII fast path, and
    # every binding after it must still get its semicolon.
    prefix = '{ _ = "\U0001f680"; '
    pieces, symbols, index = [prefix], [], len(prefix)
    for i in range(20000):
        binding, name = f"a{i} = {i}", f"a{i}"
        column = index + 1  # the astral character before it takes two UTF-16 units
        range_ = {"start": {"line": 0, "character": column}, "end": {"line": 0, "character": column + len(binding)}}
        selection = {"start": range_["start"], "end": {"line": 0, "character": column + len(name)}}
        symbols.append({"name": name, "range": range_, "selectionRange": selection, "location": {"range": range_}})
        pieces.append(binding + "; ")
        index += len(binding) + 2
    line = "".join(pieces) + "}"
    buffer = Mock(contents=line, split_lines=lambda: line.split("\n"))
    monkeypatch.setattr(
        SolidLanguageServer, "_build_document_symbols_from_raw_symbols", lambda self, path, file_buffer: DocumentSymbols(symbols)
    )
    ls = NixLanguageServer.__new__(NixLanguageServer)
    started = time.monotonic()
    result = ls._build_document_symbols_from_raw_symbols("generated.nix", buffer)
    assert time.monotonic() - started < 1.0
    assert all(
        symbol["range"]["end"]["character"] == original["range"]["end"]["character"] + 1
        for symbol, original in zip(result.root_symbols, symbols, strict=True)
    )
    assert len({id(symbol["body"]._lines) for symbol in result.root_symbols}) == 1, "one copy of the lines per document"
    assert _utf16_offsets.cache_info().currsize == 0, "the line's offsets table is not kept after the build"
