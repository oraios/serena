"""
Basic integration tests for the QML language server (qmlls) functionality.

These tests validate document symbols and basic LSP functionality
using the QML test repository.

Requires ``qmlls6`` or ``qmlls`` on PATH (shipped with Qt 6).
"""

import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.conftest import language_tests_enabled

pytestmark = [
    pytest.mark.qml,
    pytest.mark.skipif(not language_tests_enabled(Language.QML), reason="QML tests are disabled (qmlls/qmlls6 not available)"),
]


class TestQmlLanguageServer:
    """Test QML language server startup."""

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
