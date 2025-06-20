import json
import os
import time
from dataclasses import dataclass

import pytest

from multilspy.multilspy_config import Language
from serena.agent import FindReferencingSymbolsTool, FindSymbolTool, Project, ProjectConfig, SerenaAgent, SerenaConfigBase
from serena.process_isolated_agent import ProcessIsolatedSerenaAgent
from test.conftest import get_repo_path


@dataclass
class SerenaConfigForTests(SerenaConfigBase):
    """
    In-memory implementation of Serena configuration with the GUI disabled.
    """

    gui_log_window_enabled: bool = False
    web_dashboard: bool = False

    def __post_init__(self):
        # Initialize with empty projects list if not already set
        if not hasattr(self, "projects") or self.projects is None:
            self.projects = []


@pytest.fixture
def serena_config():
    """Create an in-memory configuration for tests with test repositories pre-registered."""
    # Create test projects for all supported languages
    test_projects = []
    for language in [Language.PYTHON, Language.GO, Language.JAVA, Language.RUST, Language.TYPESCRIPT, Language.PHP]:
        repo_path = get_repo_path(language)
        if repo_path.exists():
            project_name = f"test_repo_{language}"
            project = Project(
                project_root=str(repo_path),
                project_config=ProjectConfig(
                    project_name=project_name,
                    language=language,
                    ignored_paths=[],
                    excluded_tools=set(),
                    read_only=False,
                    ignore_all_files_in_gitignore=True,
                    initial_prompt="",
                    encoding="utf-8",
                ),
            )
            test_projects.append(project)

    config = SerenaConfigForTests()
    config.projects = test_projects
    return config


@pytest.fixture
def serena_agent(request: pytest.FixtureRequest, serena_config):
    language = Language(request.param)
    project_name = f"test_repo_{language}"

    # Check if this test should use process isolation by looking at the test parameters
    isolated_process = False
    if hasattr(request, "node") and hasattr(request.node, "callspec"):
        # Get the isolated_process parameter value from the test
        params = request.node.callspec.params
        isolated_process = params.get("isolated_process", False)

    if isolated_process:
        agent = ProcessIsolatedSerenaAgent(project=project_name, serena_config=serena_config)
        agent.start()

        # Add cleanup to stop the process
        def cleanup():
            agent.stop()

        request.addfinalizer(cleanup)
        return agent
    else:
        return SerenaAgent(project=project_name, serena_config=serena_config)


class TestSerenaAgent:
    @pytest.mark.parametrize(
        "isolated_process", [pytest.param(False, id="direct"), pytest.param(True, id="isolated", marks=pytest.mark.isolated_process)]
    )
    @pytest.mark.parametrize(
        "serena_agent,symbol_name,expected_kind,expected_file",
        [
            pytest.param(Language.PYTHON, "User", "Class", "models.py", marks=pytest.mark.python),
            pytest.param(Language.GO, "Helper", "Function", "main.go", marks=pytest.mark.go),
            pytest.param(Language.JAVA, "Model", "Class", "Model.java", marks=pytest.mark.java),
            pytest.param(Language.RUST, "add", "Function", "lib.rs", marks=pytest.mark.rust),
            pytest.param(Language.TYPESCRIPT, "DemoClass", "Class", "index.ts", marks=pytest.mark.typescript),
            pytest.param(Language.PHP, "helperFunction", "Function", "helper.php", marks=pytest.mark.php),
        ],
        indirect=["serena_agent"],
    )
    def test_find_symbol(self, serena_agent, symbol_name: str, expected_kind: str, expected_file: str, isolated_process: bool):
        agent = serena_agent
        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply_ex(name_path=symbol_name)

        symbols = json.loads(result)
        assert any(
            symbol_name in s["name_path"] and expected_kind.lower() in s["kind"].lower() and expected_file in s["relative_path"]
            for s in symbols
        ), f"Expected to find {symbol_name} ({expected_kind}) in {expected_file}"

    @pytest.mark.parametrize(
        "isolated_process", [pytest.param(False, id="direct"), pytest.param(True, id="isolated", marks=pytest.mark.isolated_process)]
    )
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
            pytest.param(Language.RUST, "add", os.path.join("src", "lib.rs"), os.path.join("src", "main.rs"), marks=pytest.mark.rust),
            pytest.param(Language.TYPESCRIPT, "helperFunction", "index.ts", "use_helper.ts", marks=pytest.mark.typescript),
            pytest.param(Language.PHP, "helperFunction", "helper.php", "index.php", marks=pytest.mark.php),
        ],
        indirect=["serena_agent"],
    )
    def test_find_symbol_references(self, serena_agent, symbol_name: str, def_file: str, ref_file: str, isolated_process: bool) -> None:
        agent = serena_agent

        # Find the symbol location first
        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply_ex(name_path=symbol_name, relative_path=def_file)

        time.sleep(1)
        symbols = json.loads(result)
        # Find the definition
        def_symbol = symbols[0]

        # Now find references
        find_refs_tool = agent.get_tool(FindReferencingSymbolsTool)
        result = find_refs_tool.apply_ex(name_path=def_symbol["name_path"], relative_path=def_symbol["relative_path"])

        refs = json.loads(result)
        assert any(
            ref["relative_path"] == ref_file for ref in refs
        ), f"Expected to find reference to {symbol_name} in {ref_file}. refs={refs}"

    @pytest.mark.parametrize(
        "isolated_process", [pytest.param(False, id="direct"), pytest.param(True, id="isolated", marks=pytest.mark.isolated_process)]
    )
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
        isolated_process: bool,
    ):
        agent = serena_agent

        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply_ex(
            name_path=name_path,
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
        ), f"Expected to find {name_path} ({expected_kind}) in {expected_file} for {agent._active_project.language.name}. Symbols: {symbols}"

    @pytest.mark.parametrize(
        "isolated_process", [pytest.param(False, id="direct"), pytest.param(True, id="isolated", marks=pytest.mark.isolated_process)]
    )
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
        isolated_process: bool,
    ):
        agent = serena_agent

        find_symbol_tool = agent.get_tool(FindSymbolTool)
        result = find_symbol_tool.apply_ex(
            name_path=name_path,
            depth=0,
            substring_matching=True,
        )

        symbols = json.loads(result)
        assert not symbols, f"Expected to find no symbols for {name_path}. Symbols found: {symbols}"

    @pytest.mark.parametrize(
        "isolated_process", [pytest.param(False, id="direct"), pytest.param(True, id="isolated", marks=pytest.mark.isolated_process)]
    )
    @pytest.mark.parametrize(
        "serena_agent,symbol_name,expected_signature_contains,expected_docstring_contains",
        [
            pytest.param(
                Language.PYTHON,
                "setup_logging",
                'def setup_logging(level: str = "INFO") -> Logger',
                "Set up and return a configured logger",
                marks=pytest.mark.python,
            ),
            pytest.param(
                Language.TYPESCRIPT,
                "DemoClass",
                "class DemoClass",
                "demonstration class that holds a numeric value",
                marks=pytest.mark.typescript,
            ),
            pytest.param(
                Language.JAVA,
                "factorial",
                "public static long factorial(int n)",
                "Calculates the factorial of a given number",
                marks=pytest.mark.java,
            ),
            pytest.param(
                Language.RUST,
                "factorial",
                "pub fn factorial(n: u32) -> Option<u64>",
                "Calculates the factorial of a given number",
                marks=pytest.mark.rust,
            ),
        ],
        indirect=["serena_agent"],
    )
    def test_find_symbol_with_signature_and_docstring(
        self, serena_agent, symbol_name: str, expected_signature_contains: str, expected_docstring_contains: str, isolated_process: bool
    ):
        """Test that FindSymbolTool can retrieve signature and docstring information."""
        agent = serena_agent
        find_symbol_tool = agent.get_tool(FindSymbolTool)

        # For Java and Rust, we need substring matching since method names include parameter types
        # e.g., Java: "factorial(int)" instead of just "factorial"
        active_project = agent.get_active_project()
        assert active_project is not None, "Expected an active project"
        language = active_project.project_config.language

        use_substring_matching = language in [Language.JAVA, Language.RUST]

        # Test with signature and docstring enabled
        result = find_symbol_tool.apply_ex(
            name_path=symbol_name, include_signature=True, include_docstring=True, substring_matching=use_substring_matching
        )

        symbols = json.loads(result)
        assert len(symbols) > 0, f"Expected to find symbol {symbol_name}"

        # Find the specific symbol we're looking for
        target_symbol = None
        for symbol in symbols:
            if symbol_name in symbol["name_path"]:
                target_symbol = symbol
                break

        assert target_symbol is not None, f"Expected to find symbol {symbol_name} in results"

        # Check signature if language server supports it
        if target_symbol.get("signature"):
            assert (
                expected_signature_contains.lower() in target_symbol["signature"].lower()
            ), f"Expected signature to contain '{expected_signature_contains}', got '{target_symbol.get('signature')}'"

        # Check docstring if language server supports it
        if target_symbol.get("docstring"):
            assert (
                expected_docstring_contains.lower() in target_symbol["docstring"].lower()
            ), f"Expected docstring to contain '{expected_docstring_contains}', got '{target_symbol.get('docstring')}'"

    @pytest.mark.parametrize(
        "isolated_process", [pytest.param(False, id="direct"), pytest.param(True, id="isolated", marks=pytest.mark.isolated_process)]
    )
    @pytest.mark.parametrize(
        "serena_agent,symbol_name",
        [
            pytest.param(Language.PYTHON, "setup_logging", marks=pytest.mark.python),
            pytest.param(Language.TYPESCRIPT, "DemoClass", marks=pytest.mark.typescript),
        ],
        indirect=["serena_agent"],
    )
    def test_find_symbol_signature_docstring_optional(self, serena_agent, symbol_name: str, isolated_process: bool):
        """Test that signature and docstring are optional in FindSymbolTool."""
        agent = serena_agent
        find_symbol_tool = agent.get_tool(FindSymbolTool)

        # Test without signature/docstring (default behavior)
        result = find_symbol_tool.apply_ex(name_path=symbol_name)
        symbols = json.loads(result)

        assert len(symbols) > 0, f"Expected to find symbol {symbol_name}"
        symbol = symbols[0]

        # Should not include signature/docstring by default
        assert "signature" not in symbol or symbol["signature"] is None
        assert "docstring" not in symbol or symbol["docstring"] is None

        # Test with only signature
        result = find_symbol_tool.apply_ex(name_path=symbol_name, include_signature=True)
        symbols = json.loads(result)

        assert len(symbols) > 0
        symbol = symbols[0]
        # May or may not have signature depending on language server support
        # But should not have docstring
        assert "docstring" not in symbol or symbol["docstring"] is None

        # Test with only docstring
        result = find_symbol_tool.apply_ex(name_path=symbol_name, include_docstring=True)
        symbols = json.loads(result)

        assert len(symbols) > 0
        symbol = symbols[0]
        # May or may not have docstring depending on language server support
        # But should not have signature
        assert "signature" not in symbol or symbol["signature"] is None
