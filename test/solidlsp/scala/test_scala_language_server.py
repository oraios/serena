import logging
import os

import pytest

from solidlsp.language_servers.scala_language_server import ScalaLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings

RELATIVE_FILE_PATH = "src/main/scala/Main.scala"
MAIN_FILE_PATH = "src/main/scala/Main.scala"
TEST_POSITIONS = [
    (18, 15),
    (18, 12),
    (19, 15),
]
EXPECTED_FILE_PATTERN = "Main.scala"
EXPECTED_SYMBOLS = ["Main", "main", "add", "processUser"]
EXPECTED_FILE_PATTERNS = ["Utils.scala", "Main.scala"]


@pytest.fixture(scope="module")
def scala_ls():
    repo_root = os.path.abspath("test/resources/repos/scala")
    logger = LanguageServerLogger(json_format=False, log_level=logging.INFO)
    config = LanguageServerConfig(code_language=Language.SCALA)
    solidlsp_settings = SolidLSPSettings()
    ls = ScalaLanguageServer(config, logger, repo_root, solidlsp_settings)

    with ls.start_server():
        yield ls


def test_scala_document_symbols(scala_ls):
    """Test document symbols for Main.scala"""
    symbols, _ = scala_ls.request_document_symbols(MAIN_FILE_PATH)
    symbol_names = [s["name"] for s in symbols]

    assert symbol_names[0] == "com.example"
    assert symbol_names[1] == "Main"
    assert symbol_names[2] == "main"
    assert symbol_names[7] == "add"
    assert symbol_names[8] == "processUser"

    assert symbols[0]["kind"] == 4
    assert symbols[1]["kind"] == 2
    assert symbols[2]["kind"] == 6
    assert symbols[7]["kind"] == 6
    assert symbols[8]["kind"] == 6


def test_scala_references_within_same_file(scala_ls):
    """Test finding references within the same file."""
    references_results = []
    for line, char in TEST_POSITIONS:
        refs = scala_ls.request_references(MAIN_FILE_PATH, line, char)
        references_results.append(refs)

    assert references_results[0] == []
    assert references_results[1] == []
    assert len(references_results[2]) == 1

    first_ref = references_results[2][0]
    assert first_ref["uri"].endswith("Main.scala")
    assert first_ref["range"]["start"]["line"] == 19
    assert first_ref["range"]["start"]["character"] == 14
    assert first_ref["range"]["end"]["line"] == 19
    assert first_ref["range"]["end"]["character"] == 17


def test_scala_find_definition_and_references_across_files(scala_ls):
    definitions = scala_ls.request_definition(MAIN_FILE_PATH, 8, 25)
    assert len(definitions) == 1

    first_def = definitions[0]
    assert first_def["uri"].endswith("Utils.scala")
    assert first_def["range"]["start"]["line"] == 7
    assert first_def["range"]["start"]["character"] == 6
    assert first_def["range"]["end"]["line"] == 7
    assert first_def["range"]["end"]["character"] == 14

    references = scala_ls.request_references(MAIN_FILE_PATH, 8, 25)
    assert len(references) >= 1

    first_ref = references[0]
    assert first_ref["uri"].endswith("Main.scala")
    assert first_ref["range"]["start"]["line"] == 8
    assert first_ref["range"]["start"]["character"] == 23
    assert first_ref["range"]["end"]["line"] == 8
    assert first_ref["range"]["end"]["character"] == 31
