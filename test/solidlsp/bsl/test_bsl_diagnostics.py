import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.conftest import language_server_tests_enabled
from test.solidlsp.util.diagnostics import assert_file_diagnostics


@pytest.mark.bsl
@pytest.mark.skipif(not language_server_tests_enabled(LanguageServerId.BSL), reason="BSL tests require Java")
class TestBSLDiagnostics:
    @pytest.mark.parametrize("language_server", [LanguageServerId.BSL], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        """bsl-language-server must flag the unterminated string literal in the fixture."""
        assert_file_diagnostics(
            language_server,
            "diagnostics_sample.bsl",
            ("Ошибка разбора исходного кода",),
            min_count=1,
        )
        diagnostics = language_server.request_text_document_diagnostics("diagnostics_sample.bsl", min_severity=1)
        assert any(
            diagnostic.get("code") == "ParseError"
            and diagnostic["severity"] == 1
            and diagnostic["range"] == {"start": {"line": 5, "character": 0}, "end": {"line": 5, "character": 14}}
            for diagnostic in diagnostics
        ), diagnostics
