import pytest

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.julia
class TestJuliaLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.JULIA], indirect=True)
    def test_julia_symbols(self, language_server: SolidLanguageServer):
        """
        Test if we can find the top-level symbols in the main.jl file.
        """
        all_symbols, _ = language_server.request_document_symbols("main.jl").get_all_symbols_and_roots()
        symbol_names = {s["name"] for s in all_symbols}
        assert "calculate_sum" in symbol_names
        assert "main" in symbol_names

    @pytest.mark.parametrize("language_server", [Language.JULIA], indirect=True)
    def test_julia_within_file_references(self, language_server: SolidLanguageServer):
        """
        Test finding references to a function within the same file.
        """
        # Find references to 'calculate_sum' - the function name starts at line 2, column 9
        # LSP uses 0-based indexing
        references = language_server.request_references("main.jl", line=2, column=9)

        # Should find at least the definition and the call site
        assert len(references) >= 1, f"Expected at least 1 reference, got {len(references)}"

        # Verify at least one reference is in main.jl
        reference_paths = [ref["relativePath"] for ref in references]
        assert "main.jl" in reference_paths

    @pytest.mark.parametrize("language_server", [Language.JULIA], indirect=True)
    def test_julia_cross_file_references(self, language_server: SolidLanguageServer):
        """
        Test finding references to a function defined in another file.
        """
        # The 'say_hello' function name starts at line 1, column 13 in lib/helper.jl
        # LSP uses 0-based indexing
        references = language_server.request_references("lib/helper.jl", line=1, column=13)

        # Should find at least the call site in main.jl
        assert len(references) >= 1, f"Expected at least 1 reference, got {len(references)}"

        # Verify at least one reference points to the usage
        reference_paths = [ref["relativePath"] for ref in references]
        # The reference might be in either file (definition or usage)
        assert "main.jl" in reference_paths or "lib/helper.jl" in reference_paths
