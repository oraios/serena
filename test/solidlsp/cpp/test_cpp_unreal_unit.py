"""Unreal Engine handling in the clangd and ccls servers, without starting a process.

No ``cpp`` marker: these build server shells with ``object.__new__`` and call the no-database
and directory-ignore code paths directly, so they run in the default suite.
"""

import pytest

from solidlsp.language_servers.ccls_language_server import CCLS
from solidlsp.language_servers.clangd_language_server import ClangdLanguageServer
from solidlsp.language_servers.common import UE_IGNORED_DIRNAMES, is_unreal_engine_project
from solidlsp.ls_exceptions import SolidLSPException


def _make_clangd(root) -> ClangdLanguageServer:
    server = object.__new__(ClangdLanguageServer)
    server.repository_root_path = str(root)
    return server


def _make_ccls(root) -> CCLS:
    server = object.__new__(CCLS)
    server.repository_root_path = str(root)
    return server


def test_is_unreal_engine_project_detection(tmp_path):
    assert is_unreal_engine_project(str(tmp_path)) is False
    (tmp_path / "MyGame.uproject").write_text("{}")
    assert is_unreal_engine_project(str(tmp_path)) is True


def test_missing_compile_commands_raises_for_unreal_project(tmp_path):
    (tmp_path / "MyGame.uproject").write_text("{}")
    server = _make_clangd(tmp_path)

    with pytest.raises(SolidLSPException, match="Unreal Engine"):
        server._prepare_compile_commands()


def test_missing_compile_commands_returns_none_for_non_unreal_project(tmp_path):
    server = _make_clangd(tmp_path)
    assert server._prepare_compile_commands() is None


def test_empty_compile_commands_raises_for_unreal_project(tmp_path):
    (tmp_path / "MyGame.uproject").write_text("{}")
    (tmp_path / "compile_commands.json").write_text("[]")
    server = _make_clangd(tmp_path)

    with pytest.raises(SolidLSPException, match="Unreal Engine"):
        server._prepare_compile_commands()


def test_empty_compile_commands_returns_none_for_non_unreal_project(tmp_path):
    (tmp_path / "compile_commands.json").write_text("[]")
    server = _make_clangd(tmp_path)
    assert server._prepare_compile_commands() is None


@pytest.mark.parametrize("make_server", [_make_clangd, _make_ccls])
def test_unreal_dirs_ignored_only_for_unreal_project(make_server, tmp_path):
    non_ue = make_server(tmp_path)
    for dirname in UE_IGNORED_DIRNAMES:
        assert not non_ue.is_ignored_dirname(dirname), f"{dirname} should not be pruned without a .uproject"

    ue_root = tmp_path / "ue"
    ue_root.mkdir()
    (ue_root / "MyGame.uproject").write_text("{}")
    ue = make_server(ue_root)
    for dirname in UE_IGNORED_DIRNAMES:
        assert ue.is_ignored_dirname(dirname), f"{dirname} should be pruned for a UE project"

    assert non_ue.is_ignored_dirname(".ccls-cache")
    assert ue.is_ignored_dirname(".ccls-cache")
