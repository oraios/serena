import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.conftest import language_server_tests_enabled
from test.solidlsp.util.diagnostics import assert_file_diagnostics


@pytest.mark.skipif(not language_server_tests_enabled(LanguageServerId.OCAML), reason="OCaml tests are disabled (opam not available)")
@pytest.mark.ocaml
class TestOcamlDiagnostics:
    @pytest.mark.parametrize("language_server", [LanguageServerId.OCAML], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            "lib/diagnostics_sample.ml",
            (),
            min_count=1,
        )
