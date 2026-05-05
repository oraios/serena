import os
import shutil
from unittest import mock

import pytest

from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.settings import SolidLSPSettings

REPO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "resources", "repos", "bsl", "test_repo"))

_java_available = shutil.which("java") is not None
_skip_no_java = pytest.mark.skipif(
    not _java_available,
    reason="BSL LSP integration tests require Java 11+",
)


@pytest.fixture(scope="module")
def bsl_ls():
    config = LanguageServerConfig(code_language=Language.BSL)
    settings = SolidLSPSettings()
    ls_class = Language.BSL.get_ls_class()
    server = ls_class(config, REPO_PATH, settings)
    server.start()
    yield server
    server.stop()


@pytest.mark.bsl
@pytest.mark.slow
@_skip_no_java
def test_bsl_server_starts(bsl_ls):
    assert bsl_ls.server_ready.is_set()


@pytest.mark.bsl
@pytest.mark.slow
@_skip_no_java
def test_bsl_document_symbols(bsl_ls):
    symbols = bsl_ls.request_document_symbols("CommonModule.bsl")
    names = [s.get("name") for s in symbols.iter_symbols()]
    assert "ВывестиСообщение" in names
    assert "ПолучитьПриветствие" in names
    assert "ВызватьПриветствие" in names


@pytest.mark.bsl
@pytest.mark.slow
@_skip_no_java
def test_bsl_find_references(bsl_ls):
    refs = bsl_ls.request_references("CommonModule.bsl", line=6, column=10)
    assert len(refs) >= 1


def test_bsl_filename_matcher():
    matcher = Language.BSL.get_source_fn_matcher()
    assert matcher.is_relevant_filename("module.bsl")
    assert matcher.is_relevant_filename("script.os")
    assert not matcher.is_relevant_filename("module.py")


def test_bsl_enum_registration():
    assert Language.BSL.value == "bsl"
    assert Language.BSL.get_ls_class().__name__ == "BSLLanguageServer"


def test_bsl_dependency_provider_default_version():
    """DependencyProvider uses default version and includes SHA in deps."""
    from solidlsp.language_servers.bsl_language_server import (
        DEFAULT_BSL_LS_VERSION,
        BSLLanguageServer,
    )

    settings = SolidLSPSettings()
    custom_settings = settings.get_custom_ls_settings("bsl")
    provider = BSLLanguageServer.DependencyProvider(custom_settings, "/tmp/ls_resources")

    expected_version = DEFAULT_BSL_LS_VERSION
    expected_jar_dir = os.path.join("/tmp/ls_resources", f"bsl-ls-{expected_version}")
    expected_jar_path = os.path.join(expected_jar_dir, f"bsl-language-server-{expected_version}-exec.jar")

    with (
        mock.patch("shutil.which", return_value="/usr/bin/java"),
        mock.patch("os.path.exists", return_value=True),
    ):
        jar_path = provider._get_or_install_core_dependency()

    assert jar_path == expected_jar_path


def test_bsl_dependency_provider_custom_version_no_sha():
    """When user overrides version, no SHA verification should happen (expected_sha256 is None)."""
    from solidlsp.language_servers.bsl_language_server import BSLLanguageServer
    from solidlsp.language_servers.common import RuntimeDependencyCollection

    settings = SolidLSPSettings()
    custom_settings = settings.get_custom_ls_settings("bsl")
    custom_settings["bsl_ls_version"] = "0.28.0"
    provider = BSLLanguageServer.DependencyProvider(custom_settings, "/tmp/ls_resources")

    custom_version = "0.28.0"
    expected_jar_dir = os.path.join("/tmp/ls_resources", f"bsl-ls-{custom_version}")
    expected_jar_path = os.path.join(expected_jar_dir, f"bsl-language-server-{custom_version}-exec.jar")

    installed_deps = []

    def fake_install(self_inner, install_dir):
        installed_deps.extend(self_inner._dependencies)
        os.makedirs(install_dir, exist_ok=True)
        open(expected_jar_path, "w").close()

    with (
        mock.patch("shutil.which", return_value="/usr/bin/java"),
        mock.patch.object(RuntimeDependencyCollection, "install", fake_install),
    ):
        jar_path = provider._get_or_install_core_dependency()

    assert jar_path == expected_jar_path
    assert len(installed_deps) == 1
    assert installed_deps[0].sha256 is None, "SHA256 must be None for user-overridden version"

    if os.path.exists(expected_jar_path):
        os.remove(expected_jar_path)
    if os.path.exists(expected_jar_dir):
        os.rmdir(expected_jar_dir)


def test_bsl_dependency_provider_custom_ls_path():
    """When ls_path is set, the custom path is returned directly without download."""
    from solidlsp.language_servers.bsl_language_server import BSLLanguageServer

    settings = SolidLSPSettings()
    custom_settings = settings.get_custom_ls_settings("bsl")
    custom_settings["ls_path"] = "/custom/path/bsl-language-server.jar"
    provider = BSLLanguageServer.DependencyProvider(custom_settings, "/tmp/ls_resources")

    with (
        mock.patch("shutil.which", return_value="/usr/bin/java"),
        mock.patch("os.path.exists", return_value=True),
    ):
        jar_path = provider._get_or_install_core_dependency()

    assert jar_path == "/custom/path/bsl-language-server.jar"
