import platform
from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.perl
@pytest.mark.skipif(platform.system() == "Windows", reason="Perl::LanguageServer does not support native Windows operation")
class TestPerlLanguageServer:
    """
    Tests for Perl::LanguageServer integration.

    Perl::LanguageServer provides comprehensive LSP support for Perl including:
    - Document symbols (functions, variables)
    - Go to definition (including cross-file)
    - Find references (including cross-file) - this was not available in PLS
    """

    @pytest.mark.parametrize("language_server", [Language.PERL], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.PERL], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that the language server starts and stops successfully."""
        # The fixture already handles start and stop
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.PERL], indirect=True)
    def test_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test that document symbols are correctly identified."""
        # Request document symbols
        all_symbols, _ = language_server.request_document_symbols("main.pl").get_all_symbols_and_roots()

        assert all_symbols, "Expected to find symbols in main.pl"
        assert len(all_symbols) > 0, "Expected at least one symbol"

        # DEBUG: Print all symbols
        print("\n=== All symbols in main.pl ===")
        for s in all_symbols:
            line = s.get("range", {}).get("start", {}).get("line", "?")
            print(f"Line {line}: {s.get('name')} (kind={s.get('kind')})")

        # Check that we can find function symbols
        function_symbols = [s for s in all_symbols if s.get("kind") == 12]  # 12 = Function/Method
        assert len(function_symbols) >= 2, f"Expected at least 2 functions (greet, use_helper_function), found {len(function_symbols)}"

        function_names = [s.get("name") for s in function_symbols]
        assert "greet" in function_names, f"Expected 'greet' function in symbols, found: {function_names}"
        assert "use_helper_function" in function_names, f"Expected 'use_helper_function' in symbols, found: {function_names}"

    # @pytest.mark.skip(reason="Perl::LanguageServer cross-file definition tracking needs configuration")
    @pytest.mark.parametrize("language_server", [Language.PERL], indirect=True)
    def test_find_definition_across_files(self, language_server: SolidLanguageServer) -> None:
        definition_location_list = language_server.request_definition("main.pl", 17, 0)

        assert len(definition_location_list) == 1
        definition_location = definition_location_list[0]
        print(f"Found definition: {definition_location}")
        assert definition_location["uri"].endswith("helper.pl")
        assert definition_location["range"]["start"]["line"] == 4  # add method on line 2 (0-indexed 1)

    @pytest.mark.parametrize("language_server", [Language.PERL], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer) -> None:
        """Test finding references to a function across multiple files."""
        reference_locations = language_server.request_references("helper.pl", 4, 5)

        assert len(reference_locations) >= 2, f"Expected at least 2 references to helper_function, found {len(reference_locations)}"

        main_pl_refs = [ref for ref in reference_locations if ref["uri"].endswith("main.pl")]
        assert len(main_pl_refs) >= 2, f"Expected at least 2 references in main.pl, found {len(main_pl_refs)}"

        main_pl_lines = sorted([ref["range"]["start"]["line"] for ref in main_pl_refs])
        assert 17 in main_pl_lines, f"Expected reference at line 18 (0-indexed 17), found: {main_pl_lines}"
        assert 20 in main_pl_lines, f"Expected reference at line 21 (0-indexed 20), found: {main_pl_lines}"
