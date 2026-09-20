# SPDX-License-Identifier: MIT

"""Behaviour tests for Java LS settings wiring (oraios/serena#1976)."""

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from solidlsp.language_servers.eclipse_jdtls import EclipseJDTLS


def _make_ls(custom_settings: dict, jre_home: str) -> EclipseJDTLS:
    ls = object.__new__(EclipseJDTLS)
    ls._custom_settings = custom_settings
    # must be an existing absolute path: JDTLS initialize builds a file URI from it
    # (Windows CI: "relative path can't be expressed as a file URI")
    ls.repository_root_path = str(Path(jre_home) / "project")
    Path(ls.repository_root_path).mkdir(parents=True, exist_ok=True)
    ls.runtime_dependency_paths = SimpleNamespace(
        jre_home_path=jre_home,
        jdtls_launcher_jar_path=os.path.join(jre_home, "launcher.jar"),
        jdtls_readonly_config_path=os.path.join(jre_home, "config"),
        gradle_path=None,
    )
    ls._resolve_gradle_java_home = MagicMock(return_value=None)
    return ls


def _java_settings(params: dict) -> dict:
    return params["initializationOptions"]["settings"]["java"]


def test_defaults_and_overrides_flow_into_jdtls_settings():
    with tempfile.TemporaryDirectory() as jre:
        ls = _make_ls({}, jre)
        java = _java_settings(ls._create_base_initialize_params())
        assert java["import"]["maven"]["enabled"] is True
        assert java["import"]["gradle"]["enabled"] is True
        assert java["configuration"]["updateBuildConfiguration"] == "interactive"
        assert java["autobuild"]["enabled"] is True

        ls = _make_ls(
            {
                "maven_import_enabled": False,
                "gradle_import_enabled": False,
                "update_build_configuration": "automatic",
                "autobuild_enabled": False,
            },
            jre,
        )
        java = _java_settings(ls._create_base_initialize_params())
        assert java["import"]["maven"]["enabled"] is False
        assert java["import"]["gradle"]["enabled"] is False
        assert java["configuration"]["updateBuildConfiguration"] == "automatic"
        assert java["autobuild"]["enabled"] is False

        ls = _make_ls({"update_build_configuration": "bogus"}, jre)
        java = _java_settings(ls._create_base_initialize_params())
        assert java["configuration"]["updateBuildConfiguration"] == "interactive"


def test_workspace_hash_includes_new_import_settings():
    class CS:
        def __init__(self, settings):
            self.settings = settings

        def get(self, key, default=None):
            return self.settings.get(key, default)

    root = "/tmp/proj"
    jar = "/tmp/launcher.jar"
    h1 = EclipseJDTLS.DependencyProvider._compute_workspace_hash(root, jar, CS({}))
    h2 = EclipseJDTLS.DependencyProvider._compute_workspace_hash(root, jar, CS({"maven_import_enabled": False}))
    h3 = EclipseJDTLS.DependencyProvider._compute_workspace_hash(root, jar, CS({"autobuild_enabled": False}))
    h4 = EclipseJDTLS.DependencyProvider._compute_workspace_hash(root, jar, CS({"update_build_configuration": "automatic"}))
    assert len({h1, h2, h3, h4}) == 4
