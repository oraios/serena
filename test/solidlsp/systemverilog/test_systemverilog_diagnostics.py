import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.conftest import language_tests_enabled
from test.solidlsp.util.diagnostics import assert_file_diagnostics

pytestmark = pytest.mark.skipif(
    not language_tests_enabled(Language.SYSTEMVERILOG), reason="SystemVerilog tests are disabled (verible-verilog-ls not available)"
)


@pytest.mark.systemverilog
class TestSystemverilogDiagnostics:
    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            "diagnostics_sample.sv",
            (),
            min_count=1,
        )
