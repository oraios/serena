# SPDX-License-Identifier: MIT

import tempfile
from pathlib import Path

from solidlsp.language_servers.dart_language_server import DartLanguageServer


def _make_dart_ls() -> DartLanguageServer:
    ls = object.__new__(DartLanguageServer)
    ls._custom_settings = {}
    # Windows: as_uri() rejects drive-less paths like "/tmp/..."
    project_dir = Path(tempfile.mkdtemp(prefix="fake-dart-project-")) / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    ls.repository_root_path = str(project_dir)

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


def test_dart_omits_root_uri():
    builder = _make_dart_ls()._create_initialize_params_builder()
    params = builder.build()
    # rootUri must be present (some servers reject an undefined key) but null, so that only
    # workspaceFolders determine the analysis roots (oraios/serena#2045).
    assert params["rootUri"] is None
    assert params["rootPath"] is None
    assert params["workspaceFolders"]
