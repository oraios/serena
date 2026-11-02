"""
Tests for a workspace whose graphql-config is present but points at a schema that cannot be
fully resolved (here: a directive used in the SDL but never declared in it).

``graphql-language-service-server`` logs the same "graphql-config error" line for this case as
for a missing config, but here its caches do come up and requests are served, so document
symbols must still be returned.
"""

from pathlib import Path

import pytest

from solidlsp.ls_config import LanguageServerId
from test.conftest import language_server_tests_enabled, start_ls_context

pytestmark = [
    pytest.mark.graphql,
    pytest.mark.skipif(not language_server_tests_enabled(LanguageServerId.GRAPHQL), reason="GraphQL tests are disabled"),
]

_FIXTURE_REPO = Path(__file__).parent.parent.parent / "resources" / "repos" / "graphql_unresolved_schema" / "test_repo"


def test_document_symbols_are_returned_despite_unresolved_schema() -> None:
    with start_ls_context(LanguageServerId.GRAPHQL, repo_path=str(_FIXTURE_REPO)) as ls:
        all_symbols, _ = ls.request_document_symbols("schema.graphql").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        for name in ("Query", "user", "User", "email"):
            assert name in names, f"Expected {name!r} among the document symbols, got: {names}"
