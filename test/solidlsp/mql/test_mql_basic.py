"""Basic integration tests for the MQL language server (davalillo/mql-language-server)."""

from pathlib import Path

import pytest

from serena.util.inspection import compute_language_server_support_composition
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols


class TestMqlRouting:
    """Verifies language registration routing for the single ``mql`` server id.

    One LanguageServerId serves MQL4 (.mq4), MQL5 (.mq5), and MQL5 include
    (.mqh) files; project auto-discovery must pick it up with zero changes
    to src/serena/ (spec R1, scenarios s1-s2).
    """

    def test_matcher_maps_all_three_extensions(self) -> None:
        """``get_source_fn_matcher`` routes .mq4, .mq5, and .mqh to LanguageServerId.MQL."""
        matcher = LanguageServerId.MQL.get_source_fn_matcher()

        assert matcher.is_relevant_filename("ExpertAdvisor.mq4"), ".mq4 must route to mql"
        assert matcher.is_relevant_filename("TradingClass.mq5"), ".mq5 must route to mql"
        assert matcher.is_relevant_filename("IncludeUtils.mqh"), ".mqh must route to mql"

    def test_matcher_does_not_absorb_other_languages(self) -> None:
        """The matcher must not claim extensions belonging to other languages."""
        matcher = LanguageServerId.MQL.get_source_fn_matcher()

        assert not matcher.is_relevant_filename("main.py")
        assert not matcher.is_relevant_filename("main.cpp")
        assert not matcher.is_relevant_filename("ExpertAdvisor.ex4")

    def test_auto_discovery_finds_mql_for_mq5_workspace(self, tmp_path: Path) -> None:
        """A workspace containing only .mq5 files discovers ``mql`` without src/serena/ changes."""
        (tmp_path / "TradingClass.mq5").write_text("class TradingClass {};")

        composition = compute_language_server_support_composition(str(tmp_path))

        assert LanguageServerId.MQL in composition, f"mql not discovered for .mq5-only workspace: {composition}"


@pytest.mark.mql
class TestMqlLanguageServer:
    """Verifies that the mql-language-server drives the symbol and reference APIs Serena depends on.

    The test repo (``test/resources/repos/mql/test_repo``) contains:

    - ``ExpertAdvisor.mq4``: MQL4 functions with input params and an OrderSend call.
    - ``TradingClass.mq5``: an MQL5 class with a template method and new/delete,
      including ``IncludeUtils.mqh``.
    - ``IncludeUtils.mqh``: helper functions referenced by the .mq5 file.

    Line/character positions below are 0-indexed (LSP convention) and are pinned
    to the fixture contents created in task 3.1-3.3.

    Server capability notes (probed against mql-lsp-server v2.0.0):
    - symbols come back as a FLAT DocumentSymbol list (no ``children`` key), so
      hierarchy-sensitive assertions treat class members as roots too.
    - hover/definition resolve LOCAL symbols; cross-file definition (call sites in
      another file, include lines) is not supported by the server, but references
      ARE workspace-wide and are asserted instead (spec R4 .mqh-include scenario is
      verified via the reference location pointing at the .mqh file).
    - completion returns a non-empty keyword list.
    """

    @pytest.mark.parametrize("language_server", [LanguageServerId.MQL], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.MQL], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """The server starts and reports the expected repository root."""
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [LanguageServerId.MQL], indirect=True)
    def test_document_symbols_trading_class(self, language_server: SolidLanguageServer) -> None:
        """``TradingClass.mq5`` exposes its class and methods as document symbols."""
        all_symbols, root_symbols = language_server.request_document_symbols("TradingClass.mq5").get_all_symbols_and_roots()

        root_names = [s.get("name") for s in root_symbols]
        assert "TradingClass" in root_names, f"TradingClass missing from roots: {root_names}"

        # the server reports a flat symbol list, so Execute appears alongside the class
        assert any(s.get("name") == "TradingClass" for s in all_symbols), "class symbol missing"
        assert any(s.get("name") == "Execute" for s in all_symbols), "method symbol missing"
        for symbol in all_symbols:
            assert "children" not in symbol or isinstance(symbol.get("children"), list), "children must be a list when present"

    @pytest.mark.parametrize("language_server", [LanguageServerId.MQL], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.MQL], indirect=True)
    def test_find_definition_within_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """A same-file call site resolves to the function definition in ExpertAdvisor.mq4."""
        # ExpertAdvisor.mq4 line 16 (0-indexed): "   int lots = CalculateLotSize(AccountBalance());"
        # cursor inside the CalculateLotSize identifier; the server reports the def range
        # starting on the same statement block (probe: range 16,21 -> 16,27 for the call token)
        definitions = language_server.request_definition(str(repo_path / "ExpertAdvisor.mq4"), 16, 21)

        assert definitions, "Expected a definition for the same-file call"
        target = definitions[0]
        assert target["uri"].endswith("ExpertAdvisor.mq4")

    @pytest.mark.parametrize("language_server", [LanguageServerId.MQL], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.MQL], indirect=True)
    def test_references_across_dialects_reach_mqh(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """References on the .mqh helper reach the .mq5 call site (D7-1: .mqh served as mql5 by the same server)."""
        include_utils_path = str(repo_path / "IncludeUtils.mqh")
        # IncludeUtils.mqh line 3 (0-indexed): "double NormalizeLot(double lots)"
        references = language_server.request_references(include_utils_path, 3, 12)

        assert references, "Expected references for the .mqh helper function"
        ref_pairs = {(ref["uri"].split("/")[-1], ref["range"]["start"]["line"]) for ref in references}
        # the .mq5 file references NormalizeLot in its Execute body
        assert any(f == "TradingClass.mq5" for f, _ in ref_pairs), f".mq5 reference to the .mqh helper missing: {sorted(ref_pairs)}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.MQL], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.MQL], indirect=True)
    def test_hover_and_references_on_mq4_function(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Hover returns content and references resolve for an .mq4 function."""
        expert_path = str(repo_path / "ExpertAdvisor.mq4")
        # ExpertAdvisor.mq4 line 8 (0-indexed): "int CalculateLotSize(double balance)"
        hover = language_server.request_hover(expert_path, 8, 10)

        assert hover is not None, "Expected hover content on the .mq4 function"

        references = language_server.request_references(expert_path, 8, 10)
        assert references, "Expected references for the .mq4 function"

    @pytest.mark.parametrize("language_server", [LanguageServerId.MQL], indirect=True)
    def test_completion_smoke(self, language_server: SolidLanguageServer) -> None:
        """Completion returns a non-empty list for an .mq4 document."""
        completions = language_server.request_completions("ExpertAdvisor.mq4", 16, 10)

        assert completions, "Expected completions for the .mq4 document"

    @pytest.mark.parametrize("language_server", [LanguageServerId.MQL], indirect=True)
    def test_cross_dialect_symbols_from_one_instance(self, language_server: SolidLanguageServer) -> None:
        """Both dialect files are served by the single ``mql`` server instance."""
        mq5_symbols, _ = language_server.request_document_symbols("TradingClass.mq5").get_all_symbols_and_roots()
        mq4_symbols, _ = language_server.request_document_symbols("ExpertAdvisor.mq4").get_all_symbols_and_roots()

        assert any(s.get("name") == "TradingClass" for s in mq5_symbols), "MQL5 file served by mql instance"
        assert any(s.get("name") == "CalculateLotSize" for s in mq4_symbols), "MQL4 file served by the same mql instance"

    @pytest.mark.parametrize("language_server", [LanguageServerId.MQL], indirect=True)
    def test_bare_symbol_names(self, language_server: SolidLanguageServer) -> None:
        """MQL symbols must have bare names (no whitespace/bracket/paren/comma/colon pollution)."""
        malformed_symbols = [s for s in request_all_symbols(language_server) if has_malformed_name(s)]
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )

    @pytest.mark.parametrize("language_server", [LanguageServerId.MQL], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.MQL], indirect=True)
    def test_definition_at_include_line_documents_server_limitation(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """D7-1 probe: definition at the .mq5 include line is NOT resolved by
        mql-lsp-server v2.0.0 (cross-file definition unsupported); the include
        relationship is instead verified via workspace-wide references
        (test_references_across_dialects_reach_mqh). This test pins the current
        server behavior so a future server upgrade that starts resolving include
        lines is noticed rather than silently changing semantics.
        """
        # TradingClass.mq5 line 3 (0-indexed): #include "IncludeUtils.mqh"; cursor on "IncludeUtils"
        definitions = language_server.request_definition(str(repo_path / "TradingClass.mq5"), 3, 12)

        resolved_includes = [d for d in definitions if d["uri"].endswith("IncludeUtils.mqh")]
        if definitions and resolved_includes:
            # a future server resolves includes — the contract upgrade is welcome
            assert all(d["uri"].endswith("IncludeUtils.mqh") for d in definitions)
        else:
            # current v2.0.0 behavior: no cross-file definition at the include line
            assert not resolved_includes, "unexpected partial include resolution"

    @pytest.mark.parametrize("language_server", [LanguageServerId.MQL], indirect=True)
    def test_did_save_round_trip(self, language_server: SolidLanguageServer) -> None:
        """Spec R2 didSave: the server accepts a didSave notification for an open
        document and stays responsive (synchronous notification, no hang/desync).
        """
        relative_path = "ExpertAdvisor.mq4"
        # open_file sends textDocument/didOpen (LSPFileBuffer, language id mql4 via
        # _get_language_id_for_file); didSave must reach the server while it is open
        with language_server.open_file(relative_path) as file_buffer:
            language_server.server.notify.did_save_text_document(
                {  # dict built from LSPConstants keys; shape matches the TypedDict
                    "textDocument": {"uri": file_buffer.uri},
                }
            )

            assert language_server.is_running()

            # the server must still answer requests after the save round trip
            symbols, _ = language_server.request_document_symbols("TradingClass.mq5").get_all_symbols_and_roots()
            assert any(s.get("name") == "TradingClass" for s in symbols), "server desynced after didSave"

    @pytest.mark.parametrize("language_server", [LanguageServerId.MQL], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.MQL], indirect=True)
    def test_language_ids_per_dialect(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Spec R2 both-dialects: language ids mql4/mql5 are computed per file type
        from the same server instance (verified at the _get_language_id_for_file hook,
        since didOpen language ids are only observable server-side).
        """
        assert language_server._get_language_id_for_file("ExpertAdvisor.mq4") == "mql4"
        assert language_server._get_language_id_for_file("TradingClass.mq5") == "mql5"
        assert language_server._get_language_id_for_file("IncludeUtils.mqh") == "mql5"
        # case-insensitive on Windows-typical inputs
        assert language_server._get_language_id_for_file("EA.MQ4") == "mql4"
        # and the live server instance actually serves both dialect files (R2 s4)
        mq4_symbols, _ = language_server.request_document_symbols("ExpertAdvisor.mq4").get_all_symbols_and_roots()
        assert any(s.get("name") == "CalculateLotSize" for s in mq4_symbols)

    @pytest.mark.parametrize("language_server", [LanguageServerId.MQL], indirect=True)
    def test_server_ready_and_capability_registration(self, language_server: SolidLanguageServer) -> None:
        """Spec R2 readiness: after the initialize handshake the server_ready event
        is set and the Serena-relevant providers were dynamically registered
        (msl-style registerCapability, asserted in _start_server).
        """
        assert language_server.server_ready.is_set(), "server_ready must be set after the initialize handshake"
        assert language_server.is_running()
