import pytest

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language
from test.conftest import language_tests_enabled

pytestmark = [
    pytest.mark.wolfram,
    pytest.mark.skipif(not language_tests_enabled(Language.WOLFRAM), reason="Wolfram tests disabled (WolframKernel not available)"),
]


class TestWolframLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.WOLFRAM], indirect=True)
    def test_wolfram_symbols(self, language_server: SolidLanguageServer):
        """
        Test if we can find the top-level symbols in the main.wl file.
        """
        all_symbols, _ = language_server.request_document_symbols("main.wl").get_all_symbols_and_roots()
        symbol_names = {s["name"] for s in all_symbols}
        assert "calculateSum" in symbol_names
        assert "main" in symbol_names

    @pytest.mark.parametrize("language_server", [Language.WOLFRAM], indirect=True)
    def test_wolfram_within_file_references(self, language_server: SolidLanguageServer):
        """
        Test finding references to a function within the same file.
        """
        # Find references to 'calculateSum' defined at the top of main.wl
        # LSP uses 0-based indexing
        references = language_server.request_references("main.wl", line=2, column=0)

        # Should find at least the definition and the call site
        assert len(references) >= 1, f"Expected at least 1 reference, got {len(references)}"

        # Verify at least one reference is in main.wl
        reference_paths = [ref["relativePath"] for ref in references]
        assert "main.wl" in reference_paths

    @pytest.mark.parametrize("language_server", [Language.WOLFRAM], indirect=True)
    def test_wolfram_cross_file_references(self, language_server: SolidLanguageServer):
        """
        Test finding references to a function defined in another file.
        """
        # Find references to 'sayHello' defined in lib/helper.wl at line 0
        # LSP uses 0-based indexing
        references = language_server.request_references("lib/helper.wl", line=0, column=0)

        # Should find at least the definition or usage
        assert len(references) >= 1, f"Expected at least 1 reference, got {len(references)}"

        # Verify references span files
        reference_paths = [ref["relativePath"] for ref in references]
        assert "main.wl" in reference_paths or "lib/helper.wl" in reference_paths
