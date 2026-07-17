"""Basic integration tests for the CUE language server (``cue lsp``)."""

from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols


@pytest.mark.cue
class TestCueLanguageServer:
    """Verifies that ``cue lsp`` drives the symbol and reference APIs Serena depends on.

    The test repo (``test/resources/repos/cue/test_repo``) defines three CUE files that
    share package ``testrepo`` and cross-reference each other's definitions:

    - ``schema.cue`` defines ``#Person``, ``#Greeting``, ``defaultLocale``.
    - ``lib.cue`` defines ``#BuildGreeting`` (which uses ``#Person`` and ``#Greeting``) and
      ``locales``.
    - ``main.cue`` defines ``alice: #Person & {...}``, ``greetingForAlice: (#BuildGreeting & {...})``,
      and ``locale: defaultLocale``.

    Line/character positions below are 0-indexed (LSP convention) and were captured from
    ``cue lsp v0.16.1`` responses against this repository.
    """

    @pytest.mark.parametrize("language_server", [Language.CUE], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.CUE], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """The server starts and reports the expected repository root."""
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.CUE], indirect=True)
    def test_document_symbols_schema(self, language_server: SolidLanguageServer) -> None:
        """``schema.cue`` exposes its top-level definitions with the expected hierarchy."""
        # request hierarchical document symbols for schema.cue
        all_symbols, root_symbols = language_server.request_document_symbols("schema.cue").get_all_symbols_and_roots()

        # schema.cue's three top-level definitions must appear as roots
        root_names = [s.get("name") for s in root_symbols]
        for expected in ("#Person", "#Greeting", "defaultLocale"):
            assert expected in root_names, f"{expected} missing from schema.cue roots: {root_names}"

        # #Person's field children must be nested under it (hierarchical response, not flat)
        person = next(s for s in root_symbols if s.get("name") == "#Person")
        person_children = [c.get("name") for c in person.get("children", [])]
        for expected_field in ("name", "age", "email"):
            assert expected_field in person_children, f"{expected_field} missing under #Person: {person_children}"

        # fields must not also appear at root level (that would be the flat fallback)
        assert "name" not in root_names, f"name should be a child of #Person, not a root. Roots: {root_names}"

    @pytest.mark.parametrize("language_server", [Language.CUE], indirect=True)
    def test_full_symbol_tree_contains_cross_file_names(self, language_server: SolidLanguageServer) -> None:
        """The repository-wide symbol tree contains definitions from all three CUE files."""
        symbols = language_server.request_full_symbol_tree()

        for expected in (
            "#Person",  # schema.cue
            "#Greeting",  # schema.cue
            "defaultLocale",  # schema.cue
            "#BuildGreeting",  # lib.cue
            "locales",  # lib.cue
            "alice",  # main.cue
            "greetingForAlice",  # main.cue
            "locale",  # main.cue
        ):
            assert SymbolUtils.symbol_tree_contains_name(symbols, expected), f"{expected} missing from full symbol tree"

    @pytest.mark.parametrize("language_server", [Language.CUE], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.CUE], indirect=True)
    def test_find_definition_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """``#Person`` used in ``main.cue`` resolves to its definition in ``schema.cue``."""
        # main.cue line 3 (0-indexed): "alice: #Person & {"
        #                                     ^ char 7 — cursor on '#Person'
        definitions = language_server.request_definition(str(repo_path / "main.cue"), 3, 8)

        assert definitions, f"Expected a definition for #Person, got {definitions=}"
        # definition must live in schema.cue at line 3 (0-indexed), char 0
        target = definitions[0]
        assert target["uri"].endswith("schema.cue")
        assert target["range"]["start"] == {"line": 3, "character": 0}

    @pytest.mark.parametrize("language_server", [Language.CUE], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.CUE], indirect=True)
    def test_find_references_across_files_person(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """``#Person`` has references in ``lib.cue`` and ``main.cue`` beyond its declaration."""
        schema_path = str(repo_path / "schema.cue")
        # schema.cue line 3 (0-indexed): "#Person: {" — cursor on the identifier
        references = language_server.request_references(schema_path, 3, 1)

        assert references, f"Expected references for #Person, got {references=}"

        # collapse to (filename, start_line) tuples for set-based assertions
        ref_pairs = {(ref["uri"].split("/")[-1], ref["range"]["start"]["line"]) for ref in references}

        # must include use sites in lib.cue (line 5, in `for_: #Person`) and
        # main.cue (line 3, in `alice: #Person & {`)
        assert ("lib.cue", 5) in ref_pairs, f"Expected lib.cue:5 reference, got {sorted(ref_pairs)}"
        assert ("main.cue", 3) in ref_pairs, f"Expected main.cue:3 reference, got {sorted(ref_pairs)}"

    @pytest.mark.parametrize("language_server", [Language.CUE], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.CUE], indirect=True)
    def test_find_references_within_file_build_greeting(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """``#BuildGreeting`` (defined in lib.cue) is referenced from main.cue."""
        lib_path = str(repo_path / "lib.cue")
        # lib.cue line 4 (0-indexed): "#BuildGreeting: {"
        references = language_server.request_references(lib_path, 4, 1)

        assert references, f"Expected references for #BuildGreeting, got {references=}"

        ref_pairs = {(ref["uri"].split("/")[-1], ref["range"]["start"]["line"]) for ref in references}
        # use site in main.cue is line 10: "greetingForAlice: (#BuildGreeting & {for_: alice}).result"
        assert ("main.cue", 10) in ref_pairs, f"Expected main.cue:10 reference, got {sorted(ref_pairs)}"

    @pytest.mark.parametrize("language_server", [Language.CUE], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.CUE], indirect=True)
    def test_find_references_default_locale(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """``defaultLocale`` (schema.cue) is used in main.cue."""
        schema_path = str(repo_path / "schema.cue")
        # schema.cue line 16 (0-indexed): 'defaultLocale: "en-US"'
        references = language_server.request_references(schema_path, 16, 1)

        assert references, f"Expected references for defaultLocale, got {references=}"
        ref_pairs = {(ref["uri"].split("/")[-1], ref["range"]["start"]["line"]) for ref in references}
        # use site in main.cue is line 13: "locale: defaultLocale"
        assert ("main.cue", 13) in ref_pairs, f"Expected main.cue:13 reference, got {sorted(ref_pairs)}"

    @pytest.mark.parametrize("language_server", [Language.CUE], indirect=True)
    def test_bare_symbol_names(self, language_server: SolidLanguageServer) -> None:
        """CUE symbols must have bare names (no whitespace/bracket/paren/comma/colon pollution)."""
        # `.` is allowed because the synthetic directory symbol for `cue.mod/` contains a literal
        # period — CUE modules are always anchored under a directory named `cue.mod`.
        # `#` in names like `#Person` is part of the identifier in CUE's grammar and is not
        # in the forbidden-char set.
        malformed_symbols = [s for s in request_all_symbols(language_server) if has_malformed_name(s, period_allowed=True)]
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )
