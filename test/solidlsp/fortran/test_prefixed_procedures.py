# SPDX-License-Identifier: MIT

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.solidlsp.conftest import find_document_symbol

pytestmark = pytest.mark.fortran


@pytest.mark.parametrize("language_server", [LanguageServerId.FORTRAN], indirect=True)
@pytest.mark.parametrize("name", ["increment", "scale", "double_integer", "factorial", "square"])
def test_find_references_to_prefixed_procedure(language_server: SolidLanguageServer, name: str) -> None:
    """Reference searches from prefixed procedure symbols include their cross-file call sites."""
    relative_path = "modules/prefixed_procedures.f90"
    symbol = find_document_symbol(language_server, relative_path, name)
    start = symbol["selectionRange"]["start"]

    references = language_server.request_references(relative_path, start["line"], start["character"])

    assert any(ref.get("relativePath") == "prefixed_procedure_calls.f90" for ref in references), references
