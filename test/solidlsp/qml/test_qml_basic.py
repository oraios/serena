"""
Basic integration tests for the QML language server (qmlls) functionality.

These tests validate document symbols, reference search, and diagnostics
using the QML test repository.

Requires ``qmlls6`` or ``qmlls`` on PATH (shipped with Qt 6).
"""

import os
from pathlib import Path

import pytest

from serena.util.text_utils import find_text_coordinates
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.conftest import language_tests_enabled
from test.solidlsp.conftest import read_repo_file
from test.solidlsp.util.diagnostics import assert_file_diagnostics

pytestmark = [
    pytest.mark.qml,
    pytest.mark.skipif(not language_tests_enabled(Language.QML), reason="QML tests are disabled (qmlls/qmlls6 not available)"),
]


class TestQmlLanguageServer:
    """Test QML language server startup and basic features."""

    @pytest.mark.parametrize("language_server", [Language.QML], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer) -> None:
        """Test that the language server starts successfully."""
        assert language_server.is_running()

    @pytest.mark.parametrize("language_server", [Language.QML], indirect=True)
    def test_document_symbols_main(self, language_server: SolidLanguageServer) -> None:
        """Test that document symbols are returned for the main file.

        qmlls names QML objects by their type (ApplicationWindow, Button); properties such as
        ``id`` and ``width`` appear as child symbols, so we assert on the component type names.
        """
        file_path = os.path.join("src", "main.qml")
        doc_symbols = language_server.request_document_symbols(file_path)
        all_symbols, root_symbols = doc_symbols.get_all_symbols_and_roots()

        root_names = [s.get("name") for s in root_symbols if s.get("name")]
        symbol_names = [s.get("name") for s in all_symbols if s.get("name")]
        assert "ApplicationWindow" in root_names, f"ApplicationWindow root missing. Roots: {root_names}"
        assert "Button" in symbol_names, f"Button component missing. Symbols: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.QML], indirect=True)
    def test_document_symbols_shapes(self, language_server: SolidLanguageServer) -> None:
        """Test that document symbols are returned for the shapes file."""
        file_path = os.path.join("src", "shapes.qml")
        doc_symbols = language_server.request_document_symbols(file_path)
        all_symbols, root_symbols = doc_symbols.get_all_symbols_and_roots()

        root_names = [s.get("name") for s in root_symbols if s.get("name")]
        symbol_names = [s.get("name") for s in all_symbols if s.get("name")]
        assert "Rectangle" in root_names, f"Rectangle root missing. Roots: {root_names}"
        assert "Text" in symbol_names, f"Text component missing. Symbols: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.QML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.QML], indirect=True)
    def test_find_references_within_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that references are found within the same file.

        CustomComponent.qml references ``root.width`` on multiple lines (declaration via
        ``id: root`` on line 3 and usages on lines 5 and 10). We click on a usage of
        ``root`` and verify that the other usages are found.
        """
        file_path = str(repo_path / "src" / "CustomComponent.qml")
        content = read_repo_file(language_server, os.path.join("src", "CustomComponent.qml"))

        # Probe at the `root` identifier in `root.width` on line 10 (0-indexed) —
        # the occurrence inside the Text block. `find_text_coordinates` uses a
        # capturing group around the target text so `coords` lands on `root`.
        coords = find_text_coordinates(content, r"(root)\.width")
        assert coords is not None, "Could not locate root.width in CustomComponent.qml"

        references = language_server.request_references(file_path, coords.line, coords.col + 1)
        assert references, f"Expected non-empty references for root, got {references=}"

        # All references should be within CustomComponent.qml (no cross-file
        # references to ``root``, which is scoped to this component).
        ref_files = {loc["uri"].split("/")[-1] for loc in references}
        assert "CustomComponent.qml" in ref_files, f"All references should be in CustomComponent.qml, got {ref_files}"

    @pytest.mark.parametrize("language_server", [Language.QML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.QML], indirect=True)
    def test_find_references_cross_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that references are found across files.

        CustomComponent.qml defines a QML component type that is instantiated in
        UserComponent.qml. Clicking on the ``CustomComponent`` type usage in
        UserComponent.qml should return at least one reference, ideally spanning
        both files.
        """
        file_path = str(repo_path / "src" / "UserComponent.qml")
        content = read_repo_file(language_server, os.path.join("src", "UserComponent.qml"))

        # Locate the `CustomComponent` type usage in UserComponent.qml.
        coords = find_text_coordinates(content, r"(CustomComponent)")
        assert coords is not None, "Could not locate CustomComponent type in UserComponent.qml"

        references = language_server.request_references(file_path, coords.line, coords.col + 1)
        assert references, f"Expected non-empty references for CustomComponent, got {references=}"

        ref_files = {loc["uri"].split("/")[-1] for loc in references}
        assert "UserComponent.qml" in ref_files, f"Expected at least one reference in UserComponent.qml, got {ref_files}"

    @pytest.mark.parametrize("language_server", [Language.QML], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        """Test that diagnostics are reported for a QML file with errors.

        diagnostics_sample.qml contains an unknown property (``colorr`` instead of
        ``color``) which qmlls should flag as an error or warning.
        """
        assert_file_diagnostics(
            language_server,
            os.path.join("src", "diagnostics_sample.qml"),
            (),
            min_count=1,
        )
