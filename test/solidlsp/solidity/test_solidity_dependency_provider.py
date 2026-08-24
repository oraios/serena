import os
import platform
import shutil
import subprocess
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
    assert launch_env["NODE_OPTIONS"] == (
        f"{existing_node_options} --require {provider._quote_node_option_argument(provider._HOMEDIR_PRELOAD)}"
    )
    assert "HOME" not in launch_env
    assert os.environ["NODE_OPTIONS"] == existing_node_options


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for this test")
def test_darwin_node_options_loads_preload_path_with_spaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.delenv("NODE_OPTIONS", raising=False)

    preload_path = tmp_path / "solidity state" / "preload.cjs"
    preload_path.parent.mkdir()
    preload_path.write_text("console.log('PRELOAD_LOADED_OK')", encoding="utf-8")
    provider = SolidityLanguageServer.DependencyProvider(
        SolidLSPSettings.CustomLSSettings({"solidity_state_dir": str(tmp_path / "state dir")}),
        str(tmp_path / "language-server-resources"),
    )
    monkeypatch.setattr(provider, "_HOMEDIR_PRELOAD", str(preload_path))

    launch_env = provider.create_launch_command_env()
    result = subprocess.run(
        ["node", "-e", "console.log('NODE_STARTED_OK')"],
        env={**os.environ, **launch_env},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "PRELOAD_LOADED_OK" in result.stdout
    assert "NODE_STARTED_OK" in result.stdout


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
