import pytest

from solidlsp.language_servers.clojure_lsp import ClojureLSP

pytestmark = pytest.mark.clojure


def _make_server(monkeypatch: pytest.MonkeyPatch) -> ClojureLSP:
    """Build a ClojureLSP without running __init__ (no clojure-lsp binary needed)."""
    server = object.__new__(ClojureLSP)
    monkeypatch.setattr(ClojureLSP, "_resolve_source_paths", lambda _self: None)
    return server


def test_declares_did_change_watched_files_capability(monkeypatch: pytest.MonkeyPatch) -> None:
    """clojure-lsp must announce that the client sends workspace/didChangeWatchedFiles.

    Serena notifies language servers about files changed outside its own edit tools
    (git checkout, another editor, a build step) via that notification
    (LanguageServerManager.poll_and_notify). A server that was never told the client
    supports it may keep answering symbol queries from its own stale analysis, which
    surfaces as find_symbol returning a body from the wrong location.
    """
    params = _make_server(monkeypatch)._create_base_initialize_params()

    workspace = params["capabilities"]["workspace"]
    assert "didChangeWatchedFiles" in workspace, (
        "clojure-lsp does not declare the didChangeWatchedFiles client capability, so external file changes may not invalidate its analysis"
    )
    assert workspace["didChangeWatchedFiles"]["dynamicRegistration"] is True


def test_base_initialize_params_keep_existing_workspace_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The added capability must not displace the ones already relied upon."""
    workspace = _make_server(monkeypatch)._create_base_initialize_params()["capabilities"]["workspace"]

    assert workspace["applyEdit"] is True
    assert workspace["workspaceEdit"] == {"documentChanges": True}
    assert workspace["workspaceFolders"] is True
    assert workspace["symbol"]["symbolKind"]["valueSet"] == list(range(1, 27))
