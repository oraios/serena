import os
from pathlib import Path

import pytest

from serena.constants import SERENA_MANAGED_DIR_NAME
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_utils import SymbolUtils
from solidlsp.settings import SolidLSPSettings
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols
from test.solidlsp.util.diagnostics import assert_file_diagnostics


@pytest.mark.groovy
class TestGroovyLanguageServer:
    language_server: SolidLanguageServer | None = None
    test_repo_path: Path = Path(__file__).parent.parent.parent / "resources" / "repos" / "groovy" / "test_repo"

    @classmethod
    def setup_class(cls):
        """
        Set up test class with Groovy test repository.
        """
        if not cls.test_repo_path.exists():
            pytest.skip("Groovy test repository not found")

        # Use JAR path from environment variable
        ls_jar_path = os.environ.get("GROOVY_LS_JAR_PATH")
        if not ls_jar_path or not os.path.exists(ls_jar_path):
            pytest.skip(
                "Groovy Language Server JAR not found. Set GROOVY_LS_JAR_PATH environment variable to run tests.",
                allow_module_level=True,
            )

        # Get JAR options from environment variable
        ls_jar_options = os.environ.get("GROOVY_LS_JAR_OPTIONS", "")
        ls_java_home_path = os.environ.get("GROOVY_LS_JAVA_HOME_PATH")

        groovy_settings = {"ls_jar_path": ls_jar_path, "ls_jar_options": ls_jar_options}
        if ls_java_home_path:
            groovy_settings["ls_java_home_path"] = ls_java_home_path

        # Create language server directly with Groovy-specific settings
        repo_path = str(cls.test_repo_path)
        config = LanguageServerConfig(code_language=Language.GROOVY, ignored_paths=[], trace_lsp_communication=False)

        project_data_path = os.path.join(repo_path, SERENA_MANAGED_DIR_NAME)
        solidlsp_settings = SolidLSPSettings(
            solidlsp_dir=str(Path.home() / ".serena"),
            project_data_path=project_data_path,
            ls_specific_settings={Language.GROOVY: groovy_settings},
        )

        cls.language_server = SolidLanguageServer.create(config, repo_path, solidlsp_settings=solidlsp_settings)
        cls.language_server.start()

    @classmethod
    def teardown_class(cls):
        """
        Clean up language server.
        """
        if cls.language_server is not None:
            cls.language_server.stop()

    def test_find_symbol(self) -> None:
        assert self.language_server is not None
        symbols = self.language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Main"), "Main class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Utils"), "Utils class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Model"), "Model class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "ModelUser"), "ModelUser class not found in symbol tree"

    def test_find_referencing_class_symbols(self) -> None:
        assert self.language_server is not None
        file_path = os.path.join("src", "main", "groovy", "com", "example", "Utils.groovy")
        refs = self.language_server.request_references(file_path, 3, 6)
        assert any("Main.groovy" in ref.get("relativePath", "") for ref in refs), "Utils should be referenced from Main.groovy"

        file_path = os.path.join("src", "main", "groovy", "com", "example", "Model.groovy")
        symbols = self.language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        model_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "com.example.Model" and sym.get("kind") == 5:
                model_symbol = sym
                break
        assert model_symbol is not None, "Could not find 'Model' class symbol in Model.groovy"

        if "selectionRange" in model_symbol:
            sel_start = model_symbol["selectionRange"]["start"]
        else:
            sel_start = model_symbol["range"]["start"]
        refs = self.language_server.request_references(file_path, sel_start["line"], sel_start["character"])

        main_refs = [ref for ref in refs if "Main.groovy" in ref.get("relativePath", "")]
        assert len(main_refs) >= 2, f"Model should be referenced from Main.groovy at least 2 times, found {len(main_refs)}"

        model_user_refs = [ref for ref in refs if "ModelUser.groovy" in ref.get("relativePath", "")]
        assert len(model_user_refs) >= 1, f"Model should be referenced from ModelUser.groovy at least 1 time, found {len(model_user_refs)}"

    def test_overview_methods(self) -> None:
        assert self.language_server is not None
        symbols = self.language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Main"), "Main missing from overview"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Utils"), "Utils missing from overview"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Model"), "Model missing from overview"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "ModelUser"), "ModelUser missing from overview"

    def test_bare_symbol_names(self) -> None:
        assert self.language_server is not None
        all_symbols = request_all_symbols(self.language_server)
        malformed_symbols = []
        for s in all_symbols:
            if has_malformed_name(s):
                malformed_symbols.append(s)
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )

    def test_file_diagnostics(self) -> None:
        assert self.language_server is not None
        assert_file_diagnostics(
            self.language_server,
            "src/main/groovy/com/example/DiagnosticsSample.groovy",
            (),
            min_count=1,
        )
