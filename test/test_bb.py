import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from solidlsp.language_servers.pyright_server import PyrightServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger


def test_request_text_document_diagnostics():
    ls_config = LanguageServerConfig(
        code_language=Language.PYTHON,
        ignored_paths=[],
        trace_lsp_communication= False,
    )

    ls_logger = LanguageServerLogger(log_level= logging.DEBUG)


    pyright_server = PyrightServer(ls_config, logger=ls_logger, repository_root_path=("/Users/shouheihei1/Documents/GitHub/serena/"))
    pyright_server.start()
    result = pyright_server.request_text_document_diagnostics("test/resources/repos/python/test_repo/examples/user_management.py")
    print(result)

test_request_text_document_diagnostics()

