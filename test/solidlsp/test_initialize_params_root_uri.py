# SPDX-License-Identifier: MIT

from solidlsp.initialize_params import DefaultInitializeParamsBuilder


class _FakeLS:
    repository_root_path = "/tmp/fake-project"

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


def test_builder_can_omit_root_uri():
    builder = DefaultInitializeParamsBuilder(_FakeLS(), set_root_uri=False)
    params = builder.build()
    assert "rootUri" not in params
    assert "rootPath" not in params
    assert params["processId"] is not None
    assert params["clientInfo"] == {"name": "Serena"}
