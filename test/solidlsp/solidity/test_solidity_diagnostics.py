import sys

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.util.diagnostics import assert_file_diagnostics


@pytest.mark.solidity
class TestSolidityDiagnostics:
    @pytest.mark.xfail(
        sys.platform != "linux",
        reason="Solidity diagnostics are often empty on macOS and Windows CI (AssertionError: []); "
        "passes on Ubuntu. Root cause not yet identified.",
        strict=False,
    )
    @pytest.mark.parametrize("language_server", [Language.SOLIDITY], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            "contracts/DiagnosticsSample.sol",
            (),
            min_count=1,
        )
