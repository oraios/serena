#!/usr/bin/env python3
"""Debug script to understand Lean 4 reference finding behavior in Serena."""

import json
import os
import sys
from pathlib import Path

# Add serena to path
sys.path.insert(0, str(Path(__file__).parent))

from serena.agent import SerenaAgent
from serena.config.serena_config import ProjectConfig, RegisteredProject, SerenaConfig
from serena.project import Project
from serena.tools import FindReferencingSymbolsTool, FindSymbolTool
from solidlsp.ls_config import Language
from test.conftest import get_repo_path


def debug_lean4_references():
    """Debug Lean 4 reference finding in Serena."""
    repo_path = get_repo_path(Language.LEAN4)

    # Create test project
    project_name = f"test_repo_{Language.LEAN4}"
    project = Project(
        project_root=str(repo_path),
        project_config=ProjectConfig(
            project_name=project_name,
            language=Language.LEAN4,
            ignored_paths=[],
            excluded_tools=set(),
            read_only=False,
            ignore_all_files_in_gitignore=True,
            initial_prompt="",
            encoding="utf-8",
        ),
    )

    # Create config
    config = SerenaConfig(gui_log_window_enabled=False, web_dashboard=False)
    config.projects = [RegisteredProject.from_project_instance(project)]

    # Create agent
    agent = SerenaAgent(project=project_name, serena_config=config)

    # Test find symbol
    print("=== Finding Calculator symbol ===")
    find_symbol_tool = agent.get_tool(FindSymbolTool)
    result = find_symbol_tool.apply_ex(name_path="Calculator", relative_path="Serena/Basic.lean")
    symbols = json.loads(result)
    print(f"Found {len(symbols)} symbols")
    for sym in symbols:
        if "body_location" in sym:
            print(f"  Symbol: {sym['name_path']} at line {sym['body_location']['start_line']}")
        else:
            print(f"  Symbol: {sym['name_path']} (no location info)")
        print(f"    Location: {sym.get('relative_path', 'NO PATH')}")

    if symbols:
        # Now test references
        print("\n=== Finding references to Calculator ===")
        calc_symbol = symbols[0]
        find_refs_tool = agent.get_tool(FindReferencingSymbolsTool)

        # Debug: What's being passed
        print(f"  Using name_path: {calc_symbol['name_path']}")
        print(f"  Using relative_path: {calc_symbol.get('relative_path', 'Serena/Basic.lean')}")

        refs_result = find_refs_tool.apply_ex(
            name_path=calc_symbol["name_path"], relative_path=calc_symbol.get("relative_path", "Serena/Basic.lean")
        )
        refs = json.loads(refs_result)
        print(f"Found {len(refs)} references")
        for ref in refs:
            print(f"  Reference in {ref['relative_path']} at line {ref['range']['start']['line'] + 1}")
            if "snippet" in ref:
                print(f"    Snippet: {ref['snippet']}")


if __name__ == "__main__":
    debug_lean4_references()
