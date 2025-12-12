import logging
import os
from pathlib import Path

import pytest

from serena.constants import SERENA_MANAGED_DIR_IN_HOME, SERENA_MANAGED_DIR_NAME
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import SymbolUtils
from solidlsp.settings import SolidLSPSettings


@pytest.mark.groovy
class TestGroovyLanguageServer:
    @classmethod
    def setup_class(cls):
        """
        Set up the test class with the Groovy test repository.
        """
        cls.test_repo_path = Path(__file__).parent.parent.parent / "resources" / "repos" / "groovy" / "test_repo"

        if not cls.test_repo_path.exists():
            pytest.skip("Groovy test repository not found")

        # Use JAR path from environment variable
        ls_jar_path = os.environ.get("GROOVY_LS_JAR_PATH")
        if not ls_jar_path or not os.path.exists(ls_jar_path):
            pytest.skip(
                "Groovy Language Server JAR not found. Set GROOVY_LS_JAR_PATH environment variable to run tests.",
                allow_module_level=True,
            )

        groovy_settings = {
            "ls_jar_path": ls_jar_path,
        }

        # Create language server directly with Groovy-specific settings
        repo_path = str(cls.test_repo_path)
        config = LanguageServerConfig(code_language=Language.GROOVY, ignored_paths=[], trace_lsp_communication=False)
        logger = LanguageServerLogger(log_level=logging.ERROR)

        solidlsp_settings = SolidLSPSettings(
            solidlsp_dir=SERENA_MANAGED_DIR_IN_HOME,
            project_data_relative_path=SERENA_MANAGED_DIR_NAME,
            ls_specific_settings={Language.GROOVY: groovy_settings},
        )

        cls.language_server = SolidLanguageServer.create(config, logger, repo_path, solidlsp_settings=solidlsp_settings)
        cls.language_server.start()

    @classmethod
    def teardown_class(cls):
        """
        Clean up the language server.
        """
        if hasattr(cls, "language_server"):
            cls.language_server.stop()

    def test_find_symbol(self) -> None:
        symbols = self.language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Main"), "Main class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Utils"), "Utils class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Model"), "Model class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "ModelUser"), "ModelUser class not found in symbol tree"

    def test_find_referencing_class_symbols(self) -> None:
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
        symbols = self.language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Main"), "Main missing from overview"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Utils"), "Utils missing from overview"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Model"), "Model missing from overview"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "ModelUser"), "ModelUser missing from overview"
