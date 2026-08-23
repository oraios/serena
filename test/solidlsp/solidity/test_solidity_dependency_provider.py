import os
import platform
import shlex
from pathlib import Path

import pytest

from solidlsp.language_servers.solidity_language_server import SolidityLanguageServer
from solidlsp.settings import SolidLSPSettings


@pytest.fixture
def provider(tmp_path: Path) -> SolidityLanguageServer.DependencyProvider:
    return SolidityLanguageServer.DependencyProvider(
        SolidLSPSettings.CustomLSSettings({}),
        str(tmp_path / "language-server-resources"),
    )


def test_darwin_uses_isolated_state_dir_and_preserves_node_options(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_dir = tmp_path / "solidity state"
    existing_node_options = "--max-old-space-size=2048 --trace-warnings"
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setenv("NODE_OPTIONS", existing_node_options)

    provider = SolidityLanguageServer.DependencyProvider(
        SolidLSPSettings.CustomLSSettings({"solidity_state_dir": str(state_dir)}),
        str(tmp_path / "language-server-resources"),
    )

    launch_env = provider.create_launch_command_env()

    assert launch_env["SERENA_SOLIDITY_STATE_DIR"] == str(state_dir)
    assert state_dir.is_dir()
    assert launch_env["NODE_OPTIONS"] == (f"{existing_node_options} --require {shlex.quote(provider._HOMEDIR_PRELOAD)}")
    assert "HOME" not in launch_env
    assert os.environ["NODE_OPTIONS"] == existing_node_options


def test_darwin_defaults_state_dir_under_language_server_resources(
    provider: SolidityLanguageServer.DependencyProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")

    launch_env = provider.create_launch_command_env()

    assert launch_env["SERENA_SOLIDITY_STATE_DIR"] == str(Path(provider._ls_resources_dir) / "solidity-state")
    assert Path(launch_env["SERENA_SOLIDITY_STATE_DIR"]).is_dir()


def test_non_darwin_does_not_add_state_isolation(
    monkeypatch: pytest.MonkeyPatch, provider: SolidityLanguageServer.DependencyProvider
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    launch_env = provider.create_launch_command_env()

    assert "SERENA_SOLIDITY_STATE_DIR" not in launch_env
    assert "NODE_OPTIONS" not in launch_env
