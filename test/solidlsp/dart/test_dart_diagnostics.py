import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.solidlsp.util.diagnostics import assert_file_diagnostics


@pytest.mark.dart
class TestDartDiagnostics:
    @pytest.mark.parametrize("language_server", [LanguageServerId.DART], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            "lib/diagnostics_sample.dart",
            (),
            min_count=1,
        )
