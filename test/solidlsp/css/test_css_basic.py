"""
Basic integration tests for the CSS language server.

The CSS LSP (vscode-css-language-server) returns each top-level rule (selector)
as a document symbol. Cross-file ``@import`` navigation is limited and is not
exercised here.
"""

from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.lsp_protocol_handler import lsp_types as LSPTypes
from test.solidlsp.conftest import find_in_file, request_all_symbols


@pytest.mark.css
class TestCssLanguageServerBasics:
    @pytest.mark.parametrize("language_server", [Language.CSS], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.CSS], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.CSS], indirect=True)
    def test_main_document_symbols(self, language_server: SolidLanguageServer) -> None:
        all_symbols, _ = language_server.request_document_symbols("main.css").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        joined = " | ".join(names)
        for selector in ("body", "#page-header", "#site-title", ".button", ".button-primary", ".button-secondary"):
            assert selector in joined, f"Expected selector '{selector}' to appear in CSS symbols: {names}"

    @pytest.mark.parametrize("language_server", [Language.CSS], indirect=True)
    def test_theme_document_symbols(self, language_server: SolidLanguageServer) -> None:
        all_symbols, _ = language_server.request_document_symbols("theme.css").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        joined = " | ".join(names)
        assert ":root" in joined, f"Expected ':root' selector to appear in CSS symbols: {names}"

    @pytest.mark.parametrize("language_server", [Language.CSS], indirect=True)
    def test_full_symbol_tree_includes_all_files(self, language_server: SolidLanguageServer) -> None:
        all_symbols = request_all_symbols(language_server)
        relative_paths = {s.get("location", {}).get("relativePath") for s in all_symbols}
        for f in ("main.css", "reset.css", "theme.css"):
            assert f in relative_paths, f"Expected {f} to appear in symbol tree"


@pytest.mark.css
class TestCssHover:
    """vscode-css-language-server returns MDN-backed hover content for properties."""

    @pytest.mark.parametrize("language_server", [Language.CSS], indirect=True)
    def test_hover_on_property_name(self, language_server: SolidLanguageServer) -> None:
        path = "main.css"
        line, col = find_in_file(language_server, path, "background-color")
        hover = language_server.request_hover(path, line, col + 2)
        assert hover is not None, f"Expected hover info for background-color in {path}, got None"
        contents = hover.get("contents")
        assert contents, f"Expected non-empty hover contents, got: {hover}"
        text = contents["value"] if isinstance(contents, dict) else str(contents)
        assert "background" in text.lower(), f"Expected hover text to mention 'background', got: {text}"


@pytest.mark.css
class TestCssCompletions:
    """The CSS LSP offers property and value completions inside declaration blocks."""

    @pytest.mark.parametrize("language_server", [Language.CSS], indirect=True)
    def test_property_completion_inside_rule(self, language_server: SolidLanguageServer) -> None:
        """Inside a rule body, the LSP must offer standard CSS property names."""
        # Position the cursor at the start of a property line. We use the `padding`
        # declaration in `.button` (line index lookup avoids hardcoding coords).
        path = "main.css"
        line, col = find_in_file(language_server, path, "padding:")
        # Invoke completion at the column where the property name begins so the LSP
        # treats the request as a property-name lookup.
        completions = language_server.request_completions(path, line, col)
        labels = {c.get("completionText", "") for c in completions}
        # Common standard properties should always be offered in a rule body.
        assert any(label in labels for label in ("padding", "margin", "color", "border")), (
            f"Expected at least one common property name in completions, got sample: {sorted(labels)[:20]}"
        )


@pytest.mark.css
class TestCssSymbolKinds:
    """vscode-css-language-server reports each top-level rule as a class-like symbol."""

    @pytest.mark.parametrize("language_server", [Language.CSS], indirect=True)
    def test_selector_symbol_kind(self, language_server: SolidLanguageServer) -> None:
        all_symbols, _ = language_server.request_document_symbols("main.css").get_all_symbols_and_roots()
        button = next((s for s in all_symbols if s["name"] == ".button"), None)
        assert button is not None, f"Did not find '.button' selector in {[s['name'] for s in all_symbols]}"
        # vscode-css-language-server emits selectors as Class (per upstream behaviour).
        # If the upstream changes this to Module/Object, the test should still recognise
        # the kind as a structural container — reject Variable/Method/Property which
        # would indicate a regression.
        kind = LSPTypes.SymbolKind(button["kind"])
        forbidden = {
            LSPTypes.SymbolKind.Variable,
            LSPTypes.SymbolKind.Method,
            LSPTypes.SymbolKind.Function,
            LSPTypes.SymbolKind.Property,
            LSPTypes.SymbolKind.Field,
        }
        assert kind not in forbidden, f"Selector '.button' reported as {kind.name}, expected a structural kind (Class/Module/Object/Struct)"
