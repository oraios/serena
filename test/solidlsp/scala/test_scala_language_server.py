import logging
import os

import pytest

from solidlsp.language_servers.scala_language_server import ScalaLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings


@pytest.fixture(scope="module")
def scala_ls():
    # Define the path to your test Scala repository
    repo_root = os.path.abspath("test/resources/repos/scala")

    # Create a dummy logger
    logger = LanguageServerLogger(logging.getLogger(__name__))

    # Create a LanguageServerConfig for Scala
    config = LanguageServerConfig(code_language=Language.SCALA)

    # Create SolidLSPSettings
    solidlsp_settings = SolidLSPSettings()

    # Instantiate the ScalaLanguageServer
    ls = ScalaLanguageServer(config, logger, repo_root, solidlsp_settings)

    # Start the server and yield it for tests
    with ls.start_server():
        yield ls


def test_scala_document_symbols(scala_ls):
    # Test document symbols for Main.scala
    relative_file_path = "src/main/scala/Main.scala"
    symbols, _ = scala_ls.request_document_symbols(relative_file_path)

    # Assert that expected symbols are found
    symbol_names = [s["name"] for s in symbols]
    assert "Main" in symbol_names
    assert "main" in symbol_names
    assert "add" in symbol_names

    # You can add more specific assertions about symbol kinds, ranges, etc.
    main_object = next(s for s in symbols if s["name"] == "Main")
    assert main_object["kind"] == 2  # Module (or Object in Scala's case)

    main_method = next(s for s in symbols if s["name"] == "main")
    assert main_method["kind"] == 6  # Method

    add_method = next(s for s in symbols if s["name"] == "add")
    assert add_method["kind"] == 6  # Method
