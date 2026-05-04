import shutil

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.util.diagnostics import assert_file_diagnostics

pytestmark = [
    pytest.mark.crystal,
    pytest.mark.skipif(shutil.which("crystalline") is None, reason="Crystalline is not installed"),
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
