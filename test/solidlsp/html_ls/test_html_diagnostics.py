"""
Diagnostics smoke test for the HTML language server.

``vscode-html-language-server`` does not validate HTML structure itself — upstream
``vscode-html-languageservice`` only forwards validation to embedded sub-services
(CSS/JS in ``<style>`` / ``<script>`` blocks), and those aren't wired up in
standalone mode. So a malformed-HTML fixture would yield zero diagnostics regardless.

Asserting "at least one diagnostic" would be a false positive waiting to happen.
Instead, this test verifies the diagnostics endpoint is reachable end-to-end and
the framework's pull→publish fallback handles the empty response correctly — i.e.
it returns a list, not an error. That alone catches LS-crash regressions on the
diagnostic request, which is the practical purpose for this LS.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.html
class TestHtmlDiagnostics:
    @pytest.mark.parametrize("language_server", [Language.HTML], indirect=True)
    def test_diagnostics_endpoint_returns_list(self, language_server: SolidLanguageServer) -> None:
        diagnostics = language_server.request_text_document_diagnostics("diagnostics_sample.html", min_severity=1)
        assert isinstance(diagnostics, list), diagnostics
