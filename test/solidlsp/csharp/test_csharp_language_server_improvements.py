"""
Tests for C# Language Server improvements including heartbeat, progress tracking, and error handling.
"""

import sys
import threading
import time
from unittest.mock import Mock, patch

import pytest

from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings


@pytest.fixture
def mock_logger():
    """Create a mock logger for testing."""
    return Mock(spec=LanguageServerLogger)


@pytest.fixture
def mock_config():
    """Create a mock configuration for testing."""
    return Mock(spec=LanguageServerConfig)


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    real = SolidLSPSettings()
    real.tool_timeout = 240  # type: ignore[attr-defined]
    return real


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace with C# files."""
    workspace = tmp_path / "test_workspace"
    workspace.mkdir()

    # Create a simple .csproj file
    csproj_content = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net9.0</TargetFramework>
  </PropertyGroup>
</Project>"""
    (workspace / "TestProject.csproj").write_text(csproj_content)

    # Create a simple C# file
    cs_content = """using System;

namespace TestProject
{
    public class Program
    {
        public static void Main(string[] args)
        {
            Console.WriteLine("Hello World!");
        }
    }
}"""
    (workspace / "Program.cs").write_text(cs_content)

    return str(workspace)


class TestCSharpLanguageServerImprovements:
    """Test class for C# Language Server improvements (heartbeat removed)."""

    def test_environment_variable_setup(self, mock_logger, mock_config, mock_settings, temp_workspace):
        """Test that environment variables are properly set for the language server process."""
        with patch("solidlsp.language_servers.csharp_language_server.CSharpLanguageServer._ensure_server_installed") as mock_ensure:
            mock_ensure.return_value = ("/usr/bin/dotnet", "/path/to/server.dll")
            with patch("solidlsp.language_servers.csharp_language_server.SolidLanguageServer.__init__"):
                server = CSharpLanguageServer(mock_config, mock_logger, temp_workspace, mock_settings)
                server.logger = mock_logger  # Inject logger since base __init__ is patched out
                # Check that environment variables are set
                assert hasattr(server, "dotnet_dir")
                assert server.dotnet_dir.replace("\\", "/") == "/usr/bin"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific path length warning")
    def test_windows_path_length_warning(self, mock_logger, mock_config, mock_settings, temp_workspace):
        """Test Windows path length warning functionality."""
        with patch("solidlsp.language_servers.csharp_language_server.CSharpLanguageServer._ensure_server_installed") as mock_ensure:
            mock_ensure.return_value = ("/usr/bin/dotnet", "/path/to/server.dll")
            with patch("solidlsp.language_servers.csharp_language_server.SolidLanguageServer.__init__"):
                with patch("platform.system") as mock_platform:
                    mock_platform.return_value = "Windows"
                    with patch.object(CSharpLanguageServer, "ls_resources_dir") as mock_resources_dir:
                        long_path = "C:\\" + "very_long_directory_name\\" * 10 + "resources"
                        mock_resources_dir.return_value = long_path
                        CSharpLanguageServer(mock_config, mock_logger, temp_workspace, mock_settings)
                        warning_calls = [call for call in mock_logger.log.call_args_list if "WARNING: Resource directory path" in str(call)]
                        assert len(warning_calls) > 0

    def test_readiness_event_present(self, mock_logger, mock_config, mock_settings, temp_workspace):
        """Ensure readiness-related structures exist (replacement for legacy heartbeat)."""
        with patch("solidlsp.language_servers.csharp_language_server.CSharpLanguageServer._ensure_server_installed") as mock_ensure:
            mock_ensure.return_value = ("/usr/bin/dotnet", "/path/to/server.dll")
            with patch("solidlsp.language_servers.csharp_language_server.SolidLanguageServer.__init__"):
                server = CSharpLanguageServer(mock_config, mock_logger, temp_workspace, mock_settings)
                assert hasattr(server, "_ready_event")
                assert not server._ready_event.is_set()

    def test_progress_tracking(self, mock_logger, mock_config, mock_settings, temp_workspace):
        """Test progress tracking and telemetry functionality."""
        with patch("solidlsp.language_servers.csharp_language_server.CSharpLanguageServer._ensure_server_installed") as mock_ensure:
            mock_ensure.return_value = ("/usr/bin/dotnet", "/path/to/server.dll")
            with patch("solidlsp.language_servers.csharp_language_server.SolidLanguageServer.__init__"):
                server = CSharpLanguageServer(mock_config, mock_logger, temp_workspace, mock_settings)
                server.logger = mock_logger
                assert hasattr(server, "progress_operations")
                assert isinstance(server.progress_operations, dict)
                with patch.object(server, "logger", mock_logger):
                    begin_params = {
                        "token": "test_token",
                        "value": {"kind": "begin", "title": "Indexing project", "message": "Starting indexing", "percentage": 0},
                    }
                    token = begin_params["token"]
                    value = begin_params["value"]
                    server.progress_operations[token] = {
                        "title": value.get("title", ""),
                        "start_time": time.time(),
                        "type": "indexing",
                        "last_update": time.time(),
                    }
                    assert token in server.progress_operations
                    assert server.progress_operations[token]["type"] == "indexing"

    def test_enhanced_error_handling(self, mock_logger, mock_config, mock_settings, temp_workspace):
        """Test enhanced error handling in server setup."""
        with patch("solidlsp.language_servers.csharp_language_server.CSharpLanguageServer._get_runtime_id") as mock_runtime_id:
            mock_runtime_id.side_effect = Exception("Platform detection failed")
            with pytest.raises(SolidLSPException) as exc_info:
                CSharpLanguageServer._ensure_server_installed(mock_logger, mock_config, mock_settings)
            assert "Failed to set up C# language server" in str(exc_info.value)
            error_calls = [call for call in mock_logger.log.call_args_list if "ERROR setting up C# language server" in str(call)]
            assert len(error_calls) > 0

    def test_path_validation(self, mock_logger, mock_config, mock_settings):
        """Test path validation in server setup."""
        with patch("solidlsp.language_servers.csharp_language_server.CSharpLanguageServer._get_runtime_id") as mock_runtime_id:
            mock_runtime_id.return_value = "win-x64"
            with patch("solidlsp.language_servers.csharp_language_server.CSharpLanguageServer._get_runtime_dependencies") as mock_deps:
                mock_lang_dep = Mock()
                mock_runtime_dep = Mock()
                mock_deps.return_value = (mock_lang_dep, mock_runtime_dep)
                with patch("solidlsp.language_servers.csharp_language_server.CSharpLanguageServer._ensure_dotnet_runtime") as mock_dotnet:
                    mock_dotnet.return_value = "/nonexistent/dotnet"
                    with patch(
                        "solidlsp.language_servers.csharp_language_server.CSharpLanguageServer._ensure_language_server"
                    ) as mock_server:
                        mock_server.return_value = "/nonexistent/server.dll"
                        with pytest.raises(SolidLSPException) as exc_info:
                            CSharpLanguageServer._ensure_server_installed(mock_logger, mock_config, mock_settings)
                        assert ".NET runtime path" in str(exc_info.value) and "does not exist" in str(exc_info.value)

    def test_timeout_extension_logic(self, mock_logger, mock_config, mock_settings, temp_workspace):
        """Test timeout extension for heavy operations."""
        with patch("solidlsp.language_servers.csharp_language_server.CSharpLanguageServer._ensure_server_installed") as mock_ensure:
            mock_ensure.return_value = ("/usr/bin/dotnet", "/path/to/server.dll")
            with patch("solidlsp.language_servers.csharp_language_server.SolidLanguageServer.__init__"):
                server = CSharpLanguageServer(mock_config, mock_logger, temp_workspace, mock_settings)
                server.logger = mock_logger
                server.server = Mock()
                server.solidlsp_settings = mock_settings
                future_mock = Mock()
                future_mock.result.return_value = {"result": "success"}
                server.server.send_request_async.return_value = future_mock
                _ = server._send_request_with_timeout("textDocument/codeAction", {}, timeout=30)
                future_mock.result.assert_called_once()
                call_args = future_mock.result.call_args
                assert call_args[1]["timeout"] >= 60

    def test_initialization_complete_tracking(self, mock_logger, mock_config, mock_settings, temp_workspace):
        """Test that initialization completion is properly tracked."""
        with patch("solidlsp.language_servers.csharp_language_server.CSharpLanguageServer._ensure_server_installed") as mock_ensure:
            mock_ensure.return_value = ("/usr/bin/dotnet", "/path/to/server.dll")
            with patch("solidlsp.language_servers.csharp_language_server.SolidLanguageServer.__init__"):
                server = CSharpLanguageServer(mock_config, mock_logger, temp_workspace, mock_settings)
                assert hasattr(server, "initialization_complete")
                assert isinstance(server.initialization_complete, threading.Event)
                assert not server.initialization_complete.is_set()

    def test_shutdown_cleanup(self, mock_logger, mock_config, mock_settings, temp_workspace):
        """Test proper cleanup during shutdown (without heartbeat)."""
        with patch("solidlsp.language_servers.csharp_language_server.CSharpLanguageServer._ensure_server_installed") as mock_ensure:
            mock_ensure.return_value = ("/usr/bin/dotnet", "/path/to/server.dll")
            with patch("solidlsp.language_servers.csharp_language_server.SolidLanguageServer.__init__"):
                server = CSharpLanguageServer(mock_config, mock_logger, temp_workspace, mock_settings)
                server.logger = mock_logger
                server.shutdown()
                assert server.is_shutdown is True


class TestCSharpLanguageServerRegressionSuite:
    """Regression tests to ensure improvements don't break existing functionality."""

    @pytest.fixture
    def mock_dependencies(self):
        """Setup common mock dependencies."""
        with patch("solidlsp.language_servers.csharp_language_server.CSharpLanguageServer._ensure_server_installed") as mock_ensure:
            mock_ensure.return_value = ("/usr/bin/dotnet", "/path/to/server.dll")
            with patch("solidlsp.language_servers.csharp_language_server.SolidLanguageServer.__init__") as mock_super_init:
                yield mock_ensure, mock_super_init

    def test_existing_initialization_flow(self, mock_dependencies, tmp_path):
        """Test that existing initialization flow still works (basic instantiation)."""
        _mock_ensure, mock_super_init = mock_dependencies
        workspace = tmp_path / "simple_ws"
        workspace.mkdir()

        mock_logger = Mock(spec=LanguageServerLogger)
        mock_config = Mock(spec=LanguageServerConfig)
        settings = SolidLSPSettings()
        settings.tool_timeout = 240  # type: ignore[attr-defined]

        server = CSharpLanguageServer(mock_config, mock_logger, str(workspace), settings)
        server.logger = mock_logger  # inject since base __init__ patched
        mock_super_init.assert_called_once()
        # Heartbeat removed: ensure progress tracking still present
        assert hasattr(server, "progress_operations")

    def test_solution_discovery_unchanged(self, mock_dependencies, tmp_path):
        """Test that solution/project discovery logic remains unchanged."""
        workspace = tmp_path / "test_workspace"
        workspace.mkdir()

        # Create solution file
        sln_content = """Microsoft Visual Studio Solution File, Format Version 12.00"""
        (workspace / "TestSolution.sln").write_text(sln_content)

        from solidlsp.language_servers.csharp_language_server import find_solution_or_project_file

        result = find_solution_or_project_file(str(workspace))
        assert result is not None
        assert result.endswith("TestSolution.sln")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
