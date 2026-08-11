"""Diagnostics tests for the Bazel/Starlark language server (starpls)."""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.solidlsp.util.diagnostics import assert_file_diagnostics


@pytest.mark.starlark
class TestStarlarkDiagnostics:
    @pytest.mark.parametrize("language_server", [LanguageServerId.STARLARK], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        """``diagnostics_sample.bzl`` references an undefined name and must yield an error."""
        assert_file_diagnostics(language_server, "diagnostics_sample.bzl", ("is not defined",), min_count=1)
