# SPDX-License-Identifier: MIT

import tempfile
from pathlib import Path

from solidlsp.initialize_params import DefaultInitializeParamsBuilder


class _FakeLS:
    # Windows: as_uri() rejects drive-less paths like "/tmp/..."
    repository_root_path = str(Path(tempfile.mkdtemp(prefix="fake-project-")) / "root")

    class config:
        @staticmethod
        def get_absolute_workspace_folders(root):
            return [root]

        @staticmethod
        def get_absolute_additional_workspace_folders(root):
            return []

    custom_settings: dict = {}


def test_default_builder_sets_root_uri():
    builder = DefaultInitializeParamsBuilder(_FakeLS())
    params = builder.build()
    assert "rootUri" in params
    assert "rootPath" in params


def test_builder_sends_null_root_uri_when_disabled():
    builder = DefaultInitializeParamsBuilder(_FakeLS(), set_root_uri=False)
    params = builder.build()
    # keys must be present (some servers reject an undefined rootUri); values are null
    assert params["rootUri"] is None
    assert params["rootPath"] is None
    assert params["processId"] is not None
    assert params["clientInfo"] == {"name": "Serena"}
