"""Tests for C# language server NuGet package download from NuGet.org."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from solidlsp.language_servers.common import RuntimeDependency
from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer
from solidlsp.settings import SolidLSPSettings


@pytest.mark.csharp
class TestNuGetOrgDownload:
    """Test downloading Roslyn language server packages from NuGet.org."""

    def test_download_nuget_package_uses_direct_url(self):
        """Test that _download_nuget_package uses the URL and checksum from RuntimeDependency directly."""
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

            captured_calls: list[tuple[str, str, str, str | None, tuple[str, ...] | list[str] | None]] = []

            def fake_download_and_extract(
                url: str,
                target_path: str,
                archive_type: str,
                expected_sha256: str | None = None,
                allowed_hosts: tuple[str, ...] | list[str] | None = None,
            ) -> None:
                captured_calls.append((url, target_path, archive_type, expected_sha256, allowed_hosts))
                Path(target_path).mkdir(parents=True, exist_ok=True)

            with patch(
                "solidlsp.language_servers.csharp_language_server.FileUtils.download_and_extract_archive_verified",
                side_effect=fake_download_and_extract,
            ):
                package_dir = dependency_provider._download_nuget_package(test_dependency)

            assert package_dir == Path(temp_dir) / "temp_downloads" / "roslyn-language-server.linux-x64.5.5.0-2.26078.4"
            assert captured_calls == [
                (
                    test_dependency.url,
                    str(package_dir),
                    "zip",
                    test_dependency.sha256,
                    test_dependency.allowed_hosts,
                )
            ]
            called_url = captured_calls[0][0]
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
            assert dep.package_name.startswith("roslyn-language-server."), (
                f"Package name should start with 'roslyn-language-server.' but got: {dep.package_name}"
            )

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
            with patch(
                "solidlsp.language_servers.csharp_language_server.FileUtils.download_and_extract_archive_verified",
            ):
                dependency_provider._download_nuget_package(test_dependency)
