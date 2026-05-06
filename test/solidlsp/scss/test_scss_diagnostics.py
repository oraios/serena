"""
Diagnostics tests for the SCSS / Sass / CSS language server (Some Sass).

Two sources are exercised — the SCSS parser (undefined ``$variable``) and the
plain-CSS parser (syntax error inside a rule body). ``somesass.css.diagnostics.enabled``
is flipped on at initialization so the .css path is not gated off; lint diagnostics
are deliberately left disabled (the upstream rules are opinionated about vendor
prefixes / empty rules / etc.) so only syntax-level errors surface here.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.util.diagnostics import assert_file_diagnostics


@pytest.mark.scss
class TestScssDiagnostics:
    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_scss_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            "diagnostics_sample.scss",
            (),
            min_count=1,
        )

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_plain_css_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        """Plain ``.css`` diagnostics flow through the same Some Sass server.

        Without ``somesass.css.diagnostics.enabled = true`` (which Serena pushes via
        initializationOptions), this would short-circuit to an empty list at the
        handler entrypoint.
        """
        assert_file_diagnostics(
            language_server,
            "css/diagnostics_sample.css",
            (),
            min_count=1,
        )
