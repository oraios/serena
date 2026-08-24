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
from solidlsp.ls_config import LanguageServerId
from test.solidlsp.util.diagnostics import assert_file_diagnostics


@pytest.mark.angular
class TestAngularDiagnostics:
    @pytest.mark.parametrize("language_server", [LanguageServerId.ANGULAR], indirect=True)
    def test_component_class_diagnostics(self, language_server: SolidLanguageServer) -> None:
        """The component's ``count: number = 'not-a-number'`` must be flagged by tsserver."""
        assert_file_diagnostics(
            language_server,
            "src/app/diagnostics_sample.ts",
            (),
            min_count=1,
        )

    @pytest.mark.parametrize("language_server", [LanguageServerId.ANGULAR], indirect=True)
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


@pytest.mark.angular
class TestAngularPublishedDiagnostics:
    """``textDocument/publishDiagnostics`` — the stream Serena reads after an edit.

    ngserver publishes for .html templates only; for .ts it publishes nothing, so before the
    routing below every edited component waited out the full timeout and returned nothing.
    """

    @pytest.mark.parametrize("language_server", [LanguageServerId.ANGULAR], indirect=True)
    def test_published_diagnostics_for_component_class(self, language_server: SolidLanguageServer) -> None:
        path = "src/app/diagnostics_sample.ts"
        with language_server.open_file(path):
            diagnostics = language_server.request_published_text_document_diagnostics(path, min_severity=2)
        assert diagnostics, f"Expected published diagnostics for the type error in {path}, got: {diagnostics}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.ANGULAR], indirect=True)
    def test_published_diagnostics_for_template(self, language_server: SolidLanguageServer) -> None:
        """The .html half must keep coming from ngserver — the companion cannot type-check templates."""
        path = "src/app/diagnostics_sample.html"
        with language_server.open_file(path):
            diagnostics = language_server.request_published_text_document_diagnostics(path, min_severity=2)
        assert diagnostics, f"Expected published diagnostics for the template error in {path}, got: {diagnostics}"
