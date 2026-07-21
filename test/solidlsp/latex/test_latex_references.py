r"""Reference and definition resolution for the LaTeX (texlab) language server.

Exercises within-file and cross-file ``\ref`` -> ``\label`` resolution and
``\cite`` -> BibTeX entry resolution over the latex test repository.
"""

import os

import pytest

from serena.util.text_utils import find_text_coordinates
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import Location
from test.solidlsp.conftest import read_repo_file

MAIN = "main.tex"
BACKGROUND = os.path.join("sections", "background.tex")
BIB = "references.bib"


def _coords(language_server: SolidLanguageServer, relative_path: str, regex: str):
    coords = find_text_coordinates(read_repo_file(language_server, relative_path), regex, require_unique=True)
    assert coords is not None, f"pattern {regex!r} not found in {relative_path}"
    return coords


def _rel(location: Location) -> str:
    relative_path = location["relativePath"]
    assert relative_path is not None, location
    return relative_path.replace("\\", "/")


@pytest.mark.latex
class TestLatexReferences:
    """texlab reference/definition resolution within and across files."""

    @pytest.mark.parametrize("language_server", [Language.LATEX], indirect=True)
    def test_within_file_ref_resolves_to_section(self, language_server: SolidLanguageServer) -> None:
        r"""A ``\ref`` resolves to the sectioning command labelled in the same file."""
        ref = _coords(language_server, MAIN, r"forward to Section~\\ref\{(sec:methods)\}")
        section = _coords(language_server, MAIN, r"\\section\{(Methods)\}")

        definitions = language_server.request_definition(MAIN, ref.line, ref.col)

        assert len(definitions) == 1, definitions
        assert _rel(definitions[0]) == "main.tex"
        assert definitions[0]["range"]["start"]["line"] == section.line

    @pytest.mark.parametrize("language_server", [Language.LATEX], indirect=True)
    def test_within_file_references_list_all_uses(self, language_server: SolidLanguageServer) -> None:
        r"""Requesting references on a within-file label returns both ``\ref`` uses."""
        label = _coords(language_server, MAIN, r"\\label\{(sec:methods)\}")

        references = language_server.request_references(MAIN, label.line, label.col)

        assert {_rel(ref) for ref in references} == {"main.tex"}
        assert len(references) == 2, references

    @pytest.mark.parametrize("language_server", [Language.LATEX], indirect=True)
    def test_cross_file_ref_resolves_across_files(self, language_server: SolidLanguageServer) -> None:
        r"""A ``\ref`` in main.tex resolves to a ``\label`` defined in another file."""
        ref = _coords(language_server, MAIN, r"see Section~\\ref\{(sec:background)\}")
        section = _coords(language_server, BACKGROUND, r"\\section\{(Background)\}")

        definitions = language_server.request_definition(MAIN, ref.line, ref.col)

        assert len(definitions) == 1, definitions
        assert _rel(definitions[0]) == "sections/background.tex"
        assert definitions[0]["range"]["start"]["line"] == section.line

    @pytest.mark.parametrize("language_server", [Language.LATEX], indirect=True)
    def test_cross_file_references_point_back_to_main(self, language_server: SolidLanguageServer) -> None:
        r"""References on a cross-file label include the ``\ref`` site in main.tex."""
        label = _coords(language_server, BACKGROUND, r"\\label\{(sec:background)\}")
        ref_in_main = _coords(language_server, MAIN, r"see Section~\\ref\{(sec:background)\}")

        references = language_server.request_references(BACKGROUND, label.line, label.col)

        assert any(_rel(ref) == "main.tex" and ref["range"]["start"]["line"] == ref_in_main.line for ref in references), references

    @pytest.mark.parametrize("language_server", [Language.LATEX], indirect=True)
    def test_citation_resolves_to_bib_entry(self, language_server: SolidLanguageServer) -> None:
        r"""A ``\cite`` resolves to its entry in the BibTeX file."""
        cite = _coords(language_server, MAIN, r"Knuth~\\cite\{(knuth1984)\}")
        entry = _coords(language_server, BIB, r"@book\{(knuth1984)")

        definitions = language_server.request_definition(MAIN, cite.line, cite.col)

        assert len(definitions) == 1, definitions
        assert _rel(definitions[0]) == "references.bib"
        assert definitions[0]["range"]["start"]["line"] == entry.line
