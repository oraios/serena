"""
Simple integration test for C# Language Server improvements
"""

from unittest.mock import Mock, patch


def test_csharp_server_basic_functionality():
    """Basic test to verify the enhanced C# language server works"""
    # Mock the dependencies
    with patch("solidlsp.language_servers.csharp_language_server.CSharpLanguageServer._ensure_server_installed") as mock_ensure:
        mock_ensure.return_value = ("/usr/bin/dotnet", "/path/to/server.dll")
        with patch("solidlsp.language_servers.csharp_language_server.SolidLanguageServer.__init__"):
            from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer
            from solidlsp.ls_config import LanguageServerConfig
            from solidlsp.ls_logger import LanguageServerLogger
            from solidlsp.settings import SolidLSPSettings

            # Create mock objects
            mock_logger = Mock(spec=LanguageServerLogger)
            mock_config = Mock(spec=LanguageServerConfig)
            mock_settings = Mock(spec=SolidLSPSettings)
            mock_settings.tool_timeout = 240

            # Create server instance
            server = CSharpLanguageServer(mock_config, mock_logger, "/tmp/workspace", mock_settings)

            # Verify core tracking attributes exist (heartbeat removed)
            assert hasattr(server, "progress_operations")
            assert hasattr(server, "initialization_complete")
            assert hasattr(server, "_ready_event")

            # Simulate shutdown directly
            server.shutdown()
            assert server.is_shutdown is True


def test_environment_variables_setup():
    """Test that environment variables are properly configured"""
    with patch("solidlsp.language_servers.csharp_language_server.CSharpLanguageServer._ensure_server_installed") as mock_ensure:
        mock_ensure.return_value = ("/usr/bin/dotnet", "/path/to/server.dll")
        with patch("solidlsp.language_servers.csharp_language_server.SolidLanguageServer.__init__") as mock_super:
            from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer
            from solidlsp.ls_config import LanguageServerConfig
            from solidlsp.ls_logger import LanguageServerLogger
            from solidlsp.settings import SolidLSPSettings

            mock_logger = Mock(spec=LanguageServerLogger)
            mock_config = Mock(spec=LanguageServerConfig)
            mock_settings = Mock(spec=SolidLSPSettings)
            mock_settings.tool_timeout = 240

            CSharpLanguageServer(mock_config, mock_logger, "/tmp/workspace", mock_settings)

            # Verify super().__init__ was called with environment
            mock_super.assert_called_once()
            call_args = mock_super.call_args
            launch_info = call_args[0][3]  # ProcessLaunchInfo is the 4th argument

            # Should have environment variables set
            assert hasattr(launch_info, "env") or "env" in call_args[1]


if __name__ == "__main__":
    test_csharp_server_basic_functionality()
    test_environment_variables_setup()
    print("All integration tests passed!")
