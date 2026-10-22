import pytest

from solidlsp import SolidLanguageServer
from test.conftest import TYPESCRIPT_LANGUAGE_BACKENDS
from test.solidlsp.util.diagnostics import assert_file_diagnostics


@pytest.mark.typescript
class TestTypeScriptDiagnostics:
    @pytest.mark.parametrize("language_server", TYPESCRIPT_LANGUAGE_BACKENDS, indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            "diagnostics_sample.ts",
            ("missingGreeting", "missingConsumerValue"),
            min_count=2,
        )
