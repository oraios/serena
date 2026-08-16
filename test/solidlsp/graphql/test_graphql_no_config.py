"""
Regression test for a workspace with no graphql-config file at all.

``graphql-language-service-server`` never sets its internal "initialized" flag when it
cannot find a graphql-config (.graphqlrc.yml / graphql.config.*) at the workspace root --
it only logs a "graphql-config error, only highlighting is enabled" warning and stays
uninitialized forever. Before this fix, Serena wouldn't recognize that message and would
always wait out the full 30s startup timeout, then continue to silently return empty
results (document symbols, hover, etc.) for the lifetime of the server. This test asserts
that startup instead fails fast once that warning is observed.
"""

import shutil
import time
from pathlib import Path

import pytest

from solidlsp.ls_config import LanguageServerId
from test.conftest import language_server_tests_enabled, start_ls_context

pytestmark = [
    pytest.mark.graphql,
    pytest.mark.skipif(not language_server_tests_enabled(LanguageServerId.GRAPHQL), reason="GraphQL tests are disabled"),
]

# The server logs the config-missing warning and then blocks the "caches initialized"
# signal forever; startup must bail out well short of the 30s timeout used for the
# (legitimate) slow-cache-build case.
_FAST_FAIL_BUDGET_SECONDS = 15.0

_FIXTURE_REPO = Path(__file__).parent.parent.parent / "resources" / "repos" / "graphql_no_config" / "test_repo"


def test_startup_does_not_wait_out_the_full_timeout() -> None:
    repo_path = str(_FIXTURE_REPO)
    started_at = time.monotonic()
    with start_ls_context(LanguageServerId.GRAPHQL, repo_path=repo_path) as ls:
        elapsed = time.monotonic() - started_at
        assert ls.is_running()
        assert elapsed < _FAST_FAIL_BUDGET_SECONDS, (
            f"Startup took {elapsed:.1f}s -- expected the missing-config warning to short-circuit the wait well before the 30s timeout"
        )
        # Without a graphql-config, the server never leaves its uninitialized state, so
        # document symbols must come back empty rather than raising or hanging.
        all_symbols, _ = ls.request_document_symbols("schema.graphql").get_all_symbols_and_roots()
        assert all_symbols == []


def test_adding_graphql_config_invalidates_the_stale_empty_cache(tmp_path: Path) -> None:
    """
    Regression test: `_raw_document_symbols_cache_fingerprint` must account for the resolved
    graphql-config, or Serena's own on-disk document-symbols cache -- keyed only on each file's
    content hash -- keeps serving the empty result computed while no config existed, even after
    a config is added later and the language server itself starts resolving symbols correctly.
    Reproduces a real-world case: enabling the `graphql` language server on a project that had no
    graphql-config, then adding one later without ever touching schema.graphql itself.
    """
    repo_path = tmp_path / "test_repo"
    shutil.copytree(_FIXTURE_REPO, repo_path)

    # First run: no graphql-config -- document symbols must be empty, and that empty result gets
    # persisted to the on-disk cache (mirroring what the real ls_manager does via save_cache()).
    with start_ls_context(LanguageServerId.GRAPHQL, repo_path=str(repo_path)) as ls:
        all_symbols, _ = ls.request_document_symbols("schema.graphql").get_all_symbols_and_roots()
        assert all_symbols == []
        ls.save_cache()

    # Add a graphql-config, then start a *new* server instance against the same repo path (and
    # therefore the same on-disk document-symbols cache) without touching schema.graphql itself.
    (repo_path / ".graphqlrc.yml").write_text("schema: schema.graphql\n")

    with start_ls_context(LanguageServerId.GRAPHQL, repo_path=str(repo_path)) as ls:
        all_symbols, _ = ls.request_document_symbols("schema.graphql").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        assert "Query" in names, f"Expected 'Query' to appear now that a graphql-config exists, got: {names}"
