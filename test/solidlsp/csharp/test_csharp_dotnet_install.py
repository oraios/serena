"""Tests for C# language server .NET runtime installation using official install scripts."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer
from solidlsp.settings import SolidLSPSettings


@pytest.mark.csharp
class TestDotNetInstallScript:
    """Test .NET runtime installation using Microsoft's official install scripts."""

    @patch("solidlsp.language_servers.csharp_language_server.CSharpLanguageServer.DependencyProvider._ensure_language_server")
    @patch("solidlsp.language_servers.csharp_language_server.platform.system")
    @patch("solidlsp.language_servers.csharp_language_server.subprocess.run")
    @patch("solidlsp.language_servers.csharp_language_server.urllib.request.urlretrieve")
    @patch("solidlsp.language_servers.csharp_language_server.shutil.which")
    def test_install_dotnet_uses_bash_script_on_linux(self, mock_which, mock_urlretrieve, mock_subprocess, mock_platform, mock_ensure_ls):
        """Test that Linux uses bash install script."""
        mock_platform.return_value = "Linux"
        mock_which.return_value = None  # No system dotnet
        mock_ensure_ls.return_value = "/fake/server.dll"

        with tempfile.TemporaryDirectory() as temp_dir:

            def mock_retrieve(url, path):
                # Create the file that urlretrieve would create
                Path(path).touch()
                # Also create the dotnet executable after script download
                if "dotnet-install.sh" in str(path):
                    dotnet_dir = Path(temp_dir) / "dotnet-runtime-10.0"
                    dotnet_dir.mkdir(parents=True, exist_ok=True)
                    dotnet_exe = dotnet_dir / "dotnet"
                    dotnet_exe.touch()
                    dotnet_exe.chmod(0o755)

            mock_urlretrieve.side_effect = mock_retrieve
            mock_subprocess.return_value = Mock(returncode=0, stdout="", stderr="")

            mock_settings = SolidLSPSettings()
            custom_settings = SolidLSPSettings.CustomLSSettings({})

            _ = CSharpLanguageServer.DependencyProvider(
                custom_settings=custom_settings,
                ls_resources_dir=temp_dir,
                solidlsp_settings=mock_settings,
                repository_root_path="/fake/repo",
            )

            # Verify bash script was downloaded
            assert mock_urlretrieve.called
            script_url = mock_urlretrieve.call_args[0][0]
            assert script_url == "https://dot.net/v1/dotnet-install.sh"

    @patch("solidlsp.language_servers.csharp_language_server.CSharpLanguageServer.DependencyProvider._ensure_language_server")
    @patch("solidlsp.language_servers.csharp_language_server.platform.system")
    @patch("solidlsp.language_servers.csharp_language_server.subprocess.run")
    @patch("solidlsp.language_servers.csharp_language_server.urllib.request.urlretrieve")
    @patch("solidlsp.language_servers.csharp_language_server.shutil.which")
    def test_install_dotnet_uses_powershell_script_on_windows(
        self, mock_which, mock_urlretrieve, mock_subprocess, mock_platform, mock_ensure_ls
    ):
        """Test that Windows uses PowerShell install script."""
        mock_platform.return_value = "Windows"
        mock_which.return_value = None  # No system dotnet
        mock_ensure_ls.return_value = "/fake/server.dll"

        with tempfile.TemporaryDirectory() as temp_dir:

            def mock_retrieve(url, path):
                # Create the file that urlretrieve would create
                Path(path).touch()
                # Also create the dotnet executable after script download
                if "dotnet-install.ps1" in str(path):
                    dotnet_dir = Path(temp_dir) / "dotnet-runtime-10.0"
                    dotnet_dir.mkdir(parents=True, exist_ok=True)
                    dotnet_exe = dotnet_dir / "dotnet.exe"
                    dotnet_exe.touch()

            mock_urlretrieve.side_effect = mock_retrieve
            mock_subprocess.return_value = Mock(returncode=0, stdout="", stderr="")

            mock_settings = SolidLSPSettings()
            custom_settings = SolidLSPSettings.CustomLSSettings({})

            _ = CSharpLanguageServer.DependencyProvider(
                custom_settings=custom_settings,
                ls_resources_dir=temp_dir,
                solidlsp_settings=mock_settings,
                repository_root_path="/fake/repo",
            )

            # Verify PowerShell script was downloaded
            assert mock_urlretrieve.called
            script_url = mock_urlretrieve.call_args[0][0]
            assert script_url == "https://dot.net/v1/dotnet-install.ps1"

    def test_uses_system_dotnet_10_if_available(self):
        """Test that system .NET 10 is used if available instead of downloading."""
        from solidlsp.ls_utils import PlatformId

        with patch("solidlsp.language_servers.csharp_language_server.shutil.which") as mock_which:
            with patch("solidlsp.language_servers.csharp_language_server.subprocess.run") as mock_subprocess:
                with patch("solidlsp.language_servers.common.PlatformUtils.get_platform_id") as mock_platform_id:
                    with patch(
                        "solidlsp.language_servers.csharp_language_server.CSharpLanguageServer.DependencyProvider._ensure_language_server"
                    ) as mock_ensure_ls:
                        mock_which.return_value = "/usr/bin/dotnet"
                        mock_ensure_ls.return_value = "/fake/server.dll"
                        mock_platform_id.return_value = PlatformId.LINUX_x64

                        # Mock dotnet --list-runtimes output showing .NET 10
                        mock_result = Mock()
                        mock_result.stdout = "Microsoft.NETCore.App 10.0.1 [/usr/share/dotnet/shared/Microsoft.NETCore.App]"
                        mock_result.returncode = 0
                        mock_subprocess.return_value = mock_result

                        with tempfile.TemporaryDirectory() as temp_dir:
                            mock_settings = SolidLSPSettings()
                            custom_settings = SolidLSPSettings.CustomLSSettings({})

                            dependency_provider = CSharpLanguageServer.DependencyProvider(
                                custom_settings=custom_settings,
                                ls_resources_dir=temp_dir,
                                solidlsp_settings=mock_settings,
                                repository_root_path="/fake/repo",
                            )

                            # Should have used system dotnet
                            assert dependency_provider._dotnet_path == "/usr/bin/dotnet"

    def test_runtime_dependencies_no_longer_include_dotnet_downloads(self):
        """Test that _RUNTIME_DEPENDENCIES no longer includes manual .NET download entries."""
        from solidlsp.language_servers.csharp_language_server import _RUNTIME_DEPENDENCIES

        # Check that DotNetRuntime entries don't exist (we use install script instead)
        dotnet_deps = [dep for dep in _RUNTIME_DEPENDENCIES if dep.id == "DotNetRuntime"]

        # After our changes, there should be no DotNetRuntime entries
        # (we'll use the install script instead)
        assert len(dotnet_deps) == 0, "DotNetRuntime dependencies should be removed in favor of install script"
