"""
This script demonstrates how to use Serena's tools locally, useful
for testing or development. Here the tools will be operation the serena repo itself.
"""

import json
from pprint import pprint

from serena.agent import SerenaAgent
from serena.config.serena_config import SerenaConfig
from serena.constants import REPO_ROOT
from serena.tools import (
    FindFileTool,
    FindReferencingSymbolsTool,
    JetBrainsFindSymbolTool,
    JetBrainsGetSymbolsOverviewTool,
    SearchForPatternTool,
)

if __name__ == "__main__":
    serena_config = SerenaConfig.from_config_file()
    serena_config.web_dashboard = False
    agent = SerenaAgent(project=REPO_ROOT, serena_config=serena_config)

    # apply a tool
    find_symbol_tool = agent.get_tool(JetBrainsFindSymbolTool)
    find_refs_tool = agent.get_tool(FindReferencingSymbolsTool)
    find_file_tool = agent.get_tool(FindFileTool)
    search_pattern_tool = agent.get_tool(SearchForPatternTool)
    overview_tool = agent.get_tool(JetBrainsGetSymbolsOverviewTool)

    result = agent.execute_task(
        lambda: find_symbol_tool.apply("SerenaAgent/get_tool_description_override"),
    )
    pprint(json.loads(result))
    # input("Press Enter to continue...")
