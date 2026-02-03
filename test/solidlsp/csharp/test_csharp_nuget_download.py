"""Tests for C# language server NuGet package download from NuGet.org."""

import tempfile
from unittest.mock import patch

import pytest

from solidlsp.language_servers.common import RuntimeDependency
from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer
from solidlsp.settings import SolidLSPSettings


@pytest.mark.csharp
class TestNuGetOrgDownload:
    """Test downloading Roslyn language server packages from NuGet.org."""

    def test_download_nuget_package_uses_direct_url(self):
        """Test that _download_nuget_package uses the URL from RuntimeDependency directly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a RuntimeDependency with a NuGet.org URL
            test_dependency = RuntimeDependency(
                id="TestPackage",
                description="Test package from NuGet.org",
                package_name="roslyn-language-server.linux-x64",
                package_version="5.5.0-2.26078.4",
                url="https://www.nuget.org/api/v2/package/roslyn-language-server.linux-x64/5.5.0-2.26078.4",
                platform_id="linux-x64",
                archive_type="nupkg",
                binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
                extract_path="content/LanguageServer/linux-x64",
            )

            # Mock the dependency provider
            mock_settings = SolidLSPSettings()
            custom_settings = SolidLSPSettings.CustomLSSettings({})

            dependency_provider = CSharpLanguageServer.DependencyProvider(
                custom_settings=custom_settings,
                ls_resources_dir=temp_dir,
                solidlsp_settings=mock_settings,
                repository_root_path="/fake/repo",
            )

            # Mock urllib.request.urlretrieve to capture the URL being used
            with patch("solidlsp.language_servers.csharp_language_server.urllib.request.urlretrieve") as mock_retrieve:
                with patch("solidlsp.language_servers.csharp_language_server.SafeZipExtractor"):
                    try:
                        dependency_provider._download_nuget_package(test_dependency)
                    except Exception:
                        # Expected to fail since we're mocking, but we want to check the URL
                        pass

                    # Verify that urlretrieve was called with the NuGet.org URL
                    assert mock_retrieve.called, "urlretrieve should be called"
                    called_url = mock_retrieve.call_args[0][0]
                    assert called_url == test_dependency.url, f"Should use URL from RuntimeDependency: {test_dependency.url}"
                    assert "nuget.org" in called_url, "Should use NuGet.org URL"
                    assert "azure" not in called_url.lower(), "Should not use Azure feed"

    def test_runtime_dependencies_use_nuget_org_urls(self):
        """Test that _RUNTIME_DEPENDENCIES are configured with NuGet.org URLs."""
        from solidlsp.language_servers.csharp_language_server import _RUNTIME_DEPENDENCIES

        # Check language server dependencies
        lang_server_deps = [dep for dep in _RUNTIME_DEPENDENCIES if dep.id == "CSharpLanguageServer"]

        assert len(lang_server_deps) == 6, "Should have 6 language server platform variants"

        for dep in lang_server_deps:
            # Verify package name uses roslyn-language-server
            assert dep.package_name is not None, f"Package name should be set for {dep.platform_id}"
            assert dep.package_name.startswith(
                "roslyn-language-server."
            ), f"Package name should start with 'roslyn-language-server.' but got: {dep.package_name}"

            # Verify version is the newer NuGet.org version
            assert dep.package_version == "5.5.0-2.26078.4", f"Should use NuGet.org version 5.5.0-2.26078.4, got: {dep.package_version}"

            # Verify URL points to NuGet.org
            assert dep.url is not None, f"URL should be set for {dep.platform_id}"
            assert "nuget.org" in dep.url, f"URL should point to nuget.org, got: {dep.url}"
            assert "azure" not in dep.url.lower(), f"URL should not point to Azure feed, got: {dep.url}"

    def test_download_method_does_not_call_azure_feed(self):
        """Test that the new download method does not attempt to access Azure feed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dependency = RuntimeDependency(
                id="TestPackage",
                description="Test package",
                package_name="roslyn-language-server.linux-x64",
                package_version="5.5.0-2.26078.4",
                url="https://www.nuget.org/api/v2/package/roslyn-language-server.linux-x64/5.5.0-2.26078.4",
                platform_id="linux-x64",
                archive_type="nupkg",
                binary_name="test.dll",
            )

            mock_settings = SolidLSPSettings()
            custom_settings = SolidLSPSettings.CustomLSSettings({})

            dependency_provider = CSharpLanguageServer.DependencyProvider(
                custom_settings=custom_settings,
                ls_resources_dir=temp_dir,
                solidlsp_settings=mock_settings,
                repository_root_path="/fake/repo",
            )

            # Mock urllib.request.urlopen to track if Azure feed is accessed
            with patch("solidlsp.language_servers.csharp_language_server.urllib.request.urlopen") as mock_urlopen:
                with patch("solidlsp.language_servers.csharp_language_server.urllib.request.urlretrieve"):
                    with patch("solidlsp.language_servers.csharp_language_server.SafeZipExtractor"):
                        try:
                            dependency_provider._download_nuget_package(test_dependency)
                        except Exception:
                            pass

                        # Verify that urlopen was NOT called (no service index lookup)
                        assert not mock_urlopen.called, "Should not call urlopen for Azure service index lookup"
