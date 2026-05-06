"""
Basic integration tests for the SCSS language server (Some Sass).

Some Sass provides full @use/@forward workspace navigation, so this suite
exercises both in-file document symbols and cross-file go-to-definition for
variables and mixins.
"""

import os
import re
from pathlib import Path

import pytest

from serena.util.text_utils import find_text_coordinates
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind
from solidlsp.lsp_protocol_handler import lsp_types as LSPTypes
from test.solidlsp.conftest import read_repo_file, request_all_symbols


@pytest.mark.scss
class TestScssLanguageServerBasics:
    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.SCSS], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_variables_document_symbols(self, language_server: SolidLanguageServer) -> None:
        all_symbols, _ = language_server.request_document_symbols("_variables.scss").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        for var in ("$color-primary", "$color-secondary", "$color-text", "$space-md", "$space-lg"):
            assert var in names, f"Expected variable {var} to appear in SCSS symbols: {names}"

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_mixins_document_symbols(self, language_server: SolidLanguageServer) -> None:
        all_symbols, _ = language_server.request_document_symbols("_mixins.scss").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        # Some Sass surfaces @mixin and @function entries; names may be bare ("card-surface")
        # or include the @-keyword. Check substring inclusion for robustness.
        joined = " | ".join(names)
        for expected in ("card-surface", "focus-ring", "rem"):
            assert expected in joined, f"Expected '{expected}' to appear in SCSS mixin symbols: {names}"

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_buttons_document_symbols(self, language_server: SolidLanguageServer) -> None:
        all_symbols, _ = language_server.request_document_symbols("buttons.scss").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        joined = " | ".join(names)
        for selector in (".button", ".button-primary", ".button-secondary"):
            assert selector in joined, f"Expected selector '{selector}' to appear in SCSS symbols: {names}"

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_cross_file_definition_variable(self, language_server: SolidLanguageServer) -> None:
        """`vars.$color-text` in buttons.scss must resolve into _variables.scss."""
        path = "buttons.scss"
        needle = "$color-text"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        # Cursor inside the variable identifier.
        definitions = language_server.request_definition(path, line, col + 2)
        assert definitions, f"Expected non-empty cross-file definition list for vars.$color-text, got {definitions}"
        target_uris = [d["uri"] for d in definitions]
        assert any(uri.endswith("_variables.scss") for uri in target_uris), (
            f"Expected definition to resolve into _variables.scss, got URIs: {target_uris}"
        )

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_cross_file_definition_mixin(self, language_server: SolidLanguageServer) -> None:
        """`mix.card-surface` in buttons.scss must resolve into _mixins.scss."""
        path = "buttons.scss"
        needle = "card-surface"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        definitions = language_server.request_definition(path, line, col + 2)
        assert definitions, f"Expected non-empty cross-file definition list for mix.card-surface, got {definitions}"
        target_uris = [d["uri"] for d in definitions]
        assert any(uri.endswith("_mixins.scss") for uri in target_uris), (
            f"Expected definition to resolve into _mixins.scss, got URIs: {target_uris}"
        )

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_cross_file_definition_function(self, language_server: SolidLanguageServer) -> None:
        """`mix.rem(16)` in main.scss must resolve into _mixins.scss (an @function)."""
        path = "main.scss"
        needle = "mix.rem"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        # Cursor inside the function identifier (skip the `mix.` prefix).
        definitions = language_server.request_definition(path, line, col + 5)
        assert definitions, f"Expected non-empty cross-file definition list for mix.rem, got {definitions}"
        target_uris = [d["uri"] for d in definitions]
        assert any(uri.endswith("_mixins.scss") for uri in target_uris), (
            f"Expected definition to resolve into _mixins.scss, got URIs: {target_uris}"
        )

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_full_symbol_tree_includes_all_files(self, language_server: SolidLanguageServer) -> None:
        all_symbols = request_all_symbols(language_server)
        relative_paths = {s.get("location", {}).get("relativePath") for s in all_symbols}
        for f in ("_variables.scss", "_mixins.scss", "buttons.scss", "main.scss"):
            assert f in relative_paths, f"Expected {f} to appear in symbol tree"


@pytest.mark.scss
class TestScssReferences:
    """Find-references for symbols re-exported via @use across files."""

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_mixin_references_span_files(self, language_server: SolidLanguageServer) -> None:
        """References for ``card-surface`` must include both ``buttons.scss``
        (`.button`, `.button-primary`, `.button-secondary` all `@include` it) and
        ``main.scss`` (`.panel` `@include`s it).

        Some Sass returns no references when the request originates on the
        ``@mixin`` declaration itself, so we probe from a usage site in
        ``buttons.scss`` — that's also closer to how an editor user invokes
        find-references in practice.
        """
        path = "buttons.scss"
        needle = "card-surface"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        refs = language_server.request_references(path, line, col + 2)
        ref_paths = {r.get("relativePath", "") for r in refs}
        assert any(p.endswith("buttons.scss") for p in ref_paths), (
            f"Expected card-surface references to include buttons.scss, got: {ref_paths}"
        )
        assert any(p.endswith("main.scss") for p in ref_paths), f"Expected card-surface references to include main.scss, got: {ref_paths}"

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_variable_references_span_files(self, language_server: SolidLanguageServer) -> None:
        """`$color-primary` is read in ``buttons.scss`` (`.button-primary` background)
        and ``_mixins.scss`` (default value of ``focus-ring``); references invoked
        from the ``buttons.scss`` usage site must include both files.
        """
        path = "buttons.scss"
        needle = "$color-primary"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        refs = language_server.request_references(path, line, col + 2)
        ref_paths = {r.get("relativePath", "") for r in refs}
        assert any(p.endswith("buttons.scss") for p in ref_paths), (
            f"Expected $color-primary references to include buttons.scss, got: {ref_paths}"
        )
        assert any(p.endswith("_mixins.scss") for p in ref_paths), (
            f"Expected $color-primary references to include _mixins.scss (default param of focus-ring), got: {ref_paths}"
        )


@pytest.mark.scss
class TestScssForward:
    """`@forward` re-exports a module; consumers should reach forwarded symbols."""

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_forwarded_buttons_appear_in_workspace(self, language_server: SolidLanguageServer) -> None:
        """``main.scss`` does ``@forward "buttons"``; the workspace symbol tree must
        still include ``buttons.scss`` selectors so consumers of `main` can navigate.
        """
        all_symbols = request_all_symbols(language_server)
        button_symbols = [s for s in all_symbols if s.get("location", {}).get("relativePath") == "buttons.scss"]
        names = [s["name"] for s in button_symbols]
        joined = " | ".join(names)
        assert ".button" in joined, f"Expected .button selector to remain reachable via @forward, got: {names}"


@pytest.mark.scss
class TestScssHover:
    """Some Sass returns rich hover content (SassDoc / value preview)."""

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_hover_on_variable_use(self, language_server: SolidLanguageServer) -> None:
        path = "buttons.scss"
        needle = "$color-text"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        hover = language_server.request_hover(path, line, col + 2)
        assert hover is not None, f"Expected hover info for $color-text in {path}, got None"
        contents = hover.get("contents")
        assert contents, f"Expected non-empty hover contents, got: {hover}"
        text = contents["value"] if isinstance(contents, dict) else str(contents)
        assert "color-text" in text, f"Expected '$color-text' or its value in hover text, got: {text}"

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_hover_on_mixin_call(self, language_server: SolidLanguageServer) -> None:
        path = "buttons.scss"
        needle = "card-surface"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        hover = language_server.request_hover(path, line, col + 2)
        assert hover is not None, f"Expected hover info for card-surface in {path}, got None"
        contents = hover.get("contents")
        assert contents, f"Expected non-empty hover contents, got: {hover}"
        text = contents["value"] if isinstance(contents, dict) else str(contents)
        assert "card-surface" in text, f"Expected 'card-surface' in hover text, got: {text}"


@pytest.mark.scss
class TestScssCompletions:
    """Completions after a namespaced @use prefix should list re-exported members."""

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_completion_after_namespace_dot(self, language_server: SolidLanguageServer) -> None:
        """Completion immediately after `vars.` in buttons.scss must include the
        variables defined in _variables.scss (e.g. ``$color-primary``).
        """
        path = "buttons.scss"
        # `color: vars.$color-text;` — invoke completion at the `.` position so the
        # LSP sees the namespace prefix and offers its members.
        needle = "vars.$color-text"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        # Position the cursor right after the `.` (4 chars: 'v','a','r','s','.' -> idx 5)
        completions = language_server.request_completions(path, line, col + 5)
        labels = {c.get("completionText", "") for c in completions}
        # Different Some Sass releases label vars with or without leading $; accept both.
        joined = " | ".join(sorted(labels))
        assert any("color-primary" in label for label in labels), f"Expected $color-primary completion after `vars.` prefix, got: {joined}"


@pytest.mark.scss
class TestScssSymbolKinds:
    """Validate that Some Sass classifies SCSS symbols with sensible LSP kinds."""

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_variable_symbol_kind(self, language_server: SolidLanguageServer) -> None:
        all_symbols, _ = language_server.request_document_symbols("_variables.scss").get_all_symbols_and_roots()
        by_name = {s["name"]: s for s in all_symbols}
        assert "$color-primary" in by_name, f"Variable not in symbol list: {list(by_name)}"
        kind = SymbolKind(by_name["$color-primary"]["kind"])
        assert kind in (SymbolKind.Variable, SymbolKind.Constant, SymbolKind.Property), (
            f"Expected $color-primary to be Variable/Constant/Property, got {kind.name}"
        )

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_mixin_and_function_symbol_kinds(self, language_server: SolidLanguageServer) -> None:
        all_symbols, _ = language_server.request_document_symbols("_mixins.scss").get_all_symbols_and_roots()

        # Names may include the @-keyword (e.g. "@mixin card-surface") or be bare;
        # match by substring.
        def find_one(needle: str) -> dict:
            matches = [s for s in all_symbols if needle in s["name"]]
            assert matches, f"No symbol matched '{needle}' in {[s['name'] for s in all_symbols]}"
            return matches[0]

        mixin = find_one("card-surface")
        func = find_one("rem")
        # Some Sass historically reports mixins/functions as Method or Function.
        # Accept either, but reject obviously-wrong kinds (e.g. Variable/Class).
        callable_kinds = {SymbolKind.Method, SymbolKind.Function}
        assert SymbolKind(mixin["kind"]) in callable_kinds, (
            f"Expected card-surface kind in {{Method, Function}}, got {SymbolKind(mixin['kind']).name}"
        )
        assert SymbolKind(func["kind"]) in callable_kinds, f"Expected rem kind in {{Method, Function}}, got {SymbolKind(func['kind']).name}"

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_completion_kind_is_meaningful(self, language_server: SolidLanguageServer) -> None:
        """A `$variable` completion must come back with a meaningful kind. Some Sass
        tags color-valued variables as ``Color`` (so editors render swatches) and
        non-color variables as ``Variable``/``Property``/``Constant`` — accept any
        of these but reject generic ``Text`` which would indicate the LSP failed
        to classify the completion.
        """
        path = "buttons.scss"
        needle = "vars.$color-text"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        completions = language_server.request_completions(path, line, col + 5)
        var_items = [c for c in completions if "color-primary" in c.get("completionText", "")]
        assert var_items, "no $color-primary completion item found"
        accepted = {
            LSPTypes.CompletionItemKind.Variable,
            LSPTypes.CompletionItemKind.Property,
            LSPTypes.CompletionItemKind.Constant,
            LSPTypes.CompletionItemKind.Color,
            LSPTypes.CompletionItemKind.Value,
        }
        kinds = {LSPTypes.CompletionItemKind(c["kind"]).name for c in var_items}
        assert any(LSPTypes.CompletionItemKind(c["kind"]) in accepted for c in var_items), (
            f"Expected variable-like CompletionItemKind for $color-primary, got: {kinds}"
        )


# --- Plain CSS via Some Sass --------------------------------------------------
#
# Some Sass advertises the LSP ``css`` languageId as a first-class consumer (see
# ``packages/language-services/src/language-services-types.ts:LanguageConfiguration``)
# and dispatches per-feature handlers via the ``somesass.css.*.enabled`` toggles —
# all of which default to ``false`` upstream and which Serena flips on at init.
# These tests verify the routing actually works end-to-end against a small CSS
# fixture under ``css/`` in the same SCSS test repo.


@pytest.mark.scss
class TestSomeSassWithPlainCss:
    """``Language.SCSS`` also handles plain ``.css`` via ``some-sass-language-server``."""

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_main_css_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Each top-level rule selector in ``main.css`` must surface as a document symbol."""
        all_symbols, _ = language_server.request_document_symbols("css/main.css").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        joined = " | ".join(names)
        for selector in ("body", "#page-header", "#site-title", ".button", ".button-primary", ".button-secondary"):
            assert selector in joined, f"Expected selector '{selector}' to appear in CSS symbols: {names}"

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_theme_css_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """``theme.css`` contains a single ``:root`` block; the LS must report it as a symbol."""
        all_symbols, _ = language_server.request_document_symbols("css/theme.css").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        joined = " | ".join(names)
        assert ":root" in joined, f"Expected ':root' selector to appear in CSS symbols: {names}"

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_full_symbol_tree_includes_css_files(self, language_server: SolidLanguageServer) -> None:
        """The ``.css`` files alongside the SCSS workspace must populate the workspace symbol tree."""
        all_symbols = request_all_symbols(language_server)
        relative_paths = {s.get("location", {}).get("relativePath") for s in all_symbols}
        # `relativePath` uses OS-native separators (cf. test_symbol_retrieval.py),
        # so build expected paths via os.path.join to keep this test cross-platform.
        for f in (os.path.join("css", "main.css"), os.path.join("css", "reset.css"), os.path.join("css", "theme.css")):
            assert f in relative_paths, f"Expected {f} to appear in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_hover_on_css_property(self, language_server: SolidLanguageServer) -> None:
        """Hover on a CSS property name must produce non-empty MDN-backed content
        (Some Sass forwards ``vscode-css-languageservice``'s property reference data).
        """
        path = "css/main.css"
        needle = "background-color"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        hover = language_server.request_hover(path, line, col + 2)
        assert hover is not None, f"Expected hover info for background-color in {path}, got None"
        contents = hover.get("contents")
        assert contents, f"Expected non-empty hover contents, got: {hover}"
        text = contents["value"] if isinstance(contents, dict) else str(contents)
        assert "background" in text.lower(), f"Expected hover text to mention 'background', got: {text}"

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_property_completion_in_css_rule(self, language_server: SolidLanguageServer) -> None:
        """Inside a CSS rule body the LS must offer standard property names —
        proves ``somesass.css.completion.enabled = true`` is being honoured.
        """
        path = "css/main.css"
        needle = "padding:"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        completions = language_server.request_completions(path, line, col)
        labels = {c.get("completionText", "") for c in completions}
        assert any(label in labels for label in ("padding", "margin", "color", "border")), (
            f"Expected at least one common CSS property name in completions, got sample: {sorted(labels)[:20]}"
        )

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_cross_file_completion_for_css_custom_property(self, language_server: SolidLanguageServer) -> None:
        """Completion inside a ``var(...)`` call in ``main.css`` must surface the
        ``--color-*`` custom properties declared in ``theme.css``.

        This is the single test that empirically validates Some Sass crosses file
        boundaries for plain CSS — without ``somesass.css.completion.enabled = true``
        the request would short-circuit to ``null`` at the handler entrypoint.

        Note: ``vscode-css-languageservice`` (Some Sass' CSS engine) deliberately
        does NOT implement go-to-definition for CSS custom properties yet — see
        microsoft/vscode-css-languageservice#734. Completion is the closest
        upstream-supported API that proves cross-file awareness.
        """
        path = "css/main.css"
        # ``    color: var(--color-text);`` — invoke completion right after the
        # leading dashes so the LS treats the request as a partial custom-property
        # identifier and offers matching declarations from the workspace.
        needle = "var(--color-text"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        line, col = coords.line, coords.col
        cursor_col = col + len("var(--")
        completions = language_server.request_completions(path, line, cursor_col)
        labels = {c.get("completionText", "") for c in completions}
        joined = " | ".join(sorted(labels))
        assert any("--color-primary" in label for label in labels), (
            f"Expected --color-primary completion (declared cross-file in theme.css), got: {joined}"
        )
