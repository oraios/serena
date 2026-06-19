"""Unit tests for the Unreal Engine missing-compile_commands warning (see #1566).

These do not start a clangd process; they exercise the no-database early return of
``ClangdLanguageServer._prepare_compile_commands`` directly, so they run in the default
test suite without the ``cpp`` marker.
"""

import logging

from solidlsp.language_servers.clangd_language_server import ClangdLanguageServer


def _make_server(root) -> ClangdLanguageServer:
    """Build a ClangdLanguageServer shell with only the attribute that the
    no-database early return of ``_prepare_compile_commands`` reads.
    """
    server = object.__new__(ClangdLanguageServer)
    server.repository_root_path = str(root)
    return server


def test_missing_compile_commands_warns_for_unreal_project(tmp_path, caplog):
    (tmp_path / "MyGame.uproject").write_text("{}")
    server = _make_server(tmp_path)

    with caplog.at_level(logging.WARNING):
        result = server._prepare_compile_commands()

    assert result is None
    assert any("Unreal Engine" in message and "unreal_engine_setup_guide_for_serena.md" in message for message in caplog.messages)


def test_missing_compile_commands_silent_for_non_unreal_project(tmp_path, caplog):
    server = _make_server(tmp_path)

    with caplog.at_level(logging.WARNING):
        result = server._prepare_compile_commands()

    assert result is None
    assert not any("Unreal Engine" in message for message in caplog.messages)


def test_is_unreal_engine_project_detection(tmp_path):
    server = _make_server(tmp_path)
    assert server._is_unreal_engine_project() is False

    (tmp_path / "Game.uproject").write_text("{}")
    assert server._is_unreal_engine_project() is True
