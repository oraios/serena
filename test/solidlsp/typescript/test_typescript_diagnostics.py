import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.solidlsp.util.diagnostics import assert_file_diagnostics


@pytest.mark.typescript
class TestTypeScriptDiagnostics:
    @pytest.mark.parametrize("language_server", [LanguageServerId.TYPESCRIPT], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            "diagnostics_sample.ts",
            ("missingGreeting", "missingConsumerValue"),
            min_count=2,
        )
