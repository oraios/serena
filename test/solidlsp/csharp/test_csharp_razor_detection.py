import os
from unittest.mock import Mock, patch

import pytest

from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings


@pytest.fixture
def mock_logger():
    return Mock(spec=LanguageServerLogger)


@pytest.fixture
def mock_config():
    cfg = Mock(spec=LanguageServerConfig)
    cfg.ignored_paths = []
    return cfg


@pytest.fixture
def settings():
    s = SolidLSPSettings()
    s.tool_timeout = 120  # type: ignore[attr-defined]
    return s


def _write_basic_project(ws):
    (ws / "TestProject.csproj").write_text(
        "<Project Sdk='Microsoft.NET.Sdk'><PropertyGroup><TargetFramework>net9.0</TargetFramework></PropertyGroup></Project>"
    )


def _build_server(mock_config, mock_logger, settings, ws):
    with (
        patch("solidlsp.language_servers.csharp_language_server.CSharpLanguageServer._ensure_server_installed") as m_ensure,
        patch("solidlsp.language_servers.csharp_language_server.CSharpLanguageServer._start_server"),
    ):
        m_ensure.return_value = ("/usr/bin/dotnet", "/path/to/server.dll")
        return CSharpLanguageServer(mock_config, mock_logger, str(ws), settings)


def test_auto_disables_when_no_razor_files(tmp_path, mock_logger, mock_config, settings):
    ws = tmp_path / "ws"
    ws.mkdir()
    _write_basic_project(ws)
    with patch.dict(os.environ, {}, clear=True):
        server = _build_server(mock_config, mock_logger, settings, ws)
        _ = server._get_initialize_params()
        assert server._razor_disabled is True


def test_auto_keeps_enabled_when_razor_present(tmp_path, mock_logger, mock_config, settings):
    ws = tmp_path / "ws"
    ws.mkdir()
    _write_basic_project(ws)
    (ws / "Index.razor").write_text("<h1>Hello</h1>")
    with patch.dict(os.environ, {}, clear=True):
        server = _build_server(mock_config, mock_logger, settings, ws)
        _ = server._get_initialize_params()
        assert server._razor_disabled is False


def test_force_disable_env(tmp_path, mock_logger, mock_config, settings):
    ws = tmp_path / "ws"
    ws.mkdir()
    _write_basic_project(ws)
    (ws / "Index.razor").write_text("<h1>Hello</h1>")
    with patch.dict(os.environ, {"CSHARP_LS_DISABLE_RAZOR": "1"}, clear=True):
        server = _build_server(mock_config, mock_logger, settings, ws)
        _ = server._get_initialize_params()
        assert server._razor_disabled is True


def test_force_enable_env(tmp_path, mock_logger, mock_config, settings):
    ws = tmp_path / "ws"
    ws.mkdir()
    _write_basic_project(ws)
    with patch.dict(os.environ, {"CSHARP_LS_FORCE_ENABLE_RAZOR": "1"}, clear=True):
        server = _build_server(mock_config, mock_logger, settings, ws)
        _ = server._get_initialize_params()
        assert server._razor_disabled is False
