"""
Demonstrates diagnostics tools and edit-tool diagnostic reporting on the Serena repo itself.

The script creates a temporary Python file inside this repository, introduces one warning,
shows file and symbol diagnostics, then introduces another warning and verifies that the
second edit reports only the newly introduced warning.
"""

import json
import shutil
import tempfile
from pathlib import Path
from pprint import pprint

from serena.agent import SerenaAgent
from serena.config.serena_config import LanguageBackend, ProjectConfig, RegisteredProject, SerenaConfig
from serena.constants import REPO_ROOT
from serena.project import Project
from serena.tools import (
    CreateTextFileTool,
    EditingToolWithDiagnostics,
    GetDiagnosticsForFileTool,
    GetDiagnosticsForSymbolTool,
    ReplaceContentTool,
)
from solidlsp.ls_config import Language

SEPARATOR = "=" * 80
REPO_PATH = Path(REPO_ROOT)
EDIT_RESULT_PREFIX = "Edit introduced new warning-or-higher diagnostics: "


def make_agent() -> SerenaAgent:
    """Create an LSP-backed Serena agent for the Serena repository."""
    serena_config = SerenaConfig.from_config_file()
    serena_config.web_dashboard = False
    serena_config.language_backend = LanguageBackend.LSP

    project = Project(
        project_root=str(REPO_PATH),
        project_config=ProjectConfig(
            project_name="demo_serena_repo",
            languages=[Language.PYTHON],
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
    return SerenaAgent(project="demo_serena_repo", serena_config=serena_config)


def print_section(title: str) -> None:
    """Print a visibly separated section header."""
    print(f"\n{SEPARATOR}")
    print(title)
    print(SEPARATOR)


def parse_json_result(result: str) -> object:
    """Parse and pretty-print JSON tool output."""
    parsed = json.loads(result)
    pprint(parsed, width=200)
    return parsed


def parse_edit_diagnostics_result(result: str) -> dict:
    """Extract the grouped diagnostics payload from an edit-tool result."""
    assert result.startswith(EDIT_RESULT_PREFIX), result
    return json.loads(result[len(EDIT_RESULT_PREFIX) :])


if __name__ == "__main__":
    EditingToolWithDiagnostics.ENABLE_DIAGNOSTICS = True

    temp_dir = Path(tempfile.mkdtemp(prefix="serena_demo_", dir=REPO_PATH))
    temp_file = temp_dir / "demo_temp_diagnostics.py"
    relative_path = temp_file.relative_to(REPO_PATH).as_posix()

    initial_content = """def demo_existing_issue() -> int:
    value = 1
    return value
"""

    agent = make_agent()

    try:
        # letting the language server finish startup
        agent.execute_task(lambda: None)

        create_text_file_tool = agent.get_tool(CreateTextFileTool)
        replace_content_tool = agent.get_tool(ReplaceContentTool)
        get_diagnostics_for_file_tool = agent.get_tool(GetDiagnosticsForFileTool)
        get_diagnostics_for_symbol_tool = agent.get_tool(GetDiagnosticsForSymbolTool)

        # creating a clean temporary file
        print_section("Create Temporary File")
        create_result = agent.execute_task(lambda: create_text_file_tool.apply(relative_path=relative_path, content=initial_content))
        print(create_result)

        # showing file diagnostics before introducing any warning
        print_section("Initial File Diagnostics")
        initial_diagnostics_result = agent.execute_task(
            lambda: get_diagnostics_for_file_tool.apply(relative_path=relative_path, min_severity=2)
        )
        initial_diagnostics = parse_json_result(initial_diagnostics_result)
        assert initial_diagnostics == {}, initial_diagnostics

        # introducing the first warning
        print_section("First Edit Result")
        first_edit_result = agent.execute_task(
            lambda: replace_content_tool.apply(
                relative_path=relative_path,
                needle="value = 1",
                repl="value = missing_one",
                mode="literal",
            )
        )
        print(first_edit_result)
        first_edit_diagnostics = parse_edit_diagnostics_result(first_edit_result)
        pprint(first_edit_diagnostics, width=200)
        assert "missing_one" in json.dumps(first_edit_diagnostics), first_edit_diagnostics

        # showing the file- and symbol-level diagnostics after the first warning
        print_section("File Diagnostics After First Edit")
        diagnostics_after_first_edit_result = agent.execute_task(
            lambda: get_diagnostics_for_file_tool.apply(relative_path=relative_path, min_severity=2)
        )
        diagnostics_after_first_edit = parse_json_result(diagnostics_after_first_edit_result)
        assert "missing_one" in json.dumps(diagnostics_after_first_edit), diagnostics_after_first_edit

        print_section("Symbol Diagnostics After First Edit")
        symbol_diagnostics_result = agent.execute_task(
            lambda: get_diagnostics_for_symbol_tool.apply(
                name_path="demo_existing_issue",
                reference_file=relative_path,
                min_severity=2,
            )
        )
        symbol_diagnostics = parse_json_result(symbol_diagnostics_result)
        assert "missing_one" in json.dumps(symbol_diagnostics), symbol_diagnostics

        # introducing a second warning while keeping the first one unchanged
        print_section("Second Edit Result")
        second_edit_result = agent.execute_task(
            lambda: replace_content_tool.apply(
                relative_path=relative_path,
                needle="    return value\n",
                repl="    other = missing_two\n    return value + other\n",
                mode="literal",
            )
        )
        print(second_edit_result)
        second_edit_diagnostics = parse_edit_diagnostics_result(second_edit_result)
        pprint(second_edit_diagnostics, width=200)
        second_edit_json = json.dumps(second_edit_diagnostics)
        assert "missing_two" in second_edit_json, second_edit_diagnostics
        assert "missing_one" not in second_edit_json, second_edit_diagnostics
        print("\nVerified: the second edit result reports only the newly introduced warning.")

        # showing the complete file diagnostics after both warnings exist
        print_section("File Diagnostics After Second Edit")
        diagnostics_after_second_edit_result = agent.execute_task(
            lambda: get_diagnostics_for_file_tool.apply(relative_path=relative_path, min_severity=2)
        )
        diagnostics_after_second_edit = parse_json_result(diagnostics_after_second_edit_result)
        diagnostics_after_second_edit_json = json.dumps(diagnostics_after_second_edit)
        assert "missing_one" in diagnostics_after_second_edit_json, diagnostics_after_second_edit
        assert "missing_two" in diagnostics_after_second_edit_json, diagnostics_after_second_edit
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        agent.shutdown()
