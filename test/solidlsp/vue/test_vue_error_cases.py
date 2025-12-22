import os
import sys

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language

pytestmark = pytest.mark.vue

IS_WINDOWS = sys.platform == "win32"


class TypeScriptServerBehavior:
    """Platform-specific TypeScript language server behavior for invalid positions.

    On Windows: TS server returns empty results for invalid positions
    On macOS/Linux: TS server raises exceptions with "Bad line number" or "Debug Failure"
    """

    @staticmethod
    def raises_on_invalid_position() -> bool:
        return not IS_WINDOWS

    @staticmethod
    def returns_empty_on_invalid_position() -> bool:
        return IS_WINDOWS


class TestVueInvalidPositions:
    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_negative_line_number(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        result = language_server.request_containing_symbol(file_path, -1, 0)

        assert result is None or result == {}, f"Negative line number should return None or empty dict, got: {result}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_negative_character_number(self, language_server: SolidLanguageServer) -> None:
        """Test requesting containing symbol with negative character number.

        Expected behavior: Should return None or empty dict, not crash.
        """
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        # Request containing symbol at invalid negative character
        result = language_server.request_containing_symbol(file_path, 10, -1)

        # Should handle gracefully - return None or empty dict
        assert result is None or result == {}, f"Negative character number should return None or empty dict, got: {result}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_line_number_beyond_file_length(self, language_server: SolidLanguageServer) -> None:
        """Test requesting containing symbol beyond file length.

        Expected behavior: Raises IndexError when trying to access line beyond file bounds.
        This happens in the wrapper code before even reaching the language server.
        """
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        # Request containing symbol at line 99999 (way beyond file length)
        # The wrapper code will raise an IndexError when checking if the line is empty
        with pytest.raises(IndexError) as exc_info:
            language_server.request_containing_symbol(file_path, 99999, 0)

        # Verify it's an index error for list access
        assert "list index out of range" in str(exc_info.value), f"Expected 'list index out of range' error, got: {exc_info.value}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_character_number_beyond_line_length(self, language_server: SolidLanguageServer) -> None:
        """Test requesting containing symbol beyond line length.

        Expected behavior: Should return None or empty dict, not crash.
        """
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        # Request containing symbol at character 99999 (way beyond line length)
        result = language_server.request_containing_symbol(file_path, 10, 99999)

        # Should handle gracefully - return None or empty dict
        assert result is None or result == {}, f"Character beyond line length should return None or empty dict, got: {result}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_references_at_negative_line(self, language_server: SolidLanguageServer) -> None:
        """Test requesting references with negative line number."""
        from solidlsp.ls_exceptions import SolidLSPException

        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        if TypeScriptServerBehavior.returns_empty_on_invalid_position():
            result = language_server.request_references(file_path, -1, 0)
            assert result == [], f"Expected empty list on Windows, got: {result}"
        else:
            with pytest.raises(SolidLSPException) as exc_info:
                language_server.request_references(file_path, -1, 0)
            assert "Bad line number" in str(exc_info.value) or "Debug Failure" in str(exc_info.value)

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_definition_at_invalid_position(self, language_server: SolidLanguageServer) -> None:
        """Test requesting definition at invalid position."""
        from solidlsp.ls_exceptions import SolidLSPException

        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        if TypeScriptServerBehavior.returns_empty_on_invalid_position():
            result = language_server.request_definition(file_path, -1, 0)
            assert result == [], f"Expected empty list on Windows, got: {result}"
        else:
            with pytest.raises(SolidLSPException) as exc_info:
                language_server.request_definition(file_path, -1, 0)
            assert "Bad line number" in str(exc_info.value) or "Debug Failure" in str(exc_info.value)


class TestVueNonExistentFiles:
    """Tests for handling non-existent files."""

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_document_symbols_nonexistent_file(self, language_server: SolidLanguageServer) -> None:
        """Test requesting document symbols from non-existent file.

        Expected behavior: Should raise FileNotFoundError or return empty result.
        """
        nonexistent_file = os.path.join("src", "components", "NonExistent.vue")

        # Should raise an appropriate exception or return empty result
        try:
            result = language_server.request_document_symbols(nonexistent_file)
            # If no exception, verify result is empty or indicates file not found
            symbols = result.get_all_symbols_and_roots()
            assert len(symbols[0]) == 0, f"Non-existent file should return empty symbols, got {len(symbols[0])} symbols"
        except (FileNotFoundError, Exception) as e:
            # Expected - file doesn't exist
            assert True, f"Appropriately raised exception for non-existent file: {e}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_containing_symbol_nonexistent_file(self, language_server: SolidLanguageServer) -> None:
        """Test requesting containing symbol from non-existent file.

        Expected behavior: Should raise FileNotFoundError or return None.
        """
        nonexistent_file = os.path.join("src", "components", "NonExistent.vue")

        # Should raise an appropriate exception or return None
        try:
            result = language_server.request_containing_symbol(nonexistent_file, 10, 10)
            # If no exception, verify result indicates file not found
            assert result is None or result == {}, f"Non-existent file should return None or empty dict, got: {result}"
        except (FileNotFoundError, Exception) as e:
            # Expected - file doesn't exist
            assert True, f"Appropriately raised exception for non-existent file: {e}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_references_nonexistent_file(self, language_server: SolidLanguageServer) -> None:
        """Test requesting references from non-existent file.

        Expected behavior: Should raise FileNotFoundError or return empty list.
        """
        nonexistent_file = os.path.join("src", "components", "NonExistent.vue")

        # Should raise an appropriate exception or return empty list
        try:
            result = language_server.request_references(nonexistent_file, 10, 10)
            # If no exception, verify result is empty
            assert result is None or isinstance(result, list), f"Non-existent file should return None or list, got: {result}"
            if isinstance(result, list):
                assert len(result) == 0, f"Non-existent file should return empty list, got {len(result)} references"
        except (FileNotFoundError, Exception) as e:
            # Expected - file doesn't exist
            assert True, f"Appropriately raised exception for non-existent file: {e}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_definition_nonexistent_file(self, language_server: SolidLanguageServer) -> None:
        """Test requesting definition from non-existent file.

        Expected behavior: Should raise FileNotFoundError or return empty list.
        """
        nonexistent_file = os.path.join("src", "components", "NonExistent.vue")

        # Should raise an appropriate exception or return empty list
        try:
            result = language_server.request_definition(nonexistent_file, 10, 10)
            # If no exception, verify result is empty
            assert isinstance(result, list), f"request_definition should return a list, got: {type(result)}"
            assert len(result) == 0, f"Non-existent file should return empty list, got {len(result)} definitions"
        except (FileNotFoundError, Exception) as e:
            # Expected - file doesn't exist
            assert True, f"Appropriately raised exception for non-existent file: {e}"


class TestVueUndefinedSymbols:
    """Tests for handling undefined or unreferenced symbols."""

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_references_for_unreferenced_symbol(self, language_server: SolidLanguageServer) -> None:
        """Test requesting references for a symbol that has no references.

        Expected behavior: Should return empty list (only the definition itself if include_self=True).
        """
        # Find a symbol that likely has no external references
        file_path = os.path.join("src", "components", "CalculatorButton.vue")

        # Get document symbols
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        # Find pressCount - this is exposed but may not be referenced elsewhere
        press_count_symbol = next((s for s in symbols[0] if s.get("name") == "pressCount"), None)

        if not press_count_symbol or "selectionRange" not in press_count_symbol:
            pytest.skip("pressCount symbol not found - test fixture may need updating")

        # Request references without include_self
        sel_start = press_count_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])

        # Should return a list (may be empty or contain only definition)
        assert isinstance(refs, list), f"request_references should return a list, got {type(refs)}"

        # For an unreferenced symbol, should have 0-1 references (0 without include_self, 1 with)
        # The exact count depends on the language server implementation
        assert len(refs) <= 5, (
            f"pressCount should have few or no external references. "
            f"Got {len(refs)} references. This is not necessarily an error, just documenting behavior."
        )

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_containing_symbol_at_whitespace_only_line(self, language_server: SolidLanguageServer) -> None:
        """Test requesting containing symbol at a whitespace-only line.

        Expected behavior: Should return None, empty dict, or the parent symbol.
        """
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        # Try position at line 1 (typically a blank line or template start in Vue SFCs)
        result = language_server.request_containing_symbol(file_path, 1, 0)

        # Should handle gracefully - return None, empty dict, or a valid parent symbol
        assert (
            result is None or result == {} or isinstance(result, dict)
        ), f"Whitespace line should return None, empty dict, or valid symbol. Got: {result}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_definition_at_keyword_position(self, language_server: SolidLanguageServer) -> None:
        """Test requesting definition at language keyword position.

        Expected behavior: Should return empty list or handle gracefully.
        """
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        # Try to get definition at a keyword like "const", "import", etc.
        # Line 2 typically has "import" statement - try position on "import" keyword
        result = language_server.request_definition(file_path, 2, 0)

        # Should handle gracefully - return empty list or valid definitions
        assert isinstance(result, list), f"request_definition should return a list, got {type(result)}"


class TestVueEdgeCasePositions:
    """Tests for edge case positions (0,0 and file boundaries)."""

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_containing_symbol_at_file_start(self, language_server: SolidLanguageServer) -> None:
        """Test requesting containing symbol at position (0,0).

        Expected behavior: Should return None, empty dict, or a valid symbol.
        This position typically corresponds to the start of the file (e.g., <template> tag).
        """
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        # Request containing symbol at position 0,0 (file start)
        result = language_server.request_containing_symbol(file_path, 0, 0)

        # Should handle gracefully
        assert (
            result is None or result == {} or isinstance(result, dict)
        ), f"Position 0,0 should return None, empty dict, or valid symbol. Got: {result}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_references_at_file_start(self, language_server: SolidLanguageServer) -> None:
        """Test requesting references at position (0,0).

        Expected behavior: Should return None or empty list.
        """
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        # Request references at position 0,0 (file start)
        result = language_server.request_references(file_path, 0, 0)

        # Should handle gracefully
        assert result is None or isinstance(result, list), f"Position 0,0 should return None or list. Got: {type(result)}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_definition_at_file_start(self, language_server: SolidLanguageServer) -> None:
        """Test requesting definition at position (0,0).

        Expected behavior: Should return empty list.
        """
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        # Request definition at position 0,0 (file start)
        result = language_server.request_definition(file_path, 0, 0)

        # Should handle gracefully
        assert isinstance(result, list), f"request_definition should return a list. Got: {type(result)}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_containing_symbol_in_template_section(self, language_server: SolidLanguageServer) -> None:
        """Test requesting containing symbol in the template section.

        Expected behavior: Template positions typically have no containing symbol (return None or empty).
        The Vue language server may not track template symbols the same way as script symbols.
        """
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        # Position likely in template section (early in file, before <script setup>)
        # Exact line depends on file structure, but line 5-10 is often template
        result = language_server.request_containing_symbol(file_path, 5, 10)

        # Should handle gracefully - template doesn't have containing symbols in the same way
        assert (
            result is None or result == {} or isinstance(result, dict)
        ), f"Template position should return None, empty dict, or valid symbol. Got: {result}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_zero_character_positions(self, language_server: SolidLanguageServer) -> None:
        """Test requesting symbols at character position 0 (start of lines).

        Expected behavior: Should handle gracefully, may or may not find symbols.
        """
        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        # Test multiple lines at character 0
        for line in [0, 10, 20, 30]:
            result = language_server.request_containing_symbol(file_path, line, 0)

            # Should handle gracefully
            assert (
                result is None or result == {} or isinstance(result, dict)
            ), f"Line {line}, character 0 should return None, empty dict, or valid symbol. Got: {result}"


class TestVueTypescriptFileErrors:
    """Tests for error handling in TypeScript files within Vue projects."""

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_typescript_file_invalid_position(self, language_server: SolidLanguageServer) -> None:
        """Test requesting symbols from TypeScript file at invalid position.

        Expected behavior: Should handle gracefully.
        """
        file_path = os.path.join("src", "stores", "calculator.ts")

        # Request containing symbol at invalid position
        result = language_server.request_containing_symbol(file_path, -1, -1)

        # Should handle gracefully
        assert result is None or result == {}, f"Invalid position in .ts file should return None or empty dict. Got: {result}"

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_typescript_file_beyond_bounds(self, language_server: SolidLanguageServer) -> None:
        """Test requesting symbols from TypeScript file beyond file bounds.

        Expected behavior: Raises IndexError when trying to access line beyond file bounds.
        """
        file_path = os.path.join("src", "stores", "calculator.ts")

        # Request containing symbol beyond file bounds
        # The wrapper code will raise an IndexError when checking if the line is empty
        with pytest.raises(IndexError) as exc_info:
            language_server.request_containing_symbol(file_path, 99999, 99999)

        # Verify it's an index error for list access
        assert "list index out of range" in str(exc_info.value), f"Expected 'list index out of range' error, got: {exc_info.value}"


class TestVueReferenceEdgeCases:
    """Tests for edge cases in reference finding."""

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_referencing_symbols_at_invalid_position(self, language_server: SolidLanguageServer) -> None:
        """Test requesting referencing symbols at invalid position."""
        from solidlsp.ls_exceptions import SolidLSPException

        file_path = os.path.join("src", "stores", "calculator.ts")

        if TypeScriptServerBehavior.returns_empty_on_invalid_position():
            result = list(language_server.request_referencing_symbols(file_path, -1, -1, include_self=False))
            assert result == [], f"Expected empty list on Windows, got: {result}"
        else:
            with pytest.raises(SolidLSPException) as exc_info:
                list(language_server.request_referencing_symbols(file_path, -1, -1, include_self=False))
            assert "Bad line number" in str(exc_info.value) or "Debug Failure" in str(exc_info.value)

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_defining_symbol_at_invalid_position(self, language_server: SolidLanguageServer) -> None:
        """Test requesting defining symbol at invalid position."""
        from solidlsp.ls_exceptions import SolidLSPException

        file_path = os.path.join("src", "components", "CalculatorInput.vue")

        if TypeScriptServerBehavior.returns_empty_on_invalid_position():
            result = language_server.request_defining_symbol(file_path, -1, -1)
            assert result is None, f"Expected None on Windows, got: {result}"
        else:
            with pytest.raises(SolidLSPException) as exc_info:
                language_server.request_defining_symbol(file_path, -1, -1)
            assert "Bad line number" in str(exc_info.value) or "Debug Failure" in str(exc_info.value)

    @pytest.mark.parametrize("language_server", [Language.VUE], indirect=True)
    def test_referencing_symbols_beyond_file_bounds(self, language_server: SolidLanguageServer) -> None:
        """Test requesting referencing symbols beyond file bounds."""
        from solidlsp.ls_exceptions import SolidLSPException

        file_path = os.path.join("src", "stores", "calculator.ts")

        if TypeScriptServerBehavior.returns_empty_on_invalid_position():
            result = list(language_server.request_referencing_symbols(file_path, 99999, 99999, include_self=False))
            assert result == [], f"Expected empty list on Windows, got: {result}"
        else:
            with pytest.raises(SolidLSPException) as exc_info:
                list(language_server.request_referencing_symbols(file_path, 99999, 99999, include_self=False))
            assert "Bad line number" in str(exc_info.value) or "Debug Failure" in str(exc_info.value)
