import platform
from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.php
class TestPhpLanguageServers:
    @pytest.mark.parametrize("language_server", [Language.PHP, Language.PHP_PHPACTOR], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.PHP], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that the language server starts and stops successfully."""
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.PHP, Language.PHP_PHPACTOR], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.PHP], indirect=True)
    def test_find_definition_within_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:

        # In index.php:
        # Line 9 (1-indexed): $greeting = greet($userName);
        # Line 11 (1-indexed): echo $greeting;
        # We want to find the definition of $greeting (defined on line 9)
        # from its usage in echo $greeting; on line 11.
        # LSP is 0-indexed: definition on line 8, usage on line 10.
        # $greeting in echo $greeting;  (e c h o   $ g r e e t i n g)
        #                           ^ char 5
        # Intelephense uses line 10 (0-indexed), Phpactor uses line 11 (0-indexed)
        if language_server.language_server.language == Language.PHP_PHPACTOR:
            definition_location_list = language_server.request_definition(str(repo_path / "index.php"), 11, 6)
        else:
            definition_location_list = language_server.request_definition(str(repo_path / "index.php"), 10, 6)

        assert definition_location_list, f"Expected non-empty definition_location_list but got {definition_location_list=}"
        if language_server.language_server.language == Language.PHP_PHPACTOR:
            assert len(definition_location_list) >= 1
        else:
            assert len(definition_location_list) == 1
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("index.php")
        # Definition of $greeting is on line 10 (1-indexed) / line 9 (0-indexed), char 0
        assert definition_location["range"]["start"]["line"] == 9
        if language_server.language_server.language != Language.PHP_PHPACTOR:
            assert definition_location["range"]["start"]["character"] == 0

    @pytest.mark.parametrize("language_server", [Language.PHP, Language.PHP_PHPACTOR], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.PHP], indirect=True)
    def test_find_definition_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        # Intelephense uses line 12 (0-indexed), Phpactor uses line 13 (0-indexed)
        if language_server.language_server.language == Language.PHP_PHPACTOR:
            definition_location_list = language_server.request_definition(str(repo_path / "index.php"), 13, 5)
        else:
            definition_location_list = language_server.request_definition(str(repo_path / "index.php"), 12, 5)

        assert definition_location_list, f"Expected non-empty definition_location_list but got {definition_location_list=}"
        if language_server.language_server.language == Language.PHP_PHPACTOR:
            assert len(definition_location_list) >= 1
        else:
            assert len(definition_location_list) == 1
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("helper.php")
        assert definition_location["range"]["start"]["line"] == 2
        if language_server.language_server.language != Language.PHP_PHPACTOR:
            assert definition_location["range"]["start"]["character"] == 0

    @pytest.mark.parametrize("language_server", [Language.PHP, Language.PHP_PHPACTOR], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.PHP], indirect=True)
    def test_find_definition_simple_variable(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        file_path = str(repo_path / "simple_var.php")

        # In simple_var.php:
        # Line 2 (1-indexed): $localVar = "test";
        # Line 3 (1-indexed): echo $localVar;
        # LSP is 0-indexed: definition on line 1, usage on line 2
        # Find definition of $localVar (char 5 on line 3 / 0-indexed: line 2, char 5)
        # $localVar in echo $localVar;  (e c h o   $ l o c a l V a r)
        #                           ^ char 5
        definition_location_list = language_server.request_definition(file_path, 2, 6)  # cursor on 'l' in $localVar

        assert definition_location_list, f"Expected non-empty definition_location_list but got {definition_location_list=}"
        if language_server.language_server.language == Language.PHP_PHPACTOR:
            assert len(definition_location_list) >= 1
        else:
            assert len(definition_location_list) == 1
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("simple_var.php")
        assert definition_location["range"]["start"]["line"] == 1  # Definition of $localVar (0-indexed)
        if language_server.language_server.language != Language.PHP_PHPACTOR:
            assert definition_location["range"]["start"]["character"] == 0  # $localVar (0-indexed)

    @pytest.mark.parametrize("language_server", [Language.PHP, Language.PHP_PHPACTOR], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.PHP], indirect=True)
    def test_find_references_within_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        if language_server.language == Language.PHP_PHPACTOR and platform.system() == "Windows":
            pytest.skip("Phpactor references test not working on Windows, skipping for now")

        index_php_path = str(repo_path / "index.php")

        # In index.php (0-indexed lines):
        # Line 9: $greeting = greet($userName); // Definition of $greeting
        # Line 11: echo $greeting;            // Usage of $greeting
        # Find references for $greeting from its usage in "echo $greeting;" (line 11, char 6 for 'g')
        references = language_server.request_references(index_php_path, 11, 6)

        assert references, f"Expected non-empty references for $greeting but got {references=}"

        if language_server.language_server.language == Language.PHP_PHPACTOR:
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
        else:
            # Intelephense, when asked for references from usage, seems to only return the usage itself.
            assert len(references) == 1, "Expected to find 1 reference for $greeting (the usage itself)"

            expected_locations = [{"uri_suffix": "index.php", "line": 11, "character": 5}]  # Usage: echo $greeting (points to $)

            # Convert actual references to a comparable format and sort
            actual_locations = sorted(
                [
                    {
                        "uri_suffix": loc["uri"].split("/")[-1],
                        "line": loc["range"]["start"]["line"],
                        "character": loc["range"]["start"]["character"],
                    }
                    for loc in references
                ],
                key=lambda x: (x["uri_suffix"], x["line"], x["character"]),
            )

            expected_locations = sorted(expected_locations, key=lambda x: (x["uri_suffix"], x["line"], x["character"]))

            assert actual_locations == expected_locations

    @pytest.mark.parametrize("language_server", [Language.PHP, Language.PHP_PHPACTOR], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.PHP], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        if language_server.language_server.language == Language.PHP_PHPACTOR and platform.system() == "Windows":
            pytest.skip("Phpactor references test not working on Windows, skipping for now")

        helper_php_path = str(repo_path / "helper.php")
        # In index.php (0-indexed lines):
        # Line 13: helperFunction(); // Usage of helperFunction
        # Find references for helperFunction from its definition
        references = language_server.request_references(helper_php_path, 2, len("function "))

        assert references, f"Expected non-empty references for helperFunction but got {references=}"

        if language_server.language_server.language == Language.PHP_PHPACTOR:
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
        else:
            # Intelephense might return 1 (usage) or 2 (usage + definition) references.
            # Let's check for at least the usage in index.php
            # Definition is in helper.php, line 2, char 0 (based on previous findings)
            # Usage is in index.php, line 13, char 0
            actual_locations_comparable = []
            for loc in references:
                actual_locations_comparable.append(
                    {
                        "uri_suffix": loc["uri"].split("/")[-1],
                        "line": loc["range"]["start"]["line"],
                        "character": loc["range"]["start"]["character"],
                    }
                )

            usage_in_index_php = {"uri_suffix": "index.php", "line": 13, "character": 0}
            assert usage_in_index_php in actual_locations_comparable, "Usage of helperFunction in index.php not found"
