import json
import logging
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

import pytest

from serena.agent import SerenaAgent
from serena.config.serena_config import ProjectConfig, RegisteredProject, SerenaConfig
from serena.project import Project
from serena.tools import (
    SUCCESS_RESULT,
    ActivateProjectTool,
    FindReferencingSymbolsTool,
    FindSymbolTool,
    InitialInstructionsTool,
    ReplaceContentTool,
    ReplaceSymbolBodyTool,
    SafeDeleteSymbol,
    Tool,
)
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind
from test.conftest import get_repo_path, is_ci, language_tests_enabled
from test.solidlsp import clojure as clj


@pytest.fixture
def serena_config():
    config = SerenaConfig(gui_log_window=False, web_dashboard=False, log_level=logging.ERROR)

    # Create test projects for all supported languages
    test_projects = []
    for language in [
        Language.PYTHON,
        Language.GO,
        Language.JAVA,
        Language.KOTLIN,
        Language.RUST,
        Language.TYPESCRIPT,
        Language.PHP,
        Language.CSHARP,
        Language.CLOJURE,
        Language.FSHARP,
        Language.POWERSHELL,
        Language.CPP_CCLS,
        Language.HAXE,
        Language.LEAN4,
        Language.MSL,
    ]:
        repo_path = get_repo_path(language)
        if repo_path.exists():
            project_name = f"test_repo_{language}"
            project = Project(
                project_root=str(repo_path),
                project_config=ProjectConfig(
                    project_name=project_name,
                    languages=[language],
                    ignored_paths=[],
                    excluded_tools=[],
                    read_only=False,
                    ignore_all_files_in_gitignore=True,
                    initial_prompt="",
                    encoding="utf-8",
                ),
                serena_config=config,
            )
            test_projects.append(RegisteredProject.from_project_instance(project))

    config.projects = test_projects
    return config


def read_project_file(project: Project, relative_path: str) -> str:
    """Utility function to read a file from the project."""
    file_path = os.path.join(project.project_root, relative_path)
    with open(file_path, encoding=project.project_config.encoding) as f:
        return f.read()


@contextmanager
def project_file_modification_context(serena_agent: SerenaAgent, relative_path: str) -> Iterator[None]:
    """Context manager to modify a project file and revert the changes after use."""
    project = serena_agent.get_active_project()
    file_path = os.path.join(project.project_root, relative_path)

    # Read the original content
    original_content = read_project_file(project, relative_path)

    try:
        yield
    finally:
        # Revert to the original content
        with open(file_path, "w", encoding=project.project_config.encoding) as f:
            f.write(original_content)


@pytest.fixture
def serena_agent(request: pytest.FixtureRequest, serena_config) -> Iterator[SerenaAgent]:
    language = Language(request.param)
    if not language_tests_enabled(language):
        pytest.skip(f"Tests for language {language} are not enabled.")

    project_name = f"test_repo_{language}"

    agent = SerenaAgent(project=project_name, serena_config=serena_config)

    # wait for agent to be ready
    agent.execute_task(lambda: None)

    yield agent

    # explicitly shut down to free resources
    agent.on_shutdown(timeout=5)


class TestSerenaAgent:
    @pytest.mark.parametrize("project", [None, str(get_repo_path(Language.PYTHON)), "non_existent_path"])
    def test_agent_instantiation(self, project: str | None):
        """
        Tests agent instantiation for cases where
          * no project is specified at startup
          * a valid project path is specified at startup
          * an invalid project path is specified at startup
        All cases must not raise an exception.
        """
        serena_config = SerenaConfig(gui_log_window=False, web_dashboard=False)
        SerenaAgent(project=project, serena_config=serena_config)

    def _assert_find_symbol(self, serena_agent: SerenaAgent, symbol_name: str, expected_kind: str, expected_file: str) -> None:
        agent = serena_agent
        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply(name_path_pattern=symbol_name, include_info=True)

        symbols = json.loads(result)
        assert any(
            symbol_name in s["name_path"] and expected_kind.lower() in s["kind"].lower() and expected_file in s["relative_path"]
            for s in symbols
        ), f"Expected to find {symbol_name} ({expected_kind}) in {expected_file}"
        # testing retrieval of symbol info
        if serena_agent.get_active_lsp_languages() == [Language.KOTLIN]:
            # kotlin LS doesn't seem to provide hover info right now, at least for the struct we test this on
            return
        for s in symbols:
            if s["kind"] in (SymbolKind.File.name, SymbolKind.Module.name):
                # we ignore file and module symbols for the info test
                continue
            symbol_info = s.get("info")
            assert symbol_info, f"Expected symbol info to be present for symbol: {s}"
            assert symbol_name in s["info"], (
                f"[{serena_agent.get_active_lsp_languages()[0]}] Expected symbol info to contain symbol name {symbol_name}. Info: {s['info']}"
            )
            # special additional test for Java, since Eclipse returns hover in a complex format and we want to make sure to get it right
            if s["kind"] == SymbolKind.Class.name and serena_agent.get_active_lsp_languages() == [Language.JAVA]:
                assert "A simple model class" in symbol_info, f"Java class docstring not found in symbol info: {s}"

    @pytest.mark.php
    @pytest.mark.parametrize("serena_agent", [Language.PHP], indirect=True)
    def test_find_symbol_within_php_file(self, serena_agent: SerenaAgent) -> None:
        """Verify find_symbol with a PHP file path routes to the PHP language server.

        This validates the fix in symbol.py (LanguageServerSymbolRetriever.find_symbols):
        when within_relative_path points to a PHP file, the retriever must use
        get_language_server() rather than iterating all language servers. Without this
        fix, non-PHP servers reject the PHP file and no symbols are returned.
        """
        find_symbol_tool = serena_agent.get_tool(FindSymbolTool)
        sample_php = "sample.php"

        result = find_symbol_tool.apply(name_path_pattern="Dog/greet", relative_path=sample_php)
        symbols = json.loads(result)

        assert len(symbols) > 0, (
            f"Expected to find Dog/greet in {sample_php} but got empty result. "
            "This may indicate that find_symbol is not routing to the PHP language server for PHP files."
        )
        assert any("greet" in s["name_path"] and sample_php in s["relative_path"] for s in symbols), (
            f"Dog/greet not found in {sample_php}. Symbols: {symbols}"
        )

    @pytest.mark.parametrize(
        "serena_agent,symbol_name,expected_kind,expected_file",
        [
            pytest.param(Language.PYTHON, "User", "Class", "models.py", marks=pytest.mark.python),
            pytest.param(Language.GO, "Helper", "Function", "main.go", marks=pytest.mark.go),
            pytest.param(Language.JAVA, "Model", "Class", "Model.java", marks=pytest.mark.java),
            pytest.param(
                Language.KOTLIN,
                "Model",
                "Struct",
                "Model.kt",
                marks=[pytest.mark.kotlin] + ([pytest.mark.skip(reason="Kotlin LSP JVM crashes on restart in CI")] if is_ci else []),
            ),
            pytest.param(Language.TYPESCRIPT, "DemoClass", "Class", "index.ts", marks=pytest.mark.typescript),
            pytest.param(Language.PHP, "helperFunction", "Function", "helper.php", marks=pytest.mark.php),
            pytest.param(Language.CLOJURE, "greet", "Function", clj.CORE_PATH, marks=pytest.mark.clojure),
            pytest.param(Language.CSHARP, "Calculator", "Class", "Program.cs", marks=pytest.mark.csharp),
            pytest.param(Language.POWERSHELL, "Greet-User", "Function", "main.ps1", marks=pytest.mark.powershell),
            pytest.param(Language.CPP_CCLS, "add", "Function", "b.cpp", marks=pytest.mark.cpp),
            pytest.param(Language.HAXE, "Main", "Class", "Main.hx", marks=pytest.mark.haxe),
            pytest.param(Language.LEAN4, "add", "Method", "Helper.lean", marks=pytest.mark.lean4),
            pytest.param(Language.MSL, "greet", "Function", "main.mrc", marks=pytest.mark.msl),
        ],
        indirect=["serena_agent"],
    )
    def test_find_symbol_stable(self, serena_agent: SerenaAgent, symbol_name: str, expected_kind: str, expected_file: str) -> None:
        self._assert_find_symbol(serena_agent, symbol_name, expected_kind, expected_file)

    @pytest.mark.parametrize(
        "serena_agent,symbol_name,expected_kind,expected_file",
        [
            pytest.param(Language.FSHARP, "Calculator", "Module", "Calculator.fs", marks=pytest.mark.fsharp),
        ],
        indirect=["serena_agent"],
    )
    @pytest.mark.xfail(reason="F# language server is unreliable")  # See issue #1040
    def test_find_symbol_fsharp(self, serena_agent: SerenaAgent, symbol_name: str, expected_kind: str, expected_file: str) -> None:
        self._assert_find_symbol(serena_agent, symbol_name, expected_kind, expected_file)

    @pytest.mark.parametrize(
        "serena_agent,symbol_name,expected_kind,expected_file",
        [
            pytest.param(Language.RUST, "add", "Function", "lib.rs", marks=pytest.mark.rust),
        ],
        indirect=["serena_agent"],
    )
    @pytest.mark.xfail(reason="Rust language server is unreliable")  # See issue #1040
    def test_find_symbol_rust(self, serena_agent: SerenaAgent, symbol_name: str, expected_kind: str, expected_file: str) -> None:
        self._assert_find_symbol(serena_agent, symbol_name, expected_kind, expected_file)

    def _assert_find_symbol_references(self, serena_agent: SerenaAgent, symbol_name: str, def_file: str, ref_file: str) -> None:
        agent = serena_agent

        # Find the symbol location first
        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply(name_path_pattern=symbol_name, relative_path=def_file)

        time.sleep(1)
        symbols = json.loads(result)
        # Find the definition
        def_symbol = symbols[0]

        # Now find references
        find_refs_tool = agent.get_tool(FindReferencingSymbolsTool)
        result = find_refs_tool.apply(name_path=def_symbol["name_path"], relative_path=def_symbol["relative_path"])

        def contains_ref_with_relative_path(refs, relative_path):
            """
            Checks for reference to relative path, regardless of output format (grouped an ungrouped)
            """
            if isinstance(refs, list):
                for ref in refs:
                    if contains_ref_with_relative_path(ref, relative_path):
                        return True
            elif isinstance(refs, dict):
                if relative_path in refs:
                    return True
                for value in refs.values():
                    if contains_ref_with_relative_path(value, relative_path):
                        return True
            return False

        refs = json.loads(result)
        assert contains_ref_with_relative_path(refs, ref_file), f"Expected to find reference to {symbol_name} in {ref_file}. refs={refs}"

    @pytest.mark.parametrize(
        "serena_agent,symbol_name,def_file,ref_file",
        [
            pytest.param(
                Language.PYTHON,
                "User",
                os.path.join("test_repo", "models.py"),
                os.path.join("test_repo", "services.py"),
                marks=pytest.mark.python,
            ),
            pytest.param(Language.GO, "Helper", "main.go", "main.go", marks=pytest.mark.go),
            pytest.param(
                Language.JAVA,
                "Model",
                os.path.join("src", "main", "java", "test_repo", "Model.java"),
                os.path.join("src", "main", "java", "test_repo", "Main.java"),
                marks=pytest.mark.java,
            ),
            pytest.param(
                Language.KOTLIN,
                "Model",
                os.path.join("src", "main", "kotlin", "test_repo", "Model.kt"),
                os.path.join("src", "main", "kotlin", "test_repo", "Main.kt"),
                marks=[pytest.mark.kotlin] + ([pytest.mark.skip(reason="Kotlin LSP JVM crashes on restart in CI")] if is_ci else []),
            ),
            pytest.param(Language.RUST, "add", os.path.join("src", "lib.rs"), os.path.join("src", "main.rs"), marks=pytest.mark.rust),
            pytest.param(Language.PHP, "helperFunction", "helper.php", "index.php", marks=pytest.mark.php),
            pytest.param(
                Language.CLOJURE,
                "multiply",
                clj.CORE_PATH,
                clj.UTILS_PATH,
                marks=pytest.mark.clojure,
            ),
            pytest.param(Language.CSHARP, "Calculator", "Program.cs", "Program.cs", marks=pytest.mark.csharp),
            pytest.param(Language.POWERSHELL, "Greet-User", "main.ps1", "main.ps1", marks=pytest.mark.powershell),
            pytest.param(Language.CPP_CCLS, "add", "b.cpp", "a.cpp", marks=pytest.mark.cpp),
            pytest.param(
                Language.HAXE,
                "addNumbers",
                os.path.join("src", "utils", "Helper.hx"),
                os.path.join("src", "Main.hx"),
                marks=pytest.mark.haxe,
            ),
            pytest.param(Language.LEAN4, "add", "Helper.lean", "Main.lean", marks=pytest.mark.lean4),
            pytest.param(Language.MSL, "format.coins", "utils.mrc", "main.mrc", marks=pytest.mark.msl),
        ],
        indirect=["serena_agent"],
    )
    def test_find_symbol_references_stable(self, serena_agent: SerenaAgent, symbol_name: str, def_file: str, ref_file: str) -> None:
        self._assert_find_symbol_references(serena_agent, symbol_name, def_file, ref_file)

    @pytest.mark.parametrize(
        "serena_agent,symbol_name,def_file,ref_file",
        [
            pytest.param(Language.TYPESCRIPT, "helperFunction", "index.ts", "use_helper.ts", marks=pytest.mark.typescript),
        ],
        indirect=["serena_agent"],
    )
    @pytest.mark.xfail(False, reason="TypeScript language server is unreliable")  # NOTE: Testing; may be resolved by #1120; See issue #1040
    def test_find_symbol_references_typescript(self, serena_agent: SerenaAgent, symbol_name: str, def_file: str, ref_file: str) -> None:
        self._assert_find_symbol_references(serena_agent, symbol_name, def_file, ref_file)

    @pytest.mark.parametrize(
        "serena_agent,symbol_name,def_file,ref_file",
        [
            pytest.param(Language.FSHARP, "add", "Calculator.fs", "Program.fs", marks=pytest.mark.fsharp),
        ],
        indirect=["serena_agent"],
    )
    @pytest.mark.xfail(reason="F# language server is unreliable")  # See issue #1040
    def test_find_symbol_references_fsharp(self, serena_agent: SerenaAgent, symbol_name: str, def_file: str, ref_file: str) -> None:
        self._assert_find_symbol_references(serena_agent, symbol_name, def_file, ref_file)

    @pytest.mark.parametrize(
        "serena_agent,name_path,substring_matching,expected_symbol_name,expected_kind,expected_file",
        [
            pytest.param(
                Language.PYTHON,
                "OuterClass/NestedClass",
                False,
                "NestedClass",
                "Class",
                os.path.join("test_repo", "nested.py"),
                id="exact_qualname_class",
                marks=pytest.mark.python,
            ),
            pytest.param(
                Language.PYTHON,
                "OuterClass/NestedClass/find_me",
                False,
                "find_me",
                "Method",
                os.path.join("test_repo", "nested.py"),
                id="exact_qualname_method",
                marks=pytest.mark.python,
            ),
            pytest.param(
                Language.PYTHON,
                "OuterClass/NestedCl",  # Substring for NestedClass
                True,
                "NestedClass",
                "Class",
                os.path.join("test_repo", "nested.py"),
                id="substring_qualname_class",
                marks=pytest.mark.python,
            ),
            pytest.param(
                Language.PYTHON,
                "OuterClass/NestedClass/find_m",  # Substring for find_me
                True,
                "find_me",
                "Method",
                os.path.join("test_repo", "nested.py"),
                id="substring_qualname_method",
                marks=pytest.mark.python,
            ),
            pytest.param(
                Language.PYTHON,
                "/OuterClass",  # Absolute path
                False,
                "OuterClass",
                "Class",
                os.path.join("test_repo", "nested.py"),
                id="absolute_qualname_class",
                marks=pytest.mark.python,
            ),
            pytest.param(
                Language.PYTHON,
                "/OuterClass/NestedClass/find_m",  # Absolute path with substring
                True,
                "find_me",
                "Method",
                os.path.join("test_repo", "nested.py"),
                id="absolute_substring_qualname_method",
                marks=pytest.mark.python,
            ),
        ],
        indirect=["serena_agent"],
    )
    def test_find_symbol_name_path(
        self,
        serena_agent,
        name_path: str,
        substring_matching: bool,
        expected_symbol_name: str,
        expected_kind: str,
        expected_file: str,
    ):
        agent = serena_agent

        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply_ex(
            name_path_pattern=name_path,
            depth=0,
            relative_path=None,
            include_body=False,
            include_kinds=None,
            exclude_kinds=None,
            substring_matching=substring_matching,
        )

        symbols = json.loads(result)
        assert any(
            expected_symbol_name == s["name_path"].split("/")[-1]
            and expected_kind.lower() in s["kind"].lower()
            and expected_file in s["relative_path"]
            for s in symbols
        ), f"Expected to find {name_path} ({expected_kind}) in {expected_file}. Symbols: {symbols}"

    @pytest.mark.parametrize(
        "serena_agent,name_path",
        [
            pytest.param(
                Language.PYTHON,
                "/NestedClass",  # Absolute path, NestedClass is not top-level
                id="absolute_path_non_top_level_no_match",
                marks=pytest.mark.python,
            ),
            pytest.param(
                Language.PYTHON,
                "/NoSuchParent/NestedClass",  # Absolute path with non-existent parent
                id="absolute_path_non_existent_parent_no_match",
                marks=pytest.mark.python,
            ),
        ],
        indirect=["serena_agent"],
    )
    def test_find_symbol_name_path_no_match(
        self,
        serena_agent,
        name_path: str,
    ):
        agent = serena_agent

        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply_ex(
            name_path_pattern=name_path,
            depth=0,
            substring_matching=True,
        )

        symbols = json.loads(result)
        assert not symbols, f"Expected to find no symbols for {name_path}. Symbols found: {symbols}"

    @pytest.mark.parametrize(
        "serena_agent,name_path,num_expected",
        [
            pytest.param(
                Language.JAVA,
                "Model/getName",
                2,
                id="overloaded_java_method",
                marks=pytest.mark.java,
            ),
        ],
        indirect=["serena_agent"],
    )
    def test_find_symbol_overloaded_function(self, serena_agent: SerenaAgent, name_path: str, num_expected: int):
        """
        Tests whether the FindSymbolTool can find all overloads of a function/method
        (provided that the overload id remains unspecified in the name path)
        """
        agent = serena_agent

        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply_ex(
            name_path_pattern=name_path,
            depth=0,
            substring_matching=False,
        )

        symbols = json.loads(result)
        assert len(symbols) == num_expected, (
            f"Expected to find {num_expected} symbols for overloaded function {name_path}. Symbols found: {symbols}"
        )

    @pytest.mark.parametrize(
        "serena_agent,name_path,relative_path",
        [
            pytest.param(
                Language.JAVA,
                "Model/getName",
                os.path.join("src", "main", "java", "test_repo", "Model.java"),
                id="overloaded_java_method",
                marks=pytest.mark.java,
            ),
        ],
        indirect=["serena_agent"],
    )
    def test_non_unique_symbol_reference_error(self, serena_agent: SerenaAgent, name_path: str, relative_path: str):
        """
        Tests whether the tools operating on a well-defined symbol raises an error when the symbol reference is non-unique.
        We exemplarily test a retrieval tool (FindReferencingSymbolsTool) and an editing tool (ReplaceSymbolBodyTool).
        """
        match_text = "multiple"

        find_refs_tool = serena_agent.get_tool(FindReferencingSymbolsTool)
        with pytest.raises(ValueError, match=match_text):
            find_refs_tool.apply(name_path=name_path, relative_path=relative_path)

        replace_symbol_body_tool = serena_agent.get_tool(ReplaceSymbolBodyTool)
        with pytest.raises(ValueError, match=match_text):
            replace_symbol_body_tool.apply(name_path=name_path, relative_path=relative_path, body="")

    @pytest.mark.parametrize(
        "serena_agent",
        [
            pytest.param(
                Language.TYPESCRIPT,
                marks=pytest.mark.typescript,
            ),
        ],
        indirect=["serena_agent"],
    )
    def test_replace_content_regex_with_wildcard_ok(self, serena_agent: SerenaAgent):
        """
        Tests a regex-based content replacement that has a unique match
        """
        relative_path = "ws_manager.js"
        with project_file_modification_context(serena_agent, relative_path):
            replace_content_tool = serena_agent.get_tool(ReplaceContentTool)
            result = replace_content_tool.apply(
                needle=r'catch \(error\) \{\s*console.error\("Failed to connect.*?\}',
                repl='catch(error) { console.log("Never mind"); }',
                relative_path=relative_path,
                mode="regex",
            )
            assert result == SUCCESS_RESULT

    @pytest.mark.parametrize(
        "serena_agent",
        [
            pytest.param(
                Language.TYPESCRIPT,
                marks=pytest.mark.typescript,
            ),
        ],
        indirect=["serena_agent"],
    )
    @pytest.mark.parametrize("mode", ["literal", "regex"])
    def test_replace_content_with_backslashes(self, serena_agent: SerenaAgent, mode: Literal["literal", "regex"]):
        """
        Tests a content replacement where the needle and replacement strings contain backslashes.
        This is a regression test for escaping issues.
        """
        relative_path = "ws_manager.js"
        needle = r'console.log("WebSocketManager initializing\nStatus OK");'
        repl = r'console.log("WebSocketManager initialized\nAll systems go!");'
        replace_content_tool = serena_agent.get_tool(ReplaceContentTool)
        with project_file_modification_context(serena_agent, relative_path):
            result = replace_content_tool.apply(
                needle=re.escape(needle) if mode == "regex" else needle,
                repl=repl,
                relative_path=relative_path,
                mode=mode,
            )
            assert result == SUCCESS_RESULT
            new_content = read_project_file(serena_agent.get_active_project(), relative_path)
            assert repl in new_content

    @pytest.mark.parametrize(
        "serena_agent",
        [
            pytest.param(
                Language.TYPESCRIPT,
                marks=pytest.mark.typescript,
            ),
        ],
        indirect=["serena_agent"],
    )
    def test_replace_content_regex_with_wildcard_ambiguous(self, serena_agent: SerenaAgent):
        """
        Tests that an ambiguous replacement where there is a larger match that internally contains
        a smaller match triggers an exception
        """
        replace_content_tool = serena_agent.get_tool(ReplaceContentTool)
        with pytest.raises(ValueError, match="ambiguous"):
            replace_content_tool.apply(
                needle=r'catch \(error\) \{.*?this\.updateConnectionStatus\("Connection failed", false\);.*?\}',
                repl='catch(error) { console.log("Never mind"); }',
                relative_path="ws_manager.js",
                mode="regex",
            )

    @pytest.mark.parametrize(
        "serena_agent,name_path,relative_path",
        [
            pytest.param(
                Language.PYTHON,
                "User",
                os.path.join("test_repo", "models.py"),
                marks=pytest.mark.python,
            ),
            pytest.param(
                Language.JAVA,
                "Model",
                os.path.join("src", "main", "java", "test_repo", "Model.java"),
                marks=pytest.mark.java,
            ),
            pytest.param(
                Language.KOTLIN,
                "Model",
                os.path.join("src", "main", "kotlin", "test_repo", "Model.kt"),
                marks=[pytest.mark.kotlin] + ([pytest.mark.skip(reason="Kotlin LSP JVM crashes on restart in CI")] if is_ci else []),
            ),
            pytest.param(
                Language.TYPESCRIPT,
                "helperFunction",
                "index.ts",
                marks=pytest.mark.typescript,
            ),
        ],
        indirect=["serena_agent"],
    )
    def test_safe_delete_symbol_blocked_by_references(self, serena_agent: SerenaAgent, name_path: str, relative_path: str):
        """
        Tests that SafeDeleteSymbol refuses to delete a symbol that is referenced elsewhere
        and returns a message listing the referencing files.
        """
        # wrap in modification context as a safety net: if the tool has a bug and deletes anyway,
        # the file will be restored, preventing corruption of test resources
        with project_file_modification_context(serena_agent, relative_path):
            safe_delete_tool = serena_agent.get_tool(SafeDeleteSymbol)
            result = safe_delete_tool.apply(name_path_pattern=name_path, relative_path=relative_path)
            assert "Cannot delete" in result, f"Expected deletion to be blocked due to existing references, but got: {result}"
            assert "referenced in" in result, f"Expected reference information in result, but got: {result}"

    @pytest.mark.parametrize(
        "serena_agent,name_path,relative_path",
        [
            pytest.param(
                Language.PYTHON,
                "Timer",
                os.path.join("test_repo", "utils.py"),
                marks=pytest.mark.python,
            ),
            pytest.param(
                Language.JAVA,
                "ModelUser",
                os.path.join("src", "main", "java", "test_repo", "ModelUser.java"),
                marks=pytest.mark.java,
            ),
            pytest.param(
                Language.KOTLIN,
                "ModelUser",
                os.path.join("src", "main", "kotlin", "test_repo", "ModelUser.kt"),
                marks=[pytest.mark.kotlin] + ([pytest.mark.skip(reason="Kotlin LSP JVM crashes on restart in CI")] if is_ci else []),
            ),
            pytest.param(
                Language.TYPESCRIPT,
                "unusedStandaloneFunction",
                "index.ts",
                marks=pytest.mark.typescript,
            ),
        ],
        indirect=["serena_agent"],
    )
    def test_safe_delete_symbol_succeeds_when_no_references(self, serena_agent: SerenaAgent, name_path: str, relative_path: str):
        """
        Tests that SafeDeleteSymbol successfully deletes a symbol that has no references
        and that the symbol is actually removed from the file.
        """
        with project_file_modification_context(serena_agent, relative_path):
            safe_delete_tool = serena_agent.get_tool(SafeDeleteSymbol)
            result = safe_delete_tool.apply(name_path_pattern=name_path, relative_path=relative_path)
            assert result == SUCCESS_RESULT, f"Expected successful deletion, but got: {result}"

            # verify the symbol was actually removed from the file
            file_content = read_project_file(serena_agent.get_active_project(), relative_path)
            assert name_path not in file_content, (
                f"Expected symbol {name_path} to be removed from {relative_path}, but it still appears in the file content"
            )


class TestPromptProvision:
    class MockContext:
        def __init__(self, session_id: str):
            self.session = session_id

    @classmethod
    def _call_tool(cls, agent: SerenaAgent, tool_class: type[Tool], session_id: str = "global", **kwargs) -> str:
        result = agent.get_tool(tool_class).apply_ex(mcp_ctx=cls.MockContext(session_id), **kwargs)  # type: ignore
        return result

    @staticmethod
    def _assert_activation_message(result: str, project_name: str, present: bool) -> None:
        regex = r"^The project with name '" + project_name + r"'.*?is activated.$"
        match = re.search(regex, result, re.MULTILINE)
        if present:
            assert match is not None, f"Expected project activation message in result:\n{result}"
        else:
            assert match is None, f"Expected no project activation message in result:\n{result}"

    @pytest.mark.parametrize("serena_agent", [Language.PYTHON], indirect=True)
    def test_initial_instructions_provide_project_activation_message_once_per_session(self, serena_agent: SerenaAgent) -> None:
        """
        Tests that the project activation message is provided on the first call to InitialInstructionsTool for a session,
        but not on subsequent calls within the same session. #1372
        """
        project_name = "test_repo_python"
        session1 = "session1"
        session2 = "session2"

        result1 = self._call_tool(serena_agent, InitialInstructionsTool, session_id=session1)
        self._assert_activation_message(result1, project_name, present=True)

        result2 = self._call_tool(serena_agent, InitialInstructionsTool, session_id=session2)
        self._assert_activation_message(result2, project_name, present=True)

        result3 = self._call_tool(serena_agent, InitialInstructionsTool, session_id=session1)
        self._assert_activation_message(result3, project_name, present=False)

    @pytest.mark.parametrize("serena_agent", [Language.PYTHON], indirect=True)
    def test_dynamically_activated_mode_is_provided_once_per_session(self, serena_agent: SerenaAgent) -> None:
        """
        Tests that when a new project is activated within a session that has a different mode configuration (e.g. no-onboarding),
        the new mode's prompts are provided at project activation but not in subsequent initial instructions calls within the same
        session, while they are provided in the initial instructions of a new session.
        """
        project_name1 = "test_repo_python"
        project_name2 = "test_repo_java"
        session1 = "session1"
        session2 = "session2"

        # the initial instructions must contain the project activation message for the first project
        result1 = self._call_tool(serena_agent, InitialInstructionsTool, session_id=session1)
        self._assert_activation_message(result1, project_name1, present=True)

        # now activate another project which dynamically enables a new mode (no-onboarding)
        reg_project = serena_agent.serena_config.get_registered_project(project_name2)
        reg_project.project_config.default_modes = ["no-onboarding"]
        expected_new_mode_message = "The onboarding process is not applied."
        result2 = self._call_tool(serena_agent, ActivateProjectTool, project=project_name2, session_id=session1)

        # the new mode's prompt must be included in the activation message
        self._assert_activation_message(result2, project_name2, present=True)
        assert expected_new_mode_message in result2, (
            f"Expected new mode message '{expected_new_mode_message}' not found in result:\n{result2}"
        )

        # the mode prompt must not be included in subsequent calls to the initial instructions tool within the same session
        result3 = self._call_tool(serena_agent, InitialInstructionsTool, session_id=session1)
        assert expected_new_mode_message not in result3, (
            f"Expected new mode message '{expected_new_mode_message}' to not be included in subsequent calls, but it was found in result:\n{result3}"
        )

        # the mode prompt must be included in the initial instructions of a new session
        result4 = self._call_tool(serena_agent, InitialInstructionsTool, session_id=session2)
        assert expected_new_mode_message in result4, (
            f"Expected new mode message '{expected_new_mode_message}' to be included in new session, but it was not found in result:\n{result4}"
        )

        # the initial instructions for the new session must also include the activation message for the project
        self._assert_activation_message(result4, project_name2, present=True)

    @pytest.mark.parametrize("serena_agent", [Language.PYTHON], indirect=True)
    def test_activate_project_tool_always_returns_activation_message(self, serena_agent: SerenaAgent) -> None:
        project_name = "test_repo_python"
        session = "session1"

        result1 = self._call_tool(serena_agent, ActivateProjectTool, project=project_name, session_id=session)
        self._assert_activation_message(result1, project_name, present=True)

        result2 = self._call_tool(serena_agent, ActivateProjectTool, project=project_name, session_id=session)
        self._assert_activation_message(result2, project_name, present=True)
