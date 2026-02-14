# type: ignore
import os

import pytest

from solidlsp.language_servers.scala_language_server import ScalaLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.settings import SolidLSPSettings

pytest.skip("Scala must be compiled for these tests to run through, which is a huge hassle", allow_module_level=True)

MAIN_FILE_PATH = os.path.join("src", "main", "scala", "com", "example", "Main.scala")

pytestmark = pytest.mark.scala


@pytest.fixture(scope="module")
def scala_ls():
    repo_root = os.path.abspath("test/resources/repos/scala")
    config = LanguageServerConfig(code_language=Language.SCALA)
    solidlsp_settings = SolidLSPSettings()
    ls = ScalaLanguageServer(config, repo_root, solidlsp_settings)

    with ls.start_server():
        yield ls


def test_scala_document_symbols(scala_ls):
    """Test document symbols for Main.scala"""
    symbols, _ = scala_ls.request_document_symbols(MAIN_FILE_PATH).get_all_symbols_and_roots()
    symbol_names = [s["name"] for s in symbols]
    assert symbol_names[0] == "com.example"
    assert symbol_names[1] == "Main"
    assert symbol_names[2] == "main"
    assert symbol_names[3] == "result"
    assert symbol_names[4] == "sum"
    assert symbol_names[5] == "add"
    assert symbol_names[6] == "someMethod"
    assert symbol_names[7] == "str"
    assert symbol_names[8] == "Config"
    assert symbol_names[9] == "field1"  # confirm https://github.com/oraios/serena/issues/688


def test_scala_references_within_same_file(scala_ls):
    """Test finding references within the same file."""
    definitions = scala_ls.request_definition(MAIN_FILE_PATH, 12, 23)
    first_def = definitions[0]
    assert first_def["uri"].endswith("Main.scala")
    assert first_def["range"]["start"]["line"] == 16
    assert first_def["range"]["start"]["character"] == 6
    assert first_def["range"]["end"]["line"] == 16
    assert first_def["range"]["end"]["character"] == 9


def test_scala_find_definition_and_references_across_files(scala_ls):
    definitions = scala_ls.request_definition(MAIN_FILE_PATH, 8, 25)
    assert len(definitions) == 1

    first_def = definitions[0]
    assert first_def["uri"].endswith("Utils.scala")
    assert first_def["range"]["start"]["line"] == 7
    assert first_def["range"]["start"]["character"] == 6
    assert first_def["range"]["end"]["line"] == 7
    assert first_def["range"]["end"]["character"] == 14
