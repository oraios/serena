# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the discovery and version check of the Pkl language server executable."""

import os
from typing import NamedTuple
from unittest.mock import patch

import pytest

from solidlsp.language_servers.pkl_language_server import MINIMUM_SUPPORTED_VERSION, PklLanguageServer
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.settings import SolidLSPSettings
from solidlsp.util.subprocess_util import convert_shell_cmd


class _CompletedProcess(NamedTuple):
    """The parts of a completed process the version check reads."""

    stdout: str
    stderr: str
    returncode: int = 0


class TestPklDependencyProvider:
    def test_a_supported_version_is_accepted(self) -> None:
        """A release at or above the minimum is used."""
        with patch(
            "solidlsp.language_servers.pkl_language_server.subprocess_run",
            return_value=_CompletedProcess(stdout="", stderr="pkl-lsp version 0.8.0"),
        ) as run:
            PklLanguageServer.DependencyProvider._check_version("/usr/bin/pkl-lsp")

        assert run.call_args.args[0] == convert_shell_cmd(["/usr/bin/pkl-lsp", "--version"])
        assert run.call_args.kwargs["shell"] is True, "a .cmd/.bat launcher on Windows cannot be spawned without a shell"
        expected_cwd = os.path.dirname(os.path.abspath("/usr/bin/pkl-lsp"))
        assert run.call_args.kwargs["cwd"] == expected_cwd, "the probe must resolve relative paths as the executable itself would"

    def test_the_minimum_supported_version_is_accepted(self) -> None:
        """The oldest diagnostics-publishing release is not rejected."""
        minimum = ".".join(str(part) for part in MINIMUM_SUPPORTED_VERSION)
        with patch(
            "solidlsp.language_servers.pkl_language_server.subprocess_run",
            return_value=_CompletedProcess(stdout=f"pkl-lsp version {minimum}", stderr=""),
        ):
            PklLanguageServer.DependencyProvider._check_version("/usr/bin/pkl-lsp")

    def test_an_older_version_is_rejected(self) -> None:
        """A release below the minimum is rejected, naming the version and the minimum."""
        minimum = ".".join(str(part) for part in MINIMUM_SUPPORTED_VERSION)
        with patch(
            "solidlsp.language_servers.pkl_language_server.subprocess_run",
            return_value=_CompletedProcess(stdout="", stderr="pkl-lsp version 0.7.1"),
        ):
            with pytest.raises(SolidLSPException) as exception_info:
                PklLanguageServer.DependencyProvider._check_version("/usr/bin/pkl-lsp")

        message = str(exception_info.value)
        assert "0.7.1" in message, message
        assert minimum in message, message

    def test_a_development_suffix_does_not_change_the_verdict(self) -> None:
        """A build reporting ``X.Y.Z-dev+`` is judged by its release number."""
        with patch(
            "solidlsp.language_servers.pkl_language_server.subprocess_run",
            return_value=_CompletedProcess(stdout="", stderr="pkl-lsp version 0.7.1-dev+abc123"),
        ):
            with pytest.raises(SolidLSPException):
                PklLanguageServer.DependencyProvider._check_version("/usr/bin/pkl-lsp")

    def test_an_unparseable_version_is_accepted(self) -> None:
        """Only a demonstrably old release is rejected, so an unrecognised output is tolerated."""
        with patch(
            "solidlsp.language_servers.pkl_language_server.subprocess_run",
            return_value=_CompletedProcess(stdout="unknown build", stderr=""),
        ):
            PklLanguageServer.DependencyProvider._check_version("/usr/bin/pkl-lsp")

    def test_a_failing_interrogation_is_rejected(self) -> None:
        """An executable that cannot start is rejected rather than left to fail during initialization."""
        with patch(
            "solidlsp.language_servers.pkl_language_server.subprocess_run",
            side_effect=OSError("exec format error"),
        ):
            with pytest.raises(SolidLSPException) as exception_info:
                PklLanguageServer.DependencyProvider._check_version("/usr/bin/pkl-lsp")

        assert "/usr/bin/pkl-lsp" in str(exception_info.value)

    def test_an_executable_that_cannot_start_is_rejected(self) -> None:
        """A launcher failing for want of a recent JVM names the actual failure."""
        with patch(
            "solidlsp.language_servers.pkl_language_server.subprocess_run",
            return_value=_CompletedProcess(
                stdout="",
                stderr="Error: LinkageError occurred while loading main class org.pkl.lsp.MainKt\n"
                "\tjava.lang.UnsupportedClassVersionError: org/pkl/lsp/MainKt has been compiled by a more "
                "recent version of the Java Runtime (class file version 67.0)",
                returncode=1,
            ),
        ):
            with pytest.raises(SolidLSPException) as exception_info:
                PklLanguageServer.DependencyProvider._check_version("/usr/bin/pkl-lsp")

        message = str(exception_info.value)
        assert "UnsupportedClassVersionError" in message, message
        assert "Java 23" in message, message

    def test_the_version_is_checked_for_a_configured_path_as_well(self) -> None:
        """A path configured via ls_path is subject to the same version check as one found on PATH."""
        provider = PklLanguageServer.DependencyProvider(SolidLSPSettings.CustomLSSettings({"ls_path": "/opt/pkl-lsp"}), ls_resources_dir="")
        with patch(
            "solidlsp.language_servers.pkl_language_server.subprocess_run",
            return_value=_CompletedProcess(stdout="pkl-lsp version 0.7.1", stderr=""),
        ) as run:
            with pytest.raises(SolidLSPException):
                provider.create_launch_command()

        assert run.call_args.args[0] == convert_shell_cmd(["/opt/pkl-lsp", "--version"])

    def test_a_missing_executable_is_reported(self) -> None:
        """Discovery reports the installation requirement instead of a bare lookup failure."""
        provider = PklLanguageServer.DependencyProvider(SolidLSPSettings.CustomLSSettings({}), ls_resources_dir="")
        with patch("solidlsp.language_servers.pkl_language_server.shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError) as exception_info:
                provider._get_or_install_core_dependency()

        message = str(exception_info.value)
        assert "pkl-lsp" in message, message
        assert "https://github.com/apple/pkl-lsp/releases" in message, message
