from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.php
class TestPhpDevsenseLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.PHP_DEVSENSE], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.PHP], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that the Devsense language server starts and stops successfully."""
        # The fixture already handles start and stop
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.PHP_DEVSENSE], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.PHP], indirect=True)
    def test_find_definition_within_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that Devsense can find definitions within a single file."""
        # In index.php:
        # Line 9 (1-indexed): $greeting = greet($userName);
        # Line 11 (1-indexed): echo $greeting;
        # We want to find the definition of $greeting (defined on line 9)
        # from its usage in echo $greeting; on line 11.
        # LSP is 0-indexed: definition on line 8, usage on line 10.
        # $greeting in echo $greeting; is at char 5 on line 11 (0-indexed: line 10, char 5)
        # e c h o   $ g r e e t i n g
        #           ^ char 5
        definition_location_list = language_server.request_definition(str(repo_path / "index.php"), 10, 6)  # cursor on 'g' in $greeting

        assert definition_location_list, f"Expected non-empty definition_location_list but got {definition_location_list=}"
        assert len(definition_location_list) == 1
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("index.php")
        # Definition of $greeting is on line 10 (1-indexed) / line 9 (0-indexed), char 0
        assert definition_location["range"]["start"]["line"] == 9
        assert definition_location["range"]["start"]["character"] == 0

    @pytest.mark.parametrize("language_server", [Language.PHP_DEVSENSE], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.PHP], indirect=True)
    def test_find_definition_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that Devsense can find definitions across multiple files."""
        definition_location_list = language_server.request_definition(str(repo_path / "index.php"), 12, 5)  # helperFunction

        assert definition_location_list, f"Expected non-empty definition_location_list but got {definition_location_list=}"
        assert len(definition_location_list) == 1
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("helper.php")
        assert definition_location["range"]["start"]["line"] == 2
        assert definition_location["range"]["start"]["character"] == 0

    @pytest.mark.parametrize("language_server", [Language.PHP_DEVSENSE], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.PHP], indirect=True)
    def test_find_references_within_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that Devsense can find references within a file."""
        index_php_path = str(repo_path / "index.php")

        # In index.php (0-indexed lines):
        # Line 9: $greeting = greet($userName); // Definition of $greeting
        # Line 11: echo $greeting;            // Usage of $greeting
        # Find references for $greeting from its usage in "echo $greeting;" (line 11, char 6 for 'g')
        references = language_server.request_references(index_php_path, 11, 6)

        assert references, "Expected to find references for $greeting"
        assert len(references) >= 1, "Expected to find at least 1 reference for $greeting"
