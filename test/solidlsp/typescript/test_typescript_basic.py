import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_utils import SymbolUtils
from test.conftest import find_identifier_position, get_repo_path, ls_has_verified_implementation_support
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols


@pytest.mark.typescript
class TestTypescriptLanguageServer:
    @pytest.mark.parametrize("language_server", [LanguageServerId.TYPESCRIPT], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "DemoClass"), "DemoClass not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "helperFunction"), "helperFunction not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "printValue"), "printValue method not found in symbol tree"

    @pytest.mark.parametrize("language_server", [LanguageServerId.TYPESCRIPT], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("index.ts")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        helper_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "helperFunction":
                helper_symbol = sym
                break
        assert helper_symbol is not None, "Could not find 'helperFunction' symbol in index.ts"
        sel_start = helper_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert any("index.ts" in ref.get("relativePath", "") for ref in refs), (
            "index.ts should reference helperFunction (tried all positions in selectionRange)"
        )

    @pytest.mark.parametrize("language_server", [LanguageServerId.TYPESCRIPT], indirect=True)
    def test_const_let_var_body_includes_leading_keyword_and_trailing_semicolon(self, language_server: SolidLanguageServer) -> None:
        """
        Single top-level ``const``/``let``/``var`` declarations must expose a body and replacement
        range that include a leading ``export`` (if present), the declaration keyword, and the
        trailing statement-terminating semicolon, just like ``function``/``class`` declarations
        already do (for the keyword; they are not semicolon-terminated).

        Regression test for tsserver reporting the symbol range of such declarations starting at
        the declared identifier (after the keyword(s)) and ending before the semicolon, rather
        than spanning the full statement. That asymmetry made replace_symbol_body drop the prefix
        and the semicolon from the body and replacement range, so a natural round-trip edit either
        duplicated the prefix and corrupted the file (``export const twice = ...`` ->
        ``export const export const twice = ...``) or, once only the prefix was fixed, left a
        harmless but incorrect double semicolon behind (``... n * 3;;``). GH #1956.
        """
        all_symbols, _ = language_server.request_document_symbols("symbol_body.ts").get_all_symbols_and_roots()
        symbols_by_name = {sym.get("name"): sym for sym in all_symbols}

        # single declarations: body starts with the full keyword prefix and ends with the
        # semicolon, the range start moves to the keyword (column 0 here), the range end moves
        # past the semicolon, and the selection range still points at the identifier
        expected_prefix_by_name = {
            "twice": "export const ",
            "localCounter": "const ",
            "mutableFlag": "export let ",
            "legacyVar": "var ",
        }
        for name, prefix in expected_prefix_by_name.items():
            sym = symbols_by_name.get(name)
            assert sym is not None, f"{name} not found in symbol_body.ts"
            body = sym["body"].get_text()
            assert body.startswith(prefix), f"Expected body of {name} to start with {prefix!r}, got {body[:24]!r}"
            assert body.endswith(";"), f"Expected body of {name} to end with a semicolon, got {body[-8:]!r}"
            assert sym["location"]["range"]["start"]["character"] == 0, f"Expected {name} body range to start at the keyword (col 0)"
            assert sym["selectionRange"]["start"]["character"] > 0, f"Expected {name} selectionRange to point at the identifier"

        # function/class declarations already include their keyword in tsserver's own range and
        # are not semicolon-terminated; this override must be a no-op for them
        for name in ("helperFunction", "HelperClass"):
            sym = symbols_by_name.get(name)
            assert sym is not None, f"{name} not found in symbol_body.ts"
            body = sym["body"].get_text()
            assert body.startswith("export "), f"Expected {name} body to already start with 'export ', got {body[:24]!r}"
            assert not body.endswith(";"), f"Expected {name} body to not have gained a trailing semicolon, got {body[-8:]!r}"

    if ls_has_verified_implementation_support(LanguageServerId.TYPESCRIPT):

        @pytest.mark.parametrize("language_server", [LanguageServerId.TYPESCRIPT], indirect=True)
        def test_find_implementations(self, language_server: SolidLanguageServer) -> None:
            repo_path = get_repo_path(LanguageServerId.TYPESCRIPT)
            pos = find_identifier_position(repo_path / "formatters.ts", "formatGreeting")
            assert pos is not None, "Could not find Greeter.formatGreeting in fixture"

            implementations = language_server.request_implementation("formatters.ts", *pos)
            assert implementations, "Expected at least one implementation of Greeter.formatGreeting"
            assert any("formatters.ts" in implementation.get("relativePath", "") for implementation in implementations), (
                f"Expected ConsoleGreeter.formatGreeting in implementations, got: {implementations}"
            )

        @pytest.mark.parametrize("language_server", [LanguageServerId.TYPESCRIPT], indirect=True)
        def test_request_implementing_symbols(self, language_server: SolidLanguageServer) -> None:
            repo_path = get_repo_path(LanguageServerId.TYPESCRIPT)
            pos = find_identifier_position(repo_path / "formatters.ts", "formatGreeting")
            assert pos is not None, "Could not find Greeter.formatGreeting in fixture"

            implementing_symbols = language_server.request_implementing_symbols("formatters.ts", *pos)
            assert implementing_symbols, "Expected implementing symbols for Greeter.formatGreeting"
            assert any(
                symbol.get("name") == "formatGreeting" and "formatters.ts" in symbol["location"].get("relativePath", "")
                for symbol in implementing_symbols
            ), f"Expected ConsoleGreeter.formatGreeting symbol, got: {implementing_symbols}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.TYPESCRIPT], indirect=True)
    def test_tsx_symbol_range_not_truncated_by_jsx(self, language_server: SolidLanguageServer) -> None:
        # Regression: when the language id is sent as "typescript" instead of
        # "typescriptreact" for .tsx files, tsserver parses JSX as syntax
        # errors and recovers by truncating the enclosing symbol's range at
        # the first multi-line JSX expression. find_symbol then returns a
        # body that ends mid-component and hides everything below.
        file_path = "jsx_component.tsx"
        roots = language_server.request_document_symbols(file_path).root_symbols

        jsx_component = next((s for s in roots if s.get("name") == "JsxComponent"), None)
        assert jsx_component is not None, "JsxComponent not found at root level of jsx_component.tsx"

        end_line = jsx_component["location"]["range"]["end"]["line"]
        # JsxComponent's body extends to line 38 (0-based 37) in the fixture;
        # the truncation bug cut it at the first multi-line JSX (~line 21).
        # Use a generous lower bound so the test survives small fixture edits
        # that don't affect the regression behaviour we care about.
        assert end_line >= 30, (
            f"JsxComponent symbol range truncated at line {end_line + 1} (1-based); "
            f"expected end at or past line 31 (1-based). "
            f"This indicates the .tsx file was opened with the wrong languageId."
        )

        # The trailing helper must be visible as a top-level symbol — it lives
        # past the truncation point and disappears entirely when the bug is
        # active because tsserver stops emitting symbols after the parse error.
        assert any(s.get("name") == "trailingHelper" for s in roots), (
            "trailingHelper missing from jsx_component.tsx root symbols; tsserver likely stopped parsing at the first JSX expression."
        )

    @pytest.mark.parametrize("language_server", [LanguageServerId.TYPESCRIPT], indirect=True)
    def test_bare_symbol_names(self, language_server) -> None:
        all_symbols = request_all_symbols(language_server)
        malformed_symbols = []
        for s in all_symbols:
            if has_malformed_name(s):
                malformed_symbols.append(s)
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )
