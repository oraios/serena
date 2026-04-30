import shutil

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.util.diagnostics import assert_file_diagnostics


@pytest.mark.elm
@pytest.mark.skipif(shutil.which("node") is None or shutil.which("npm") is None, reason="Elm diagnostics require Node.js and npm")
class TestElmDiagnostics:
    @pytest.mark.parametrize("language_server", [Language.ELM], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            "DiagnosticsSample.elm",
            (),
            min_count=1,
        )
