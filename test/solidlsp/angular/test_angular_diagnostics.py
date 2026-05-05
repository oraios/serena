"""
Diagnostics tests for the Angular language server.

Two paths are exercised:
  * .ts component — tsserver (via the @angular/language-service plugin) reports
    the type-mismatch on a class field initializer.
  * .html template — ngserver reports the unresolved identifier in a template
    interpolation, but only because the template is attached to a @Component via
    ``templateUrl``. Bare .html files are not type-checked by ngserver.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.util.diagnostics import assert_file_diagnostics


@pytest.mark.angular
class TestAngularDiagnostics:
    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_component_class_diagnostics(self, language_server: SolidLanguageServer) -> None:
        """The component's ``count: number = 'not-a-number'`` must be flagged by tsserver."""
        assert_file_diagnostics(
            language_server,
            "src/app/diagnostics_sample.ts",
            (),
            min_count=1,
        )

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_template_diagnostics(self, language_server: SolidLanguageServer) -> None:
        """The template's ``{{ undefinedSignal() }}`` must be flagged by ngserver.

        Routed through the Angular template compiler, which only checks templates
        attached to a @Component — see the companion ``diagnostics_sample.ts`` that
        wires this file via ``templateUrl``.
        """
        assert_file_diagnostics(
            language_server,
            "src/app/diagnostics_sample.html",
            (),
            min_count=1,
        )
