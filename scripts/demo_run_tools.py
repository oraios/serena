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
    JetBrainsFindImplementationsTool,
    JetBrainsFindSymbolTool,
    JetBrainsGetSymbolsOverviewTool,
    JetBrainsInlineSymbol,
    JetBrainsListInspectionsTool,
    JetBrainsRunInspectionsTool,
    JetBrainsSafeDeleteTool,
    SearchForPatternTool,
)

if __name__ == "__main__":
    serena_config = SerenaConfig.from_config_file()
    serena_config.web_dashboard = False
    # project = Path(REPO_ROOT).parent / "serena-jetbrains-plugin-copy"
    project = Path(REPO_ROOT) / "test/resources/repos/python/test_repo"
    agent = SerenaAgent(project=str(project), serena_config=serena_config)

    # apply a tool
    find_symbol_tool = agent.get_tool(JetBrainsFindSymbolTool)
    find_refs_tool = agent.get_tool(FindReferencingSymbolsTool)
    find_file_tool = agent.get_tool(FindFileTool)
    search_pattern_tool = agent.get_tool(SearchForPatternTool)
    overview_tool = agent.get_tool(JetBrainsGetSymbolsOverviewTool)
    safe_delete_tool = agent.get_tool(JetBrainsSafeDeleteTool)
    inline_symbol = agent.get_tool(JetBrainsInlineSymbol)
    inspections_tool = agent.get_tool(JetBrainsRunInspectionsTool)
    list_inspections_tool = agent.get_tool(JetBrainsListInspectionsTool)
    find_implementations_tool = agent.get_tool(JetBrainsFindImplementationsTool)

    result = agent.execute_task(
        lambda: find_implementations_tool.apply(
            relative_path="test_repo/nested.py",
            # min_severity="WEAK_WARNING"
            name_path="b",
            include_info=True,
            # language="Python",
            # keep_definition=True,
        )
    )
    pprint(json.loads(result))
    # input("Press Enter to continue...")
