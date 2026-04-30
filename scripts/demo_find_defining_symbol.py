"""
Demonstrates both defining-symbol tools on the Python test repository.
"""

import json
import re
from pathlib import Path
from pprint import pprint

from serena.agent import SerenaAgent
from serena.config.serena_config import LanguageBackend, ProjectConfig, RegisteredProject, SerenaConfig
from serena.constants import REPO_ROOT
from serena.project import Project
from serena.tools import FindDeclarationTool
from solidlsp.ls_config import Language

SEPARATOR = "=" * 80
PYTHON_TEST_REPO = Path(REPO_ROOT) / "test" / "resources" / "repos" / "python" / "test_repo"
SERVICES_FILE = Path("test_repo") / "services.py"


def make_agent(project_root: Path, language: Language, project_name: str) -> SerenaAgent:
    """Create an LSP-backed Serena agent for a single explicit project."""
    serena_config = SerenaConfig.from_config_file()
    serena_config.web_dashboard = False
    serena_config.language_backend = LanguageBackend.LSP

    project = Project(
        project_root=str(project_root),
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
        serena_config=serena_config,
    )
    serena_config.projects = [RegisteredProject.from_project_instance(project)]
    return SerenaAgent(project=project_name, serena_config=serena_config)


def print_section(title: str) -> None:
    """Print a visibly separated section header."""
    print(f"\n{SEPARATOR}")
    print(title)
    print(SEPARATOR)


def find_identifier_occurrence_position(file_path: Path, identifier: str, occurrence_index: int = 0) -> tuple[int, int]:
    """Find the 0-based position of an identifier occurrence in a file."""
    pattern = re.compile(r"\b" + re.escape(identifier) + r"\b")
    current_occurrence_index = 0
    with file_path.open(encoding="utf-8") as f:
        for line_index, line in enumerate(f):
            for match in pattern.finditer(line):
                if current_occurrence_index == occurrence_index:
                    return line_index, match.start()
                current_occurrence_index += 1
    raise ValueError(f"Could not find occurrence {occurrence_index} of {identifier!r} in {file_path}")


if __name__ == "__main__":
    agent = make_agent(PYTHON_TEST_REPO, Language.PYTHON, "demo_python_test_repo")

    try:
        # letting the language server finish startup
        agent.execute_task(lambda: None)

        relative_path = SERVICES_FILE.as_posix()
        services_abs_path = PYTHON_TEST_REPO / SERVICES_FILE

        # resolving via regex over the full file
        find_by_regex_tool = agent.get_tool(FindDeclarationTool)
        regex_result = agent.execute_task(
            lambda: find_by_regex_tool.apply(
                regex=r"from \.models import Item, (User)",
                relative_path=relative_path,
                include_info=True,
            )
        )

        print_section("FindDefiningSymbolTool (File Regex)")
        regex_symbol = json.loads(regex_result)
        pprint(regex_symbol, width=200)

        # resolving via regex restricted to one containing symbol body
        contained_regex_result = agent.execute_task(
            lambda: find_by_regex_tool.apply(
                regex=r"=\s+(User)\(",
                relative_path=relative_path,
                containing_symbol_name_path="UserService/create_user",
                include_info=True,
            )
        )

        print_section("FindDefiningSymbolTool (Contained Regex)")
        contained_regex_symbol = json.loads(contained_regex_result)
        pprint(contained_regex_symbol, width=200)

        # validating the demonstrated result
        for symbol in [regex_symbol, contained_regex_symbol]:
            assert symbol is not None, "Expected a defining symbol result"
            assert symbol.get("relative_path") is not None
            assert "models.py" in symbol["relative_path"], symbol
            assert "User" in json.dumps(symbol), symbol
        print("\nVerified definition target: User in models.py")
    finally:
        agent.shutdown()
