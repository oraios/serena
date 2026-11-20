"""
Tests for the GraphQL language server's view of documents that change while it is running.

Each test works on a copy of the fixture repository, since the documents are modified.
"""

import shutil
from pathlib import Path

import pytest

from serena.util.text_utils import find_text_coordinates
from solidlsp.ls_config import LanguageServerId
from test.conftest import language_server_tests_enabled, start_ls_context

pytestmark = [
    pytest.mark.graphql,
    pytest.mark.skipif(not language_server_tests_enabled(LanguageServerId.GRAPHQL), reason="GraphQL tests are disabled"),
]

_FIXTURE_REPO = Path(__file__).parent.parent.parent / "resources" / "repos" / "graphql" / "test_repo"


def _copy_fixture_repo(parent_dir: Path) -> Path:
    repo_path = parent_dir / "test_repo"
    shutil.copytree(_FIXTURE_REPO, repo_path)
    return repo_path


def test_definition_resolves_into_a_file_edited_via_the_language_server(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Edits applied through the language server must leave the server with the complete edited document."""
    repo_path = _copy_fixture_repo(tmp_path_factory.mktemp("repo"))

    with start_ls_context(LanguageServerId.GRAPHQL, repo_path=str(repo_path)) as ls:
        # edit the schema the way Serena's code editor does: within the open file, then save it
        with ls.open_file("schema.graphql") as file_buffer:
            ls.insert_text_at_position("schema.graphql", 0, 0, "type Inserted {\n  value: Int\n}\n\n")
            (repo_path / "schema.graphql").write_text(file_buffer.contents)

        queries_path = "operations/queries.graphql"
        usage = find_text_coordinates((repo_path / queries_path).read_text(), r"(user)\(id")
        assert usage is not None
        definitions = ls.request_definition(queries_path, usage.line, usage.col + 1)

        declaration = find_text_coordinates((repo_path / "schema.graphql").read_text(), r"(user)\(id: ID!\)")
        assert declaration is not None
        assert len(definitions) == 1, f"Expected exactly one definition, got: {definitions}"
        definition = definitions[0]
        assert Path(definition["absolutePath"]).name == "schema.graphql"
        # the range of a definition starts with its description, so it encloses the declaration
        assert definition["range"]["start"]["line"] <= declaration.line <= definition["range"]["end"]["line"]


def test_documents_under_a_path_resembling_a_config_file_name_are_up_to_date(tmp_path_factory: pytest.TempPathFactory) -> None:
    """
    The server mistakes documents whose path contains a config file name like "graphql_config" for config files
    and never reads them itself; their symbols must nonetheless reflect their current contents.
    """
    repo_path = _copy_fixture_repo(tmp_path_factory.mktemp("graphql_config"))

    with start_ls_context(LanguageServerId.GRAPHQL, repo_path=str(repo_path)) as ls:
        schema_path = repo_path / "schema.graphql"
        schema_path.write_text(schema_path.read_text() + "\ntype Added {\n  value: Int\n}\n")
        schema_names = [s["name"] for s in ls.request_document_symbols("schema.graphql").root_symbols]
        assert "Added" in schema_names

        (repo_path / "operations" / "new.graphql").write_text("query Fresh {\n  posts {\n    id\n  }\n}\n")
        new_names = [s["name"] for s in ls.request_document_symbols("operations/new.graphql").root_symbols]
        assert new_names == ["Fresh"]
