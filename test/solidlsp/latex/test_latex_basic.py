"""Basic tests for the texlab-based LaTeX language server."""

import pytest

from serena.symbol import LanguageServerSymbol
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.latex
class TestLatexLanguageServerBasics:
    """Basic functionality of the LaTeX (texlab) language server."""

    @pytest.mark.parametrize("language_server", [Language.LATEX], indirect=True)
    def test_document_symbols_are_sections(self, language_server: SolidLanguageServer) -> None:
        """Sectioning commands should surface as document symbols."""
        symbols, _roots = language_server.request_document_symbols("main.tex").get_all_symbols_and_roots()
        assert len(symbols) > 0, "Should find at least some symbols in main.tex"

        names = {s.get("name", "") for s in symbols}
        for expected in ("Introduction", "Methods", "Conclusion"):
            assert expected in names, f"Expected section '{expected}' among document symbols, got: {sorted(names)}"

    @pytest.mark.parametrize("language_server", [Language.LATEX], indirect=True)
    def test_subsection_symbol_present(self, language_server: SolidLanguageServer) -> None:
        """A nested subsection should also be exposed as a symbol."""
        symbols, _roots = language_server.request_document_symbols("main.tex").get_all_symbols_and_roots()
        names = {s.get("name", "") for s in symbols}
        assert "Implementation Details" in names, f"Expected the subsection symbol, got: {sorted(names)}"

    @pytest.mark.parametrize("language_server", [Language.LATEX], indirect=True)
    def test_subsection_name_path_nests_under_section(self, language_server: SolidLanguageServer) -> None:
        """A subsection's name path nests under its parent section ("section/subsection")."""
        _symbols, roots = language_server.request_document_symbols("main.tex").get_all_symbols_and_roots()
        matches = [m for root in roots for m in LanguageServerSymbol(root).find("Methods/Implementation Details")]
        assert len(matches) == 1, matches
        assert matches[0].get_name_path() == "Methods/Implementation Details"
