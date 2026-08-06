import shutil
from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_utils import SymbolUtils

pytestmark = pytest.mark.skipif(shutil.which("java") is None, reason="Nextflow language server requires a Java runtime")


@pytest.mark.nextflow
class TestNextflowLanguageServer:
    @pytest.mark.parametrize("language_server", [LanguageServerId.NEXTFLOW], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.NEXTFLOW], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Language server starts and attaches to the test repository."""
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [LanguageServerId.NEXTFLOW], indirect=True)
    def test_document_symbols_workflows(self, language_server: SolidLanguageServer) -> None:
        """Workflows declared in a script are reported, with the ``workflow`` keyword stripped."""
        all_symbols, _ = language_server.request_document_symbols("main.nf").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        assert "SAY_HELLO" in names, f"SAY_HELLO not found in main.nf symbols. Found: {names}"
        # the implicit entry workflow has no name of its own; the language server calls it "<entry>"
        assert "<entry>" in names, f"entry workflow not found in main.nf symbols. Found: {names}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.NEXTFLOW], indirect=True)
    def test_document_symbols_processes_and_functions(self, language_server: SolidLanguageServer) -> None:
        """Processes and functions are reported without their declaration keyword."""
        process_symbols, _ = language_server.request_document_symbols("modules/greet/main.nf").get_all_symbols_and_roots()
        process_names = [s["name"] for s in process_symbols]
        assert "GREET" in process_names, f"GREET not found in modules/greet/main.nf symbols. Found: {process_names}"
        assert "SHOUT" in process_names, f"SHOUT not found in modules/greet/main.nf symbols. Found: {process_names}"

        function_symbols, _ = language_server.request_document_symbols("modules/util/main.nf").get_all_symbols_and_roots()
        function_names = [s["name"] for s in function_symbols]
        assert "normalizeName" in function_names, f"normalizeName not found in modules/util/main.nf symbols. Found: {function_names}"
        assert "buildGreeting" in function_names, f"buildGreeting not found in modules/util/main.nf symbols. Found: {function_names}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.NEXTFLOW], indirect=True)
    def test_full_symbol_tree(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        for name in ("SAY_HELLO", "GREET", "SHOUT", "normalizeName", "buildGreeting"):
            assert SymbolUtils.symbol_tree_contains_name(symbols, name), f"{name} not found in symbol tree"

    @pytest.mark.parametrize("language_server", [LanguageServerId.NEXTFLOW], indirect=True)
    def test_find_references_within_file(self, language_server: SolidLanguageServer) -> None:
        """``normalizeName`` is defined and called within modules/util/main.nf only."""
        util_path = "modules/util/main.nf"
        symbol = self._get_symbol(language_server, util_path, "normalizeName")
        start = symbol["selectionRange"]["start"]

        refs = language_server.request_references(util_path, start["line"], start["character"])
        ref_lines = {(ref["relativePath"], ref["range"]["start"]["line"]) for ref in refs}
        # modules/util/main.nf, 0-indexed line 5: return "Hello, " + normalizeName(name)
        assert (util_path, 5) in ref_lines, f"call to normalizeName inside buildGreeting not found. Found: {ref_lines}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.NEXTFLOW], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer) -> None:
        """The GREET process is defined in a module and used by the workflow in main.nf."""
        module_path = "modules/greet/main.nf"
        symbol = self._get_symbol(language_server, module_path, "GREET")
        start = symbol["selectionRange"]["start"]

        refs = language_server.request_references(module_path, start["line"], start["character"])
        ref_lines = {(ref["relativePath"], ref["range"]["start"]["line"]) for ref in refs}
        # main.nf, 0-indexed line 2: include { GREET; SHOUT } from './modules/greet/main.nf'
        assert ("main.nf", 2) in ref_lines, f"include of GREET in main.nf not found. Found: {ref_lines}"
        # main.nf, 0-indexed line 12: greetings = GREET(names)
        assert ("main.nf", 12) in ref_lines, f"invocation of GREET in main.nf not found. Found: {ref_lines}"

    @staticmethod
    def _get_symbol(language_server: SolidLanguageServer, relative_path: str, name: str) -> dict:
        all_symbols, _ = language_server.request_document_symbols(relative_path).get_all_symbols_and_roots()
        matches = [s for s in all_symbols if s["name"] == name]
        assert matches, f"{name} not found in {relative_path}. Found: {[s['name'] for s in all_symbols]}"
        return matches[0]
