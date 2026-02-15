import pytest

from serena.constants import REPO_ROOT
from serena.jetbrains.jetbrains_plugin_client import JetBrainsPluginClient


class TestSerenaJetBrainsPluginClient:
    @pytest.mark.parametrize(
        "serena_path, plugin_path",
        [
            (REPO_ROOT, REPO_ROOT),
            ("/home/user/project", "/home/user/project"),
            ("/home/user/project", "//wsl.localhost/Ubuntu-24.04/home/user/project"),
            ("/home/user/project", "//wsl$/Ubuntu/home/user/project"),
            ("/home/user/project", "//wsl$/Ubuntu/home/user/project"),
            ("/mnt/c/Users/user/projects/my-app", "/workspaces/serena/C:/Users/user/projects/my-app"),
        ],
    )
    def test_path_matching(self, serena_path, plugin_path) -> None:
        assert JetBrainsPluginClient._paths_match(serena_path, plugin_path)
