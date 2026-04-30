"""
Basic integration tests for the SCSS language server (Some Sass).

Some Sass provides full @use/@forward workspace navigation, so this suite
exercises both in-file document symbols and cross-file go-to-definition for
variables and mixins.
"""

from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.conftest import request_all_symbols


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
        """Resolve `vars.$color-primary` in buttons.scss to its definition in _variables.scss.

        buttons.scss layout (LSP coordinates are 0-based):
            line 0: @use "variables" as vars;
            line 1: @use "mixins" as mix;
            line 2:
            line 3: .button {
            line 4:     @include mix.card-surface();
            line 5:     color: vars.$color-text;
        We point at the `$color-text` token in `vars.$color-text` on line 5.
        """
        path = "buttons.scss"
        # Cursor inside `$color-text`. Column ~17 lands inside the variable name.
        definitions = language_server.request_definition(path, 5, 17)
        assert definitions, f"Expected non-empty cross-file definition list for vars.$color-text, got {definitions}"
        target_uris = [d["uri"] for d in definitions]
        assert any(uri.endswith("_variables.scss") for uri in target_uris), (
            f"Expected definition to resolve into _variables.scss, got URIs: {target_uris}"
        )

    @pytest.mark.parametrize("language_server", [Language.SCSS], indirect=True)
    def test_cross_file_definition_mixin(self, language_server: SolidLanguageServer) -> None:
        """Resolve `mix.card-surface` in buttons.scss to its definition in _mixins.scss.

        Line 4: `    @include mix.card-surface();` — we point inside `card-surface`.
        """
        path = "buttons.scss"
        # Column ~22 lands inside `card-surface`.
        definitions = language_server.request_definition(path, 4, 22)
        assert definitions, f"Expected non-empty cross-file definition list for mix.card-surface, got {definitions}"
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
