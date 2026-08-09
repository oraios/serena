import pytest

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.conftest import language_server_tests_enabled

pytestmark = [
    pytest.mark.wolfram,
    pytest.mark.skipif(
        not language_server_tests_enabled(LanguageServerId.WOLFRAM), reason="Wolfram tests disabled (WolframKernel not available)"
    ),
]

# Note: the LSPServer paclet computes textDocument/references per document, i.e. only
# references within the file containing the queried position are returned; cross-file
# references are not supported by the language server.


class TestWolframLanguageServer:
    @pytest.mark.parametrize("language_server", [LanguageServerId.WOLFRAM], indirect=True)
    def test_wolfram_symbols(self, language_server: SolidLanguageServer):
        """
        Test if we can find the top-level symbols in the main.wl file.
        """
        all_symbols, _ = language_server.request_document_symbols("main.wl").get_all_symbols_and_roots()
        symbol_names = {s["name"] for s in all_symbols}
        assert "calculateSum" in symbol_names
        assert "main" in symbol_names

    @pytest.mark.parametrize("language_server", [LanguageServerId.WOLFRAM], indirect=True)
    def test_wolfram_symbols_in_subdirectory(self, language_server: SolidLanguageServer):
        """
        Test if we can find the top-level symbols in a file in a subdirectory.
        """
        all_symbols, _ = language_server.request_document_symbols("lib/helper.wl").get_all_symbols_and_roots()
        symbol_names = {s["name"] for s in all_symbols}
        assert "sayHello" in symbol_names
        assert "formatResult" in symbol_names

    @pytest.mark.parametrize("language_server", [LanguageServerId.WOLFRAM], indirect=True)
    def test_wolfram_within_file_references(self, language_server: SolidLanguageServer):
        """
        Test finding references to a function within the same file.
        """
        # 'calculateSum' is defined on line 2 of main.wl and called on line 10 (0-based)
        references = language_server.request_references("main.wl", line=2, column=0)

        reference_lines = {(ref["relativePath"], ref["range"]["start"]["line"]) for ref in references}
        assert ("main.wl", 2) in reference_lines, f"Expected the definition site among references, got {reference_lines}"
        assert ("main.wl", 10) in reference_lines, f"Expected the call site among references, got {reference_lines}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.WOLFRAM], indirect=True)
    def test_wolfram_no_cross_file_references(self, language_server: SolidLanguageServer):
        """
        Test documenting that references are computed per document by the LSPServer paclet.

        'sayHello' is defined in lib/helper.wl and called in main.wl, but querying references
        from its definition must only return locations within lib/helper.wl. If this test
        starts failing, the language server gained cross-file reference support and the
        documentation (docs page, CHANGELOG, module comment above) should be updated.
        """
        references = language_server.request_references("lib/helper.wl", line=0, column=0)

        assert references, "Expected at least one within-file reference in lib/helper.wl fixture"
        reference_paths = {ref["relativePath"] for ref in references}
        assert reference_paths == {"lib/helper.wl"}, f"Expected references only within lib/helper.wl, got {reference_paths}"
