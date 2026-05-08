import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.util.diagnostics import assert_file_diagnostics


@pytest.mark.ada
class TestAdaDiagnostics:
    @pytest.mark.parametrize("language_server", [Language.ADA], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            "src/diagnostics_sample.adb",
            (),
            min_count=1,
        )
