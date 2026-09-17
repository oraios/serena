# SPDX-License-Identifier: MIT

from solidlsp.language_servers.dart_language_server import DartLanguageServer


def _make_dart_ls(custom_settings: dict | None = None) -> DartLanguageServer:
    ls = object.__new__(DartLanguageServer)
    ls._custom_settings = custom_settings or {}
    ls.repository_root_path = "/tmp/fake-dart-project"

    class _Cfg:
        @staticmethod
        def get_absolute_workspace_folders(root):
            return [root]

        @staticmethod
        def get_absolute_additional_workspace_folders(root):
            return []

    ls.config = _Cfg()
    # custom_settings property reads from _custom_settings on SolidLanguageServer
    return ls


def test_dart_defaults_to_omitting_root_uri():
    builder = _make_dart_ls()._create_initialize_params_builder()
    params = builder.build()
    assert params["rootUri"] is None
    assert params["rootPath"] is None
    assert params["workspaceFolders"]


def test_dart_can_opt_back_into_root_uri():
    builder = _make_dart_ls({"set_root_uri": True})._create_initialize_params_builder()
    params = builder.build()
    assert "rootUri" in params
    assert "rootPath" in params
