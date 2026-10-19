"""
Unit tests for ``VueLanguageServer._setup_runtime_dependencies`` that need neither node nor npm.
"""

import os
import shutil

import pytest

from solidlsp.language_servers.common import RuntimeDependencyCollection
from solidlsp.language_servers.vue_language_server import VueLanguageServer, VueRuntimePaths
from solidlsp.ls_config import LanguageServerConfig, LanguageServerId
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.settings import SolidLSPSettings

VUE_VERSION = "3.1.5"
TS_VERSION = "5.9.3"
TS_LS_VERSION = "5.1.3"


def _settings(tmp_path, vue: dict | None = None) -> SolidLSPSettings:
    return SolidLSPSettings(
        solidlsp_dir=str(tmp_path / "solidlsp"),
        ls_specific_settings={
            LanguageServerId.VUE: vue or {},
            LanguageServerId.TYPESCRIPT: {"typescript_version": TS_VERSION, "typescript_language_server_version": TS_LS_VERSION},
        },
    )


def _setup(settings: SolidLSPSettings) -> VueRuntimePaths:
    return VueLanguageServer._setup_runtime_dependencies(LanguageServerConfig(ls_id=LanguageServerId.VUE), settings)


@pytest.fixture
def no_node_tooling(monkeypatch) -> list[str]:
    """Hides node/npm from PATH lookups and records any attempted installation."""
    install_calls: list[str] = []
    real_which = shutil.which
    monkeypatch.setattr(shutil, "which", lambda name, *a, **kw: None if name in ("node", "npm") else real_which(name, *a, **kw))
    monkeypatch.setattr(RuntimeDependencyCollection, "install", lambda self, target_dir: install_calls.append(target_dir))
    return install_calls


def _only_node_on_path(monkeypatch) -> None:
    real_which = shutil.which
    fake = {"node": "/usr/bin/node", "npm": None}
    monkeypatch.setattr(shutil, "which", lambda name, *a, **kw: fake[name] if name in fake else real_which(name, *a, **kw))


def _write_managed_install(settings: SolidLSPSettings, marker: str) -> str:
    vue_ls_dir = os.path.join(VueLanguageServer.ls_resources_dir(settings), "vue-lsp")
    bin_dir = os.path.join(vue_ls_dir, "node_modules", ".bin")
    os.makedirs(bin_dir)
    suffix = ".cmd" if os.name == "nt" else ""
    for exe in ("vue-language-server", "typescript-language-server"):
        with open(os.path.join(bin_dir, exe + suffix), "w") as f:
            f.write("")
    with open(os.path.join(vue_ls_dir, ".installed_version"), "w") as f:
        f.write(marker)
    return vue_ls_dir


def test_custom_ls_path_bypasses_managed_installation(tmp_path, no_node_tooling) -> None:
    settings = _settings(
        tmp_path,
        {
            "ls_path": "/opt/vue/vue-language-server",
            "ts_ls_path": "/opt/vue/typescript-language-server",
            "tsdk_path": "/opt/vue/typescript/lib",
            "vue_plugin_path": "/opt/vue/@vue/typescript-plugin",
        },
    )

    paths = _setup(settings)

    assert paths == VueRuntimePaths(
        vue_ls_cmd=["/opt/vue/vue-language-server", "--stdio"],
        ts_ls_executable_path="/opt/vue/typescript-language-server",
        tsdk_path="/opt/vue/typescript/lib",
        vue_plugin_path="/opt/vue/@vue/typescript-plugin",
    )
    assert no_node_tooling == []


def test_custom_ls_base_cmd_takes_precedence_over_ls_path(tmp_path, no_node_tooling) -> None:
    settings = _settings(
        tmp_path,
        {
            "ls_base_cmd": ["node", "/opt/vue/server.js"],
            "ls_path": "/ignored",
            "ts_ls_path": "/opt/ts-ls",
            "tsdk_path": "/opt/tsdk",
            "vue_plugin_path": "/opt/plugin",
        },
    )

    assert _setup(settings).vue_ls_cmd == ["node", "/opt/vue/server.js", "--stdio"]


def test_custom_ls_path_without_companion_paths_is_rejected(tmp_path, no_node_tooling) -> None:
    settings = _settings(tmp_path, {"ls_path": "/opt/vue/vue-language-server", "ts_ls_path": "/opt/ts-ls"})

    with pytest.raises(SolidLSPException, match="missing: 'tsdk_path', 'vue_plugin_path'"):
        _setup(settings)


def test_up_to_date_managed_installation_does_not_require_npm(tmp_path, monkeypatch, no_node_tooling) -> None:
    # node is still needed to run the managed shims, npm only for installing
    _only_node_on_path(monkeypatch)
    settings = _settings(tmp_path)
    vue_ls_dir = _write_managed_install(settings, f"{VUE_VERSION}_{TS_VERSION}_{TS_LS_VERSION}")

    paths = _setup(settings)

    assert no_node_tooling == []
    assert paths.tsdk_path == os.path.join(vue_ls_dir, "node_modules", "typescript", "lib")
    assert paths.vue_plugin_path == os.path.join(vue_ls_dir, "node_modules", "@vue", "typescript-plugin")


def test_installation_without_npm_raises_instead_of_asserting(tmp_path, monkeypatch, no_node_tooling) -> None:
    _only_node_on_path(monkeypatch)
    settings = _settings(tmp_path)
    _write_managed_install(settings, "outdated")

    with pytest.raises(SolidLSPException, match="npm is not installed"):
        _setup(settings)
    assert no_node_tooling == []


def test_managed_installation_without_node_raises(tmp_path, no_node_tooling) -> None:
    with pytest.raises(SolidLSPException, match="node is not installed"):
        _setup(_settings(tmp_path))
