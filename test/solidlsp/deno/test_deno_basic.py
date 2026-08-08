from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_types import Hover
from solidlsp.ls_utils import SymbolUtils
from test.conftest import language_server_tests_enabled


def _hover_text(hover: Hover | None) -> str:
    """Flatten the hover contents (markup object, plain string or list of either) into one string."""
    assert hover is not None, "Expected hover information, got None"
    contents = hover["contents"]
    items = contents if isinstance(contents, list) else [contents]
    return "\n".join(item if isinstance(item, str) else item["value"] for item in items)


@pytest.mark.skipif(not language_server_tests_enabled(LanguageServerId.DENO), reason="Deno tests are disabled (deno not available)")
@pytest.mark.deno
class TestDenoLanguageServer:
    @pytest.mark.parametrize("language_server", [LanguageServerId.DENO], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.DENO], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [LanguageServerId.DENO], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.DENO], indirect=True)
    def test_find_definition_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        # main.ts line 4 (0-indexed): "    return add(a, b);" — cursor on `add` (char 11).
        # `add` is defined in util.ts at line 0.
        definitions = language_server.request_definition(str(repo_path / "main.ts"), 4, 11)

        assert definitions, f"Expected a definition for `add`, got {definitions=}"
        definition = definitions[0]
        assert definition["uri"].endswith("util.ts")
        assert definition["range"]["start"]["line"] == 0

    @pytest.mark.parametrize("language_server", [LanguageServerId.DENO], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.DENO], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        # `add` is defined in util.ts line 0 at char len("export function ") == 16.
        references = language_server.request_references(str(repo_path / "util.ts"), 0, len("export function "))

        assert references, f"Expected references for `add`, got {references=}"
        locations = [(ref["uri"].split("/")[-1], ref["range"]["start"]["line"]) for ref in references]
        # The usage inside Calculator.sum lives on line 4 of main.ts.
        assert ("main.ts", 4) in locations, f"Expected a reference in main.ts line 4, got {locations}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.DENO], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.DENO], indirect=True)
    def test_document_symbols(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        all_symbols, _roots = language_server.request_document_symbols("main.ts").get_all_symbols_and_roots()
        names = [sym.get("name") for sym in all_symbols]
        assert "Calculator" in names, f"Calculator not found in main.ts document symbols: {names}"
        assert "sum" in names, f"sum not found in main.ts document symbols: {names}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.DENO], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.DENO], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Calculator"), "Calculator not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "add"), "add not found in symbol tree"

    @pytest.mark.parametrize("language_server", [LanguageServerId.DENO], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.DENO], indirect=True)
    def test_hover_reports_function_signature(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        # `add` is defined in util.ts line 0 at char len("export function ") == 16.
        hover = language_server.request_hover(str(repo_path / "util.ts"), 0, len("export function "))

        text = _hover_text(hover)
        assert "add" in text, f"Hover should name the function, got: {text}"
        assert "(a: number, b: number): number" in text, f"Hover should carry the signature, got: {text}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.DENO], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.DENO], indirect=True)
    def test_hover_resolves_deno_global(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """The `Deno.*` namespace is what this server adds over the plain TypeScript one, so it must resolve."""
        main = repo_path / "main.ts"
        lines = main.read_text(encoding="utf-8").splitlines()
        line = next(i for i, content in enumerate(lines) if "Deno.cwd()" in content)

        hover = language_server.request_hover(str(main), line, lines[line].index("Deno.cwd") + len("Deno."))

        text = _hover_text(hover)
        assert "cwd" in text, f"Hover should resolve Deno.cwd, got: {text}"
        assert "string" in text, f"Hover should carry Deno.cwd's return type, got: {text}"
