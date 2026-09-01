"""Behavioral coverage for the Helm language server adapter."""

from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.solidlsp.conftest import read_repo_file

pytestmark = pytest.mark.helm


@pytest.mark.parametrize("language_server", [LanguageServerId.HELM], indirect=True)
@pytest.mark.parametrize("repo_path", [LanguageServerId.HELM], indirect=True)
def test_helm_server_starts(language_server: SolidLanguageServer, repo_path: Path) -> None:
    assert language_server.is_running()
    assert Path(language_server.repository_root_path).resolve() == repo_path.resolve()


@pytest.mark.parametrize("language_server", [LanguageServerId.HELM], indirect=True)
def test_helm_chart_and_template_symbols_are_returned(language_server: SolidLanguageServer) -> None:
    chart_symbols, _ = language_server.request_document_symbols("Chart.yaml").get_all_symbols_and_roots()
    chart_names = {symbol["name"] for symbol in chart_symbols}
    assert {"apiVersion", "name", "version"} <= chart_names

    template_symbols, _ = language_server.request_document_symbols("templates/deployment.yaml").get_all_symbols_and_roots()
    template_names = {symbol["name"] for symbol in template_symbols}
    assert {"apiVersion", "kind", "metadata", "spec"} <= template_names


@pytest.mark.parametrize("language_server", [LanguageServerId.HELM], indirect=True)
def test_helm_values_definition_and_references(language_server: SolidLanguageServer) -> None:
    content = read_repo_file(language_server, "templates/deployment.yaml")
    marker = ".Values.replicaCount"
    line, column = next(
        (line_no, content_line.index(marker)) for line_no, content_line in enumerate(content.splitlines()) if marker in content_line
    )

    definitions = language_server.request_definition("templates/deployment.yaml", line, column + len(".Values."))
    assert any(location["uri"].endswith("values.yaml") for location in definitions)

    references = language_server.request_references("values.yaml", 0, 0)
    assert any(reference.get("relativePath") == "templates/deployment.yaml" for reference in references)
