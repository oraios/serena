"""
Standalone demo script that runs Serena tools using the LSP backend — no JetBrains IDE required.
Useful for local development and testing your fork independently.
"""

import json
from pprint import pprint

from serena.agent import SerenaAgent
from serena.config.serena_config import SerenaConfig
from serena.constants import REPO_ROOT
from serena.tools import (
    FindFileTool,
    FindReferencingSymbolsTool,
    FindSymbolTool,
    GetSymbolsOverviewTool,
    SearchForPatternTool,
)

if __name__ == "__main__":
    serena_config = SerenaConfig.from_config_file()
    serena_config.web_dashboard = False
    agent = SerenaAgent(project=REPO_ROOT, serena_config=serena_config)

    find_symbol_tool = agent.get_tool(FindSymbolTool)
    find_refs_tool = agent.get_tool(FindReferencingSymbolsTool)
    find_file_tool = agent.get_tool(FindFileTool)
    search_pattern_tool = agent.get_tool(SearchForPatternTool)
    overview_tool = agent.get_tool(GetSymbolsOverviewTool)

    # Example 1: find a symbol by name path (LSP-based)
    result = agent.execute_task(
        lambda: find_symbol_tool.apply("SerenaAgent/get_tool_description_override"),
        name="find_symbol",
    )
    print("=== find_symbol ===")
    pprint(json.loads(result))

    # Example 2: get symbols overview of a file
    result2 = agent.execute_task(
        lambda: overview_tool.apply("src/serena/agent.py", depth=1),
        name="overview",
    )
    print("\n=== overview: src/serena/agent.py ===")
    pprint(json.loads(result2))
