import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.conftest import language_tests_enabled
from test.solidlsp.util.diagnostics import assert_file_diagnostics

pytestmark = [
    pytest.mark.crystal,
    pytest.mark.skipif(not language_tests_enabled(Language.CRYSTAL), reason="Crystal tests are disabled (crystalline not available)"),
]


class TestCrystalDiagnostics:
    @pytest.mark.parametrize("language_server", [Language.CRYSTAL], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            "src/diagnostics_sample.cr",
            (),
            min_count=1,
        )
