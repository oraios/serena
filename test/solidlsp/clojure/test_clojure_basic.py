import pytest

from serena.project import Project
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import UnifiedSymbolInformation
from test.conftest import language_tests_enabled

from . import CORE_PATH, UTILS_PATH


@pytest.mark.skipif(not language_tests_enabled(Language.CLOJURE), reason="Clojure tests are disabled")
@pytest.mark.clojure
class TestLanguageServerBasics:
    @pytest.mark.parametrize("language_server", [Language.CLOJURE], indirect=True)
    def test_basic_definition(self, language_server: SolidLanguageServer):
        """
        Test finding definition of 'greet' function call in core.clj
        """
        result = language_server.request_definition(CORE_PATH, 20, 12)  # Position of 'greet' in (greet "World")

        assert isinstance(result, list)
        assert len(result) >= 1

        definition = result[0]
        assert definition["relativePath"] == CORE_PATH
        assert definition["range"]["start"]["line"] == 2, "Should find the definition of greet function at line 2"

    @pytest.mark.parametrize("language_server", [Language.CLOJURE], indirect=True)
    def test_cross_file_references(self, language_server: SolidLanguageServer):
        """
        Test finding references to 'multiply' function from core.clj
        """
        result = language_server.request_references(CORE_PATH, 12, 6)

        assert isinstance(result, list) and len(result) >= 2, "Should find definition + usage in utils.clj"

        usage_found = any(
            item["relativePath"] == UTILS_PATH and item["range"]["start"]["line"] == 6  # multiply usage in calculate-area
            for item in result
        )
        assert usage_found, "Should find multiply usage in utils.clj"

    @pytest.mark.parametrize("language_server", [Language.CLOJURE], indirect=True)
    def test_completions(self, language_server: SolidLanguageServer):
        with language_server.open_file(UTILS_PATH):
            # After "core/" in calculate-area
            result = language_server.request_completions(UTILS_PATH, 6, 8)

            assert isinstance(result, list) and len(result) > 0

            completion_texts = [item["completionText"] for item in result]
            assert any("multiply" in text for text in completion_texts), "Should find 'multiply' function in completions after 'core/'"

    @pytest.mark.parametrize("language_server", [Language.CLOJURE], indirect=True)
    def test_document_symbols(self, language_server: SolidLanguageServer):
        symbols, _ = language_server.request_document_symbols(CORE_PATH).get_all_symbols_and_roots()

        assert isinstance(symbols, list) and len(symbols) >= 4, "greet, add, multiply, -main functions"

        # Check that we find the expected function symbols
        symbol_names = [symbol["name"] for symbol in symbols]
        expected_functions = ["greet", "add", "multiply", "-main"]

        for func_name in expected_functions:
            assert func_name in symbol_names, f"Should find {func_name} function in symbols"

    @pytest.mark.parametrize("language_server", [Language.CLOJURE], indirect=True)
    def test_hover(self, language_server: SolidLanguageServer):
        """Test hover on greet function"""
        result = language_server.request_hover(CORE_PATH, 2, 7)

        assert result is not None, "Hover should return information for greet function"
        assert "contents" in result
        # Should contain function signature or documentation
        contents = result["contents"]
        if isinstance(contents, str):
            assert "greet" in contents.lower()
        elif isinstance(contents, dict) and "value" in contents:
            assert "greet" in contents["value"].lower()
        else:
            assert False, f"Unexpected contents format: {type(contents)}"

    @pytest.mark.parametrize("language_server", [Language.CLOJURE], indirect=True)
    def test_workspace_symbols(self, language_server: SolidLanguageServer):
        # Search for functions containing "add"
        result = language_server.request_workspace_symbol("add")

        assert isinstance(result, list) and len(result) > 0, "Should find at least one symbol containing 'add'"

        # Should find the 'add' function
        symbol_names = [symbol["name"] for symbol in result]
        assert any("add" in name.lower() for name in symbol_names), f"Should find 'add' function in symbols: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.CLOJURE], indirect=True)
    def test_namespace_functions(self, language_server: SolidLanguageServer):
        """Test definition lookup for core/greet usage in utils.clj"""
        # Position of 'greet' in core/greet call
        result = language_server.request_definition(UTILS_PATH, 11, 25)

        assert isinstance(result, list)
        assert len(result) >= 1

        definition = result[0]
        assert definition["relativePath"] == CORE_PATH, "Should find the definition of greet in core.clj"

    @pytest.mark.parametrize("language_server", [Language.CLOJURE], indirect=True)
    def test_request_references_with_content(self, language_server: SolidLanguageServer):
        """Test references to multiply function with content"""
        references = language_server.request_references(CORE_PATH, 12, 6)
        result = [
            language_server.retrieve_content_around_line(ref1["relativePath"], ref1["range"]["start"]["line"], 3, 0) for ref1 in references
        ]

        assert result is not None, "Should find references with content"
        assert isinstance(result, list)
        assert len(result) >= 2, "Should find definition + usage in utils.clj"

        for ref in result:
            assert ref.source_file_path is not None, "Each reference should have a source file path"
            content_str = ref.to_display_string()
            assert len(content_str) > 0, "Content should not be empty"

        # Verify we find the reference in utils.clj with context
        utils_refs = [ref for ref in result if ref.source_file_path and "utils.clj" in ref.source_file_path]
        assert len(utils_refs) > 0, "Should find reference in utils.clj"

        # The context should contain the calculate-area function
        utils_content = utils_refs[0].to_display_string()
        assert "calculate-area" in utils_content

    @pytest.mark.parametrize("language_server", [Language.CLOJURE], indirect=True)
    def test_request_full_symbol_tree(self, language_server: SolidLanguageServer):
        """Test retrieving the full symbol tree for project overview
        We just check that we find some expected symbols.
        """
        result = language_server.request_full_symbol_tree()

        assert result is not None, "Should return symbol tree"
        assert isinstance(result, list), "Symbol tree should be a list"
        assert len(result) > 0, "Should find symbols in the project"

        def traverse_symbols(symbols, indent=0):
            """Recursively traverse symbols to print their structure"""
            info = []
            for s in symbols:
                name = getattr(s, "name", "NO_NAME")
                kind = getattr(s, "kind", "NO_KIND")
                info.append(f"{' ' * indent}Symbol: {name}, Kind: {kind}")
                if hasattr(s, "children") and s.children:
                    info.append(" " * indent + "Children:")
                    info.extend(traverse_symbols(s.children, indent + 2))
            return info

        def list_all_symbols(symbols: list[UnifiedSymbolInformation]):
            found = []
            for symbol in symbols:
                found.append(symbol["name"])
                found.extend(list_all_symbols(symbol["children"]))
            return found

        all_symbol_names = list_all_symbols(result)

        expected_symbols = ["greet", "add", "multiply", "-main", "calculate-area", "format-greeting", "sum-list"]
        found_expected = [name for name in expected_symbols if any(name in symbol_name for symbol_name in all_symbol_names)]

        if len(found_expected) < 7:
            pytest.fail(
                f"Expected to find at least 3 symbols from {expected_symbols}, but found: {found_expected}.\n"
                f"All symbol names: {all_symbol_names}\n"
                f"Symbol tree structure:\n{traverse_symbols(result)}"
            )

    @pytest.mark.parametrize("language_server", [Language.CLOJURE], indirect=True)
    def test_request_referencing_symbols(self, language_server: SolidLanguageServer):
        """Test finding symbols that reference a given symbol
        Finds references to the 'multiply' function.
        """
        result = language_server.request_referencing_symbols(CORE_PATH, 12, 6)
        assert isinstance(result, list) and len(result) > 0, "Should find at least one referencing symbol"
        found_relevant_references = False
        for ref in result:
            if hasattr(ref, "symbol") and "calculate-area" in ref.symbol["name"]:
                found_relevant_references = True
                break

        assert found_relevant_references, f"Should have found calculate-area referencing multiply, but got: {result}"


class TestProjectBasics:
    @pytest.mark.parametrize("project", [Language.CLOJURE], indirect=True)
    def test_retrieve_content_around_line(self, project: Project):
        """Test retrieving content around specific lines"""
        # Test retrieving content around the greet function definition (line 2)
        result = project.retrieve_content_around_line(CORE_PATH, 2, 2)

        assert result is not None, "Should retrieve content around line 2"
        content_str = result.to_display_string()
        assert "greet" in content_str, "Should contain the greet function definition"
        assert "defn" in content_str, "Should contain defn keyword"

        # Test retrieving content around multiply function (around line 13)
        result = project.retrieve_content_around_line(CORE_PATH, 13, 1)

        assert result is not None, "Should retrieve content around line 13"
        content_str = result.to_display_string()
        assert "multiply" in content_str, "Should contain multiply function"

    @pytest.mark.parametrize("project", [Language.CLOJURE], indirect=True)
    def test_search_files_for_pattern(self, project: Project) -> None:
        result = project.search_source_files_for_pattern("defn.*greet")

        assert result is not None, "Pattern search should return results"
        assert len(result) > 0, "Should find at least one match for 'defn.*greet'"

        core_matches = [match for match in result if match.source_file_path and "core.clj" in match.source_file_path]
        assert len(core_matches) > 0, "Should find greet function in core.clj"

        result = project.search_source_files_for_pattern(":require")

        assert result is not None, "Should find require statements"
        utils_matches = [match for match in result if match.source_file_path and "utils.clj" in match.source_file_path]
        assert len(utils_matches) > 0, "Should find require statement in utils.clj"
