import os
import sys

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language

pytestmark = pytest.mark.svelte

IS_WINDOWS = sys.platform == "win32"


class TypeScriptServerBehavior:
    @staticmethod
    def raises_on_invalid_position() -> bool:
        return not IS_WINDOWS

    @staticmethod
    def returns_empty_on_invalid_position() -> bool:
        return IS_WINDOWS


class TestSvelteInvalidPositions:
    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_negative_line_number(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "routes", "Counter.svelte")
        result = language_server.request_containing_symbol(file_path, -1, 0)
        assert result is None or result == {}, f"Expected None/empty for negative line, got {result}"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_negative_character_number(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "routes", "Counter.svelte")
        result = language_server.request_containing_symbol(file_path, 7, -1)
        assert result is None or result == {} or isinstance(result, dict), (
            f"Expected graceful response for negative character, got {result}"
        )

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_line_number_beyond_file_length(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "routes", "Counter.svelte")
        with pytest.raises(IndexError) as exc_info:
            language_server.request_containing_symbol(file_path, 99999, 0)
        assert "list index out of range" in str(exc_info.value), f"Expected bounds error, got {exc_info.value}"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_character_number_beyond_line_length(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "routes", "Counter.svelte")
        result = language_server.request_containing_symbol(file_path, 7, 99999)
        assert result is None or result == {} or isinstance(result, dict), (
            f"Expected graceful response for out-of-range character, got {result}"
        )

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_references_at_negative_line(self, language_server: SolidLanguageServer) -> None:
        from solidlsp.ls_exceptions import SolidLSPException

        file_path = os.path.join("src", "routes", "sverdle", "game.ts")
        try:
            result = language_server.request_references(file_path, -1, 0)
            assert result == [], f"Expected empty list for invalid position when no exception is raised, got {result}"
        except SolidLSPException as exc_info:
            assert "Bad line number" in str(exc_info) or "Debug Failure" in str(exc_info)

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_definition_at_invalid_position(self, language_server: SolidLanguageServer) -> None:
        from solidlsp.ls_exceptions import SolidLSPException

        file_path = os.path.join("src", "routes", "sverdle", "game.ts")
        try:
            result = language_server.request_definition(file_path, -1, 0)
            assert result == [], f"Expected empty list for invalid position when no exception is raised, got {result}"
        except SolidLSPException as exc_info:
            assert "Bad line number" in str(exc_info) or "Debug Failure" in str(exc_info)


class TestSvelteNonExistentFiles:
    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_requesting_on_nonexistent_svelte_file(self, language_server: SolidLanguageServer) -> None:
        nonexistent_file = os.path.join("src", "routes", "DoesNotExist.svelte")
        with pytest.raises(FileNotFoundError):
            language_server.request_references(nonexistent_file, 1, 1)
        with pytest.raises(FileNotFoundError):
            language_server.request_definition(nonexistent_file, 1, 1)
        with pytest.raises(FileNotFoundError):
            language_server.request_document_symbols(nonexistent_file)

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_requesting_on_nonexistent_ts_file(self, language_server: SolidLanguageServer) -> None:
        nonexistent_file = os.path.join("src", "routes", "sverdle", "missing.ts")
        with pytest.raises(FileNotFoundError):
            language_server.request_references(nonexistent_file, 1, 1)
        with pytest.raises(FileNotFoundError):
            language_server.request_definition(nonexistent_file, 1, 1)
        with pytest.raises(FileNotFoundError):
            language_server.request_document_symbols(nonexistent_file)


class TestSvelteEdgeCasePositions:
    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_containing_symbol_at_file_start(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "routes", "Counter.svelte")
        result = language_server.request_containing_symbol(file_path, 0, 0)
        assert result is None or result == {} or isinstance(result, dict), f"Expected graceful response at file start, got {result}"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_references_at_file_start(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "routes", "Counter.svelte")
        result = language_server.request_references(file_path, 0, 0)
        assert result is None or isinstance(result, list), f"Expected list/None at file start, got {type(result)}"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_containing_symbol_template_region(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "routes", "Counter.svelte")
        result = language_server.request_containing_symbol(file_path, 14, 3)
        assert result is None or result == {} or isinstance(result, dict), f"Expected graceful response in template region, got {result}"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_containing_symbol_whitespace_line(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "routes", "Counter.svelte")
        result = language_server.request_containing_symbol(file_path, 12, 0)
        assert result is None or result == {} or isinstance(result, dict), f"Expected graceful response for whitespace line, got {result}"
