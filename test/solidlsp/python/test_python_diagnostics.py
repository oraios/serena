import os

import pytest

from solidlsp import SolidLanguageServer
from test.conftest import PYTHON_LANGUAGE_BACKENDS
from test.solidlsp.util.diagnostics import assert_file_diagnostics


@pytest.mark.python
class TestPythonDiagnostics:
    @pytest.mark.parametrize("language_server", PYTHON_LANGUAGE_BACKENDS, indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            os.path.join("test_repo", "diagnostics_sample.py"),
            ("missing_user", "undefined_name"),
            min_count=2,
        )
