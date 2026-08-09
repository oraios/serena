import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.solidlsp.util.diagnostics import assert_file_diagnostics


@pytest.mark.java
class TestJavaDiagnostics:
    @pytest.mark.parametrize("language_server", [LanguageServerId.JAVA], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            "src/main/java/test_repo/DiagnosticsSample.java",
            (),
            min_count=1,
        )
