import os
from pathlib import Path
from unittest import mock

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from solidlsp.settings import SolidLSPSettings
from test.conftest import language_tests_enabled
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols


@pytest.mark.bsl
class TestBSLLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.BSL], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "ВывестиСообщение"), \
            "ВывестиСообщение not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "ПолучитьПриветствие"), \
            "ПолучитьПриветствие not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Инициализировать"), \
            "Инициализировать not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.BSL], indirect=True)
    def test_document_symbols(self, language_server: SolidLanguageServer) -> None:
        doc_symbols = language_server.request_document_symbols("CommonModule.bsl")
        all_symbols, _ = doc_symbols.get_all_symbols_and_roots()
        names = [s.get("name") for s in all_symbols if s.get("name")]
        assert "ВывестиСообщение" in names, \
            f"ВывестиСообщение not found in CommonModule.bsl symbols. Found: {names}"
        assert "ПолучитьПриветствие" in names, \
            f"ПолучитьПриветствие not found in CommonModule.bsl symbols. Found: {names}"
        assert "ВызватьПриветствие" in names, \
            f"ВызватьПриветствие not found in CommonModule.bsl symbols. Found: {names}"

    @pytest.mark.parametrize("language_server", [Language.BSL], indirect=True)
    def test_find_references_within_file(self, language_server: SolidLanguageServer) -> None:
        # CommonModule.bsl (0-indexed):
        # line 2: Процедура ВывестиСообщение(Текст) Экспорт
        # line 13: ВывестиСообщение(Сообщение);  <- internal call
        refs = language_server.request_references("CommonModule.bsl", line=2, column=10)
        assert refs, "Expected at least one reference to ВывестиСообщение"
        file_names = [ref.get("relativePath", "") for ref in refs]
        assert any("CommonModule.bsl" in f for f in file_names), \
            f"Expected self-reference in CommonModule.bsl, got: {file_names}"

    @pytest.mark.parametrize("language_server", [Language.BSL], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer) -> None:
        # ВывестиСообщение is defined in CommonModule.bsl (line 2)
        # and called from ObjectModule.bsl (line 6)
        refs = language_server.request_references("CommonModule.bsl", line=2, column=10)
        assert refs, "Expected references to ВывестиСообщение"
        file_names = [ref.get("relativePath", "") for ref in refs]
        assert any("ObjectModule.bsl" in f for f in file_names), \
            f"Expected cross-file reference in ObjectModule.bsl, got: {file_names}"

    @pytest.mark.parametrize("language_server", [Language.BSL], indirect=True)
    def test_bare_symbol_names(self, language_server: SolidLanguageServer) -> None:
        all_symbols = request_all_symbols(language_server)
        malformed = [s for s in all_symbols if has_malformed_name(s)]
        if malformed:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(s) for s in malformed]}",
                pytrace=False,
            )


# ---------------------------------------------------------------------------
# Unit tests — no language server needed, always run regardless of Java
# ---------------------------------------------------------------------------

def test_bsl_filename_matcher() -> None:
    matcher = Language.BSL.get_source_fn_matcher()
    assert matcher.is_relevant_filename("module.bsl")
    assert matcher.is_relevant_filename("script.os")
    assert not matcher.is_relevant_filename("module.py")


def test_bsl_enum_registration() -> None:
    assert Language.BSL.value == "bsl"
    assert Language.BSL.get_ls_class().__name__ == "BSLLanguageServer"


def test_bsl_dependency_provider_default_version() -> None:
    """DependencyProvider uses default version and includes SHA in deps."""
    from solidlsp.language_servers.bsl_language_server import (
        DEFAULT_BSL_LS_VERSION,
        BSLLanguageServer,
    )

    settings = SolidLSPSettings()
    provider = BSLLanguageServer.DependencyProvider(
        settings.get_ls_specific_settings(Language.BSL),
        "/tmp/ls_resources",
    )

    expected_version = DEFAULT_BSL_LS_VERSION
    expected_jar_dir = os.path.join("/tmp/ls_resources", f"bsl-ls-{expected_version}")
    expected_jar_path = os.path.join(expected_jar_dir, f"bsl-language-server-{expected_version}-exec.jar")

    with (
        mock.patch("shutil.which", return_value="/usr/bin/java"),
        mock.patch("os.path.exists", return_value=True),
    ):
        jar_path = provider._get_or_install_core_dependency()

    assert jar_path == expected_jar_path


def test_bsl_dependency_provider_custom_version_no_sha() -> None:
    """When user overrides version, no SHA verification should happen."""
    from solidlsp.language_servers.bsl_language_server import BSLLanguageServer
    from solidlsp.language_servers.common import RuntimeDependencyCollection

    settings = SolidLSPSettings()
    settings.ls_specific_settings[Language.BSL] = {"bsl_ls_version": "0.28.0"}
    provider = BSLLanguageServer.DependencyProvider(
        settings.get_ls_specific_settings(Language.BSL),
        "/tmp/ls_resources",
    )

    custom_version = "0.28.0"
    expected_jar_dir = os.path.join("/tmp/ls_resources", f"bsl-ls-{custom_version}")
    expected_jar_path = os.path.join(expected_jar_dir, f"bsl-language-server-{custom_version}-exec.jar")

    installed_deps = []

    def fake_install(self_inner, install_dir):
        installed_deps.extend(self_inner.get_dependencies_for_current_platform())
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


def test_bsl_dependency_provider_custom_ls_path() -> None:
    """When ls_path is set, the custom path is returned directly without download."""
    from solidlsp.language_servers.bsl_language_server import BSLLanguageServer

    settings = SolidLSPSettings()
    settings.ls_specific_settings[Language.BSL] = {"ls_path": "/custom/path/bsl-language-server.jar"}
    provider = BSLLanguageServer.DependencyProvider(
        settings.get_ls_specific_settings(Language.BSL),
        "/tmp/ls_resources",
    )

    with (
        mock.patch("shutil.which", return_value="/usr/bin/java"),
        mock.patch("os.path.exists", return_value=True),
    ):
        jar_path = provider._get_or_install_core_dependency()

    assert jar_path == "/custom/path/bsl-language-server.jar"
