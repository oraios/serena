"""Basic tests for BSL Language Server integration."""

import os
import shutil

import pytest

from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.settings import SolidLSPSettings

REPO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "resources", "repos", "bsl", "test_repo"))

_java_available = shutil.which("java") is not None
_skip_if_no_java = pytest.mark.skipif(not _java_available, reason="Java is not installed")


@pytest.fixture(scope="module")
def bsl_ls():
    config = LanguageServerConfig(code_language=Language.BSL)
    settings = SolidLSPSettings()
    ls_class = Language.BSL.get_ls_class()
    server = ls_class(config, REPO_PATH, settings)
    server.start()
    yield server
    server.stop()


@pytest.mark.bsl
@pytest.mark.slow
@_skip_if_no_java
def test_bsl_server_starts(bsl_ls):
    assert bsl_ls.server_ready.is_set()


@pytest.mark.bsl
@pytest.mark.slow
@_skip_if_no_java
def test_bsl_document_symbols(bsl_ls):
    symbols = bsl_ls.request_document_symbols("CommonModule.bsl")
    names = [s.get("name") for s in symbols.iter_symbols()]
    assert "ВывестиСообщение" in names
    assert "ПолучитьПриветствие" in names
    assert "ВызватьПриветствие" in names


@pytest.mark.bsl
@pytest.mark.slow
@_skip_if_no_java
def test_bsl_find_references(bsl_ls):
    # find references to ПолучитьПриветствие defined in CommonModule.bsl
    refs = bsl_ls.request_references("CommonModule.bsl", line=6, column=10)
    assert len(refs) >= 1


def test_bsl_filename_matcher():
    matcher = Language.BSL.get_source_fn_matcher()
    assert matcher.is_relevant_filename("module.bsl")
    assert matcher.is_relevant_filename("script.os")
    assert not matcher.is_relevant_filename("module.py")


def test_bsl_enum_registration():
    assert Language.BSL.value == "bsl"
    assert Language.BSL.get_ls_class().__name__ == "BSLLanguageServer"
