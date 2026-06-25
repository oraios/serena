r"""Beamer presentation support for the LaTeX (texlab) language server.

Beamer frames surface as ``Frame: <title>`` document symbols nested under their
section, and ``\ref`` resolution works inside frames.
"""

import pytest

from serena.util.text_utils import find_text_coordinates
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import Location
from test.solidlsp.conftest import read_repo_file

SLIDES = "slides.tex"


def _rel(location: Location) -> str:
    relative_path = location["relativePath"]
    assert relative_path is not None, location
    return relative_path.replace("\\", "/")


@pytest.mark.latex
class TestLatexBeamer:
    """texlab handling of a beamer presentation (sections and frames)."""

    @pytest.mark.parametrize("language_server", [Language.LATEX], indirect=True)
    def test_beamer_sections_and_frames_are_symbols(self, language_server: SolidLanguageServer) -> None:
        r"""Beamer sections and ``\frametitle`` frames both surface as document symbols."""
        symbols, _roots = language_server.request_document_symbols(SLIDES).get_all_symbols_and_roots()
        names = {s.get("name", "") for s in symbols}
        for expected in ("Overview", "Results", "Frame: Introduction", "Frame: Methodology", "Frame: Findings"):
            assert expected in names, f"Expected beamer symbol {expected!r}, got: {sorted(names)}"

    @pytest.mark.parametrize("language_server", [Language.LATEX], indirect=True)
    def test_beamer_frames_nest_under_sections(self, language_server: SolidLanguageServer) -> None:
        r"""Frames are children of the section they appear in."""
        _symbols, roots = language_server.request_document_symbols(SLIDES).get_all_symbols_and_roots()
        roots_by_name = {root.get("name"): root for root in roots}

        overview = roots_by_name.get("Overview")
        assert overview is not None, [root.get("name") for root in roots]
        overview_children = {child.get("name") for child in overview.get("children", [])}
        assert overview_children == {"Frame: Introduction", "Frame: Methodology"}, overview_children

    @pytest.mark.parametrize("language_server", [Language.LATEX], indirect=True)
    def test_beamer_frame_ref_resolves_to_section(self, language_server: SolidLanguageServer) -> None:
        r"""A ``\ref`` inside a beamer frame resolves to the section it targets."""
        content = read_repo_file(language_server, SLIDES)
        ref = find_text_coordinates(content, r"see Section~\\ref\{(sec:results)\}", require_unique=True)
        section = find_text_coordinates(content, r"\\section\{(Results)\}", require_unique=True)
        assert ref is not None and section is not None

        definitions = language_server.request_definition(SLIDES, ref.line, ref.col)

        assert len(definitions) == 1, definitions
        assert _rel(definitions[0]) == "slides.tex"
        assert definitions[0]["range"]["start"]["line"] == section.line
