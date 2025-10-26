from __future__ import annotations

import pathlib
from collections.abc import Iterable

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.language_servers.gdscript_language_server import GDScriptLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings
from test.conftest import create_ls, get_repo_path

pytestmark = pytest.mark.gdscript


def ensure_server_ready(language_server: SolidLanguageServer, timeout: float = 180.0) -> GDScriptLanguageServer:
    ls = language_server.language_server
    if not isinstance(ls, GDScriptLanguageServer):
        raise AssertionError(f"Expected GDScriptLanguageServer, got {type(ls)}")
    if not ls.server_ready.wait(timeout):
        raise AssertionError("GDScript language server did not report ready in time")
    if not ls.completions_available.wait(timeout):
        raise AssertionError("GDScript language server did not make completions available in time")
    return ls


@pytest.fixture()
def logger() -> LanguageServerLogger:
    return LanguageServerLogger()


@pytest.fixture()
def solidlsp_settings(tmp_path: pathlib.Path) -> SolidLSPSettings:
    return SolidLSPSettings(
        solidlsp_dir=str(tmp_path / "serena"),
        project_data_relative_path="project",
        ls_specific_settings={},
    )


@pytest.fixture(scope="module")
def gdscript_repo_path() -> pathlib.Path:
    return get_repo_path(Language.GDSCRIPT)


@pytest.fixture(scope="module")
def gdscript_ls_with_ignored_dirs(gdscript_repo_path: pathlib.Path) -> Iterable[SolidLanguageServer]:
    ignored = ["scripts", "custom_test"]
    ls = create_ls(language=Language.GDSCRIPT, repo_path=str(gdscript_repo_path), ignored_paths=ignored)
    ls.start()
    try:
        ensure_server_ready(ls)
        yield ls
    finally:
        try:
            ls.stop()
        except SolidLSPException:
            pass


def find_identifier_position(file_path: pathlib.Path, identifier: str) -> tuple[int, int]:
    for line_number, line in enumerate(file_path.read_text().splitlines()):
        column = line.find(identifier)
        if column != -1:
            return line_number, column
    raise AssertionError(f"Identifier '{identifier}' not found in {file_path}")
