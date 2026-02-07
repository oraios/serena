from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.php
class TestPhpPhpactorLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.PHP_PHPACTOR], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.PHP], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that the phpactor language server starts and stops successfully."""
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.PHP_PHPACTOR], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.PHP], indirect=True)
    def test_find_definition_within_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        # In index.php (0-indexed lines):
        # Line 9: $greeting = greet($userName);
        # Line 11: echo $greeting;
        # Find the definition of $greeting from its usage on line 11 (0-indexed), char 6
        definition_location_list = language_server.request_definition(str(repo_path / "index.php"), 11, 6)

        assert definition_location_list, f"Expected non-empty definition_location_list but got {definition_location_list=}"
        assert len(definition_location_list) >= 1
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("index.php")
        assert definition_location["range"]["start"]["line"] == 9

    @pytest.mark.parametrize("language_server", [Language.PHP_PHPACTOR], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.PHP], indirect=True)
    def test_find_definition_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        # In index.php (0-indexed lines):
        # Line 13: helperFunction();
        # Find the definition of helperFunction which is in helper.php, line 2 (0-indexed)
        definition_location_list = language_server.request_definition(str(repo_path / "index.php"), 13, 5)

        assert definition_location_list, f"Expected non-empty definition_location_list but got {definition_location_list=}"
        assert len(definition_location_list) >= 1
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("helper.php")
        assert definition_location["range"]["start"]["line"] == 2

    @pytest.mark.parametrize("language_server", [Language.PHP_PHPACTOR], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.PHP], indirect=True)
    def test_find_definition_simple_variable(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        file_path = str(repo_path / "simple_var.php")

        # In simple_var.php (0-indexed lines):
        # Line 1: $localVar = "test";
        # Line 2: echo $localVar;
        # Find definition of $localVar from its usage on line 2, char 6
        definition_location_list = language_server.request_definition(file_path, 2, 6)

        assert definition_location_list, f"Expected non-empty definition_location_list but got {definition_location_list=}"
        assert len(definition_location_list) >= 1
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("simple_var.php")
        assert definition_location["range"]["start"]["line"] == 1

    @pytest.mark.parametrize("language_server", [Language.PHP_PHPACTOR], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.PHP], indirect=True)
    def test_find_references_within_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        index_php_path = str(repo_path / "index.php")

        # In index.php (0-indexed lines):
        # Line 9: $greeting = greet($userName);  // Definition of $greeting
        # Line 11: echo $greeting;               // Usage of $greeting
        # Find references for $greeting from its usage on line 11, char 6
        references = language_server.request_references(index_php_path, 11, 6)

        assert references, f"Expected non-empty references for $greeting but got {references=}"

        actual_locations = [
            {
                "uri_suffix": loc["uri"].split("/")[-1],
                "line": loc["range"]["start"]["line"],
            }
            for loc in references
        ]

        # Check that at least one reference points to $greeting usage in index.php
        matching = [loc for loc in actual_locations if loc["uri_suffix"] == "index.php" and loc["line"] == 11]
        assert matching, f"Expected reference to $greeting on line 11 of index.php, got {actual_locations}"

    @pytest.mark.parametrize("language_server", [Language.PHP_PHPACTOR], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.PHP], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        helper_php_path = str(repo_path / "helper.php")

        # Find references for helperFunction from its definition in helper.php
        # Line 2 (0-indexed): function helperFunction(): void {
        references = language_server.request_references(helper_php_path, 2, len("function "))

        assert references, f"Expected non-empty references for helperFunction but got {references=}"

        actual_locations_comparable = []
        for loc in references:
            actual_locations_comparable.append(
                {
                    "uri_suffix": loc["uri"].split("/")[-1],
                    "line": loc["range"]["start"]["line"],
                }
            )

        # Check that helperFunction usage in index.php line 13 is found
        matching = [loc for loc in actual_locations_comparable if loc["uri_suffix"] == "index.php" and loc["line"] == 13]
        assert matching, f"Usage of helperFunction in index.php (line 13) not found in {actual_locations_comparable}"
