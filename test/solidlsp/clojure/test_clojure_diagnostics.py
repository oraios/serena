import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.util.diagnostics import assert_file_diagnostics


@pytest.mark.clojure
class TestClojureDiagnostics:
    @pytest.mark.parametrize("language_server", [Language.CLOJURE], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            os.path.join("src", "test_app", "diagnostics_sample.clj"),
            ("missing-greeting", "missing-consumer-value"),
            min_count=2,
        )
