import shutil
from pathlib import Path

import pytest

from serena.code_editor import LanguageServerCodeEditor
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from src.serena.symbol import LanguageServerSymbolRetriever
from test.conftest import project_with_ls_context, start_ls_context


def _extract_changes(workspace_edit: dict) -> dict[str, list[dict]]:
    changes = workspace_edit.get("changes", {})
    if changes:
        return changes

    document_changes = workspace_edit.get("documentChanges", [])
    return {change["textDocument"]["uri"]: change["edits"] for change in document_changes if "textDocument" in change and "edits" in change}


def _copy_php_fixture(tmp_path: Path) -> Path:
    from test.conftest import get_repo_path

    fixture_path = get_repo_path(Language.PHP)
    target_path = tmp_path / "test_repo"
    shutil.copytree(fixture_path, target_path)
    return target_path


def _write_psr4_fixture(repo_path: Path) -> None:
    serena_dir = repo_path / ".serena"
    serena_dir.mkdir(exist_ok=True)
    (serena_dir / "project.yml").write_text(
        """project_name: php-phase1
languages:
  - php_phpantom
""",
        encoding="utf-8",
    )

    (repo_path / "composer.json").write_text('{"autoload": {"psr-4": {"Demo\\\\": "src/"}}}\n', encoding="utf-8")

    src_dir = repo_path / "src"
    src_dir.mkdir(exist_ok=True)

    (src_dir / "Greeter.php").write_text(
        """<?php
namespace Demo;

interface Greeter
{
    /** Returns a greeting for the given name. */
    public function greet(string $name): string;
}
""",
        encoding="utf-8",
    )

    (src_dir / "Helper.php").write_text(
        """<?php
namespace Demo;

/** Utility helper docs. */
function format_name(string $name): string
{
    return strtoupper($name);
}
""",
        encoding="utf-8",
    )

    (src_dir / "Welcome.php").write_text(
        """<?php
namespace Demo;

use const Demo\\MAX_GREETING_LENGTH;
use function Demo\\format_name;

const MAX_GREETING_LENGTH = 80;

/** Welcome service docs. */
class Welcome implements Greeter
{
    /** Friendly greeting docs. */
    public function greet(string $name): string
    {
        return substr("Hello ".format_name($name), 0, MAX_GREETING_LENGTH);
    }
}
""",
        encoding="utf-8",
    )

    (src_dir / "UseWelcome.php").write_text(
        """<?php
namespace Demo;

function run_demo(): string
{
    $service = new Welcome();
    return $service->greet('world');
}
""",
        encoding="utf-8",
    )


def _find_root_symbol(language_server: SolidLanguageServer, relative_path: str, symbol_name: str) -> dict:
    all_symbols, root_symbols = language_server.request_document_symbols(relative_path).get_all_symbols_and_roots()
    for symbol in root_symbols:
        if symbol.get("name") == symbol_name:
            return symbol
    for symbol in all_symbols:
        if symbol.get("name") == symbol_name:
            return symbol
    raise AssertionError(f"Symbol {symbol_name!r} not found in {relative_path}")


def _find_child_symbol(parent_symbol: dict, child_name: str) -> dict:
    for child in parent_symbol.get("children", []):
        if child.get("name") == child_name:
            return child
    raise AssertionError(f"Child symbol {child_name!r} not found in {parent_symbol.get('name')!r}")


@pytest.mark.php
class TestPHPantom:
    @pytest.mark.parametrize("language_server", [Language.PHP_PHPANTOM], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.PHP], indirect=True)
    def test_rename_local_variable(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        workspace_edit = language_server.request_rename_symbol_edit(str(Path("index.php")), 9, 1, "welcomeMessage")
        assert workspace_edit is not None, "Rename should be supported for local PHP variables"

        changes = _extract_changes(workspace_edit)
        index_edits = [edits for uri, edits in changes.items() if uri.endswith("index.php")]
        assert index_edits, f"Expected edits for index.php, got: {list(changes.keys())}"

        edits = index_edits[0]
        assert len(edits) >= 2, f"Expected at least two local variable edits, got {len(edits)}"
        assert {edit["range"]["start"]["line"] for edit in edits} >= {9, 11}
        assert all(edit["newText"] == "$welcomeMessage" for edit in edits)

    def test_rename_method_across_files(self, tmp_path: Path) -> None:
        repo_path = _copy_php_fixture(tmp_path)
        _write_psr4_fixture(repo_path)

        with start_ls_context(Language.PHP_PHPANTOM, repo_path=str(repo_path), solidlsp_dir=tmp_path) as language_server:
            welcome_symbol = _find_root_symbol(language_server, "src/Welcome.php", "Welcome")
            greet_symbol = _find_child_symbol(welcome_symbol, "greet")
            selection = greet_symbol["selectionRange"]["start"]
            workspace_edit = language_server.request_rename_symbol_edit(
                "src/Welcome.php", selection["line"], selection["character"], "salute"
            )

        assert workspace_edit is not None, "Rename should be supported for methods"
        changes = _extract_changes(workspace_edit)
        changed_files = sorted(uri.split("/")[-1] for uri in changes)
        assert "Welcome.php" in changed_files
        assert "UseWelcome.php" in changed_files
        assert all(edit["newText"] == "salute" for edits in changes.values() for edit in edits)

    def test_rename_class_across_files(self, tmp_path: Path) -> None:
        repo_path = _copy_php_fixture(tmp_path)
        _write_psr4_fixture(repo_path)

        with start_ls_context(Language.PHP_PHPANTOM, repo_path=str(repo_path), solidlsp_dir=tmp_path) as language_server:
            welcome_symbol = _find_root_symbol(language_server, "src/Welcome.php", "Welcome")
            selection = welcome_symbol["selectionRange"]["start"]
            workspace_edit = language_server.request_rename_symbol_edit(
                "src/Welcome.php", selection["line"], selection["character"], "GreetingService"
            )

        assert workspace_edit is not None, "Rename should be supported for classes"
        changes = _extract_changes(workspace_edit)
        changed_files = sorted(uri.split("/")[-1] for uri in changes)
        assert "GreetingService.php" in changed_files or "Welcome.php" in changed_files
        assert "UseWelcome.php" in changed_files
        assert all(edit["newText"] == "GreetingService" for edits in changes.values() for edit in edits)

    def test_psr4_class_rename_applies_file_rename(self, tmp_path: Path) -> None:
        repo_path = _copy_php_fixture(tmp_path)
        _write_psr4_fixture(repo_path)

        with project_with_ls_context(Language.PHP_PHPANTOM, str(repo_path)) as project:
            symbol_retriever = LanguageServerSymbolRetriever(project)
            code_editor = LanguageServerCodeEditor(symbol_retriever)
            status_message = code_editor.rename_symbol("Welcome", relative_path="src/Welcome.php", new_name="GreetingService")

        assert "Successfully renamed 'Welcome' to 'GreetingService'" in status_message
        assert not (repo_path / "src" / "Welcome.php").exists()
        assert (repo_path / "src" / "GreetingService.php").exists()

        renamed_content = (repo_path / "src" / "GreetingService.php").read_text(encoding="utf-8")
        usage_content = (repo_path / "src" / "UseWelcome.php").read_text(encoding="utf-8")
        assert "class GreetingService" in renamed_content
        assert "new GreetingService()" in usage_content

    def test_hover_info_is_available_via_find_symbol_include_info(self, tmp_path: Path) -> None:
        repo_path = _copy_php_fixture(tmp_path)
        _write_psr4_fixture(repo_path)

        with project_with_ls_context(Language.PHP_PHPANTOM, str(repo_path)) as project:
            symbol_retriever = LanguageServerSymbolRetriever(project)
            symbols = symbol_retriever.find("Welcome", within_relative_path="src/Welcome.php")
            info_by_symbol = symbol_retriever.request_info_for_symbol_batch(symbols)

        welcome_infos = [info for symbol, info in info_by_symbol.items() if symbol.name == "Welcome"]
        assert welcome_infos, "Expected Welcome symbol info to be available"
        assert any(info and "Welcome service docs." in info for info in welcome_infos)

    def test_workspace_symbol_queries_cover_class_function_and_constant(self, tmp_path: Path) -> None:
        repo_path = _copy_php_fixture(tmp_path)
        _write_psr4_fixture(repo_path)

        with start_ls_context(Language.PHP_PHPANTOM, repo_path=str(repo_path), solidlsp_dir=tmp_path) as language_server:
            class_symbols = language_server.request_workspace_symbol("Welcome") or []
            function_symbols = language_server.request_workspace_symbol("format_name") or []
            constant_symbols = language_server.request_workspace_symbol("MAX_GREETING_LENGTH") or []

        def summarize(symbols: list[dict]) -> list[tuple[str, str]]:
            return [(symbol["name"], symbol["location"]["uri"]) for symbol in symbols]

        assert any(name == "Demo\\Welcome" and uri.endswith("src/Welcome.php") for name, uri in summarize(class_symbols))
        assert all(uri.endswith(".php") for _name, uri in summarize(function_symbols))
        assert function_symbols == [] or any(
            "location" in symbol and symbol["location"]["uri"].startswith("file://") for symbol in function_symbols
        )
        assert constant_symbols == [] or any(
            "location" in symbol and symbol["location"]["uri"].startswith("file://") for symbol in constant_symbols
        )
