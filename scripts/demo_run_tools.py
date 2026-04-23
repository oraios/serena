"""
This script demonstrates how to use Serena's tools locally, useful
for testing or development. Here the tools will be operation the serena repo itself.
"""

import json
from pathlib import Path
from pprint import pprint

from serena.agent import SerenaAgent
from serena.config.serena_config import SerenaConfig
from serena.constants import REPO_ROOT
from serena.tools import (
    FindFileTool,
    FindReferencingSymbolsTool,
    JetBrainsFindSymbolTool,
    JetBrainsGetSymbolsOverviewTool,
    JetBrainsInlineSymbol,
    JetBrainsSafeDeleteTool,
    SearchForPatternTool,
)

if __name__ == "__main__":
    serena_config = SerenaConfig.from_config_file()
    serena_config.web_dashboard = False
    # project = Path(REPO_ROOT).parent / "serena-jetbrains-plugin-copy"
    project = Path(REPO_ROOT)
    agent = SerenaAgent(project=str(project), serena_config=serena_config)

    # apply a tool
    find_symbol_tool = agent.get_tool(JetBrainsFindSymbolTool)
    find_refs_tool = agent.get_tool(FindReferencingSymbolsTool)
    find_file_tool = agent.get_tool(FindFileTool)
    search_pattern_tool = agent.get_tool(SearchForPatternTool)
    overview_tool = agent.get_tool(JetBrainsGetSymbolsOverviewTool)
    safe_delete_tool = agent.get_tool(JetBrainsSafeDeleteTool)
    inline_symbol = agent.get_tool(JetBrainsInlineSymbol)

    result = agent.execute_task(
        lambda: overview_tool.apply(
            # name_path_pattern="SerenaAgent",
            relative_path="src/serena/agent.py",
            depth=2,
            # keep_definition=True,
        )
    )
    pprint(json.loads(result))
    # input("Press Enter to continue...")
