import time
from unittest.mock import Mock, patch

import pytest

from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings


@pytest.fixture
def mock_logger():
    return Mock(spec=LanguageServerLogger)


@pytest.fixture
def mock_config():
    cfg = LanguageServerConfig(code_language=Language.CSHARP)
    return cfg


@pytest.fixture
def mock_settings(tmp_path):
    s = SolidLSPSettings()
    # attach a tool_timeout used by tests (not part of dataclass normally)
    return s


class DummySend:
    def __init__(self, result=None):
        self._result = result or []

    def workspace_symbol(self, params):
        return self._result


class DummyServer:
    def __init__(self, result=None):
        self.send = DummySend(result=result)

    def is_running(self):
        return True


def _build_server(tmp_path, mock_logger, mock_config, mock_settings):
    # Patch heavy installation & parent init
    with patch('solidlsp.language_servers.csharp_language_server.CSharpLanguageServer._ensure_server_installed') as mock_ensure:
        mock_ensure.return_value = (str(tmp_path / 'dotnet'), str(tmp_path / 'server.dll'))
        (tmp_path / 'dotnet').write_text('')
        (tmp_path / 'server.dll').write_text('')
    with patch('solidlsp.language_servers.csharp_language_server.SolidLanguageServer.__init__') as mock_super_init:
        mock_super_init.return_value = None
        server = CSharpLanguageServer(mock_config, mock_logger, str(tmp_path), mock_settings)
        server.logger = mock_logger  # inject logger since base __init__ is patched out
        return server


def test_probe_readiness_sets_event(tmp_path, mock_logger, mock_config, mock_settings):
    server = _build_server(tmp_path, mock_logger, mock_config, mock_settings)
    # Attach dummy server object for probe
    server.server = DummyServer(result=[])  # type: ignore[attr-defined]
    assert not server.is_ready()
    # Invoke wait logic (internal polling) - should mark ready via probe_success
    server._get_wait_time_for_cross_file_referencing()
    assert server.is_ready()
    assert server._ready_reason in {"probe_success", "progress_empty"}


def test_fallback_readiness(tmp_path, mock_logger, mock_config, mock_settings):
    server = _build_server(tmp_path, mock_logger, mock_config, mock_settings)
    # Original fallback thread may already be sleeping with default value; invoke manually
    server._readiness_fallback_seconds = 0
    assert not server.is_ready()
    server._fallback_readiness_timer()
    assert server.is_ready()
    assert server._ready_reason == 'fallback'


def test_progress_quiet_triggers_readiness(tmp_path, mock_logger, mock_config, mock_settings):
    server = _build_server(tmp_path, mock_logger, mock_config, mock_settings)
    server.server = DummyServer(result=[])  # type: ignore[attr-defined]
    server._progress_quiet_seconds = 0  # minimal quiet time
    # Simulate active progress operation
    server.progress_operations['tok'] = {"start_time": time.time(), "last_update": time.time(), "type": "indexing", "title": "Index"}
    assert not server.is_ready()
    # End operation
    del server.progress_operations['tok']
    # Force quiet period
    server._last_progress_activity = time.time() - 0.1
    server._get_wait_time_for_cross_file_referencing()
    assert server.is_ready()
    assert server._ready_reason in {"progress_empty", "probe_success"}


def test_capability_snapshot_supports(tmp_path, mock_logger, mock_config, mock_settings):
    server = _build_server(tmp_path, mock_logger, mock_config, mock_settings)
    # Simulate recording capabilities
    sample_caps = {
        "definitionProvider": True,
        "referencesProvider": True,
        "workspace": {"workspaceFolders": True},
        "textDocument": {"completion": {"completionItem": {"snippetSupport": True}}},
    }
    server._record_capabilities(sample_caps)  # type: ignore[attr-defined]
    assert server.supports("definitionProvider")
    assert server.supports("workspace.workspaceFolders")
    assert server.supports("textDocument.completion.completionItem.snippetSupport")
    assert not server.supports("nonexistent.feature.flag")
