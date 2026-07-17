import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.conftest import language_tests_enabled
from test.solidlsp.util.diagnostics import assert_file_diagnostics

pytestmark = pytest.mark.skipif(not language_tests_enabled(Language.LEAN4), reason="Lean4 tests are disabled (lean not available)")


@pytest.mark.lean4
class TestLean4Diagnostics:
    @pytest.mark.parametrize("language_server", [Language.LEAN4], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            "DiagnosticsSample.lean",
            (),
            min_count=1,
        )
