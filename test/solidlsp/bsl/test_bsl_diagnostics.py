import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.conftest import language_tests_enabled
from test.solidlsp.util.diagnostics import assert_file_diagnostics


@pytest.mark.bsl
@pytest.mark.skipif(not language_tests_enabled(Language.BSL), reason="BSL tests are disabled")
class TestBSLDiagnostics:
    @pytest.mark.parametrize("language_server", [Language.BSL], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        """bsl-language-server must flag the unterminated string literal in the fixture."""
        assert_file_diagnostics(
            language_server,
            "diagnostics_sample.bsl",
            (),
            min_count=1,
        )
