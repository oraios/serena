import shutil

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.conftest import language_tests_enabled
from test.solidlsp.util.diagnostics import assert_file_diagnostics

pytestmark = [
    pytest.mark.pascal,
    pytest.mark.skipif(not language_tests_enabled(Language.PASCAL), reason="Pascal tests are disabled"),
    pytest.mark.skipif(shutil.which("fpc") is None, reason="Pascal diagnostics require the Free Pascal compiler"),
]


class TestPascalDiagnostics:
    @pytest.mark.parametrize("language_server", [Language.PASCAL], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            "diagnostics_sample.pas",
            (),
            min_count=1,
        )
