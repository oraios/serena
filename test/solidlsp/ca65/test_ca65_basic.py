"""Basic integration tests for the CA65 language server (ca65-ls).

These exercise the must-have LSP methods Serena's symbolic agent tools depend on:

  * `request_document_symbols`  -> drives get_symbols_overview
  * `request_definition`        -> drives goto-definition / find_symbol resolution
  * `request_references`        -> drives find_referencing_symbols

The fixture corpus is at `test/resources/repos/ca65/test_repo/` and exercises
.proc / .scope / .import / .export / .macro / .struct / cheap-locals / anonymous-labels.
"""

from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.conftest import language_tests_enabled

pytestmark = [
    pytest.mark.ca65,
    pytest.mark.skipif(not language_tests_enabled(Language.CA65), reason="CA65 tests disabled (cc65 not installed?)"),
]


@pytest.mark.ca65
class TestCa65LanguageServer:
    """End-to-end tests against the bundled ca65-ls daemon."""

    @pytest.mark.parametrize("language_server", [Language.CA65], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.CA65], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.CA65], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.CA65], indirect=True)
    def test_document_symbols_helpers_scope(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """`get_symbols_overview` on helpers.s must surface the .scope and its nested .procs."""
        file_path = str(Path("src") / "helpers.s")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        _all_symbols, root_symbols = symbols

        root_names = [s.get("name") for s in root_symbols]
        # The synthetic corpus has a .struct S, a .macro mac1, and a .scope helpers
        # all at top level — every one must be visible to Serena.
        assert "helpers" in root_names, f"missing 'helpers' scope; got {root_names}"
        assert "S" in root_names, f"missing 'S' struct; got {root_names}"
        assert "mac1" in root_names, f"missing 'mac1' macro; got {root_names}"

        # The helpers scope must expose its nested .procs as children
        helpers = next(s for s in root_symbols if s.get("name") == "helpers")
        child_names = [c.get("name") for c in (helpers.get("children") or [])]
        assert "foo" in child_names, f"helpers.children missing 'foo'; got {child_names}"
        assert "bar" in child_names, f"helpers.children missing 'bar'; got {child_names}"

    @pytest.mark.parametrize("language_server", [Language.CA65], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.CA65], indirect=True)
    def test_definition_crosses_module_boundary(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """`request_definition` on `jsr lib_export` in main.s must jump to lib.s."""
        main_path = str(Path("src") / "main.s")
        # main.s line 15 (1-indexed) is `        jsr     lib_export` -- 0-indexed: line 14.
        # `lib_export` starts at column 16 (8-space indent + "jsr" + 5-space gap).
        definitions = language_server.request_definition(main_path, 14, 18)
        assert definitions, f"expected definitions, got {definitions}"
        # The defining file must be lib.s -- crossing the .import boundary.
        uris = {d["uri"] for d in definitions}
        assert any(u.endswith("src/lib.s") for u in uris), f"got {uris}"

    @pytest.mark.parametrize("language_server", [Language.CA65], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.CA65], indirect=True)
    def test_references_finds_cross_file_use(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """`request_references` on lib_export's definition in lib.s must find the use in main.s."""
        lib_path = str(Path("src") / "lib.s")
        # lib.s line 14 (1-indexed) is `.proc lib_export` -- 0-indexed: line 13.
        # `lib_export` starts at column 6 (after ".proc ").
        references = language_server.request_references(lib_path, 13, 8)
        assert references, f"expected references for lib_export, got {references}"
        uris = {r["uri"] for r in references}
        # At least one reference must be in main.s (the .import declarator or jsr site).
        assert any(u.endswith("src/main.s") for u in uris), f"references not in main.s: {uris}"

    @pytest.mark.parametrize("language_server", [Language.CA65], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.CA65], indirect=True)
    def test_definition_of_proc_in_scope(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Goto-definition on `helpers_foo` in main.s resolves to the alias in helpers.s.

        The alias `.export helpers_foo := helpers::foo` is module-scope in helpers.s.
        Serena must be able to resolve the .import across the module boundary.
        """
        main_path = str(Path("src") / "main.s")
        # main.s line 16 (1-indexed) `        jsr     helpers_foo` -- 0-indexed: line 15
        definitions = language_server.request_definition(main_path, 15, 18)
        assert definitions, f"expected definitions, got {definitions}"
        uris = {d["uri"] for d in definitions}
        assert any(u.endswith("src/helpers.s") for u in uris), f"got {uris}"
