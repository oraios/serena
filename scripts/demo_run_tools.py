"""
This script demonstrates how to use Serena's tools locally, useful
for testing or development. Here the config is pointing to the serena repo itself,
it assumes that you already have a serena_config.yml file setup.
"""

import json
from pathlib import Path
from pprint import pprint

from serena.agent import *

project_root = Path(__file__).parent.parent

if __name__ == "__main__":
    agent = SerenaAgent(project_file_path=str(project_root / ".serena" / "project.yml"))
    overview_tool = agent.get_tool(GetSymbolsOverviewTool)
    find_symbol_tool = agent.get_tool(FindSymbolTool)

    print("Getting an overview of the util package\n")
    pprint(json.loads(overview_tool.apply("src/serena/util")))

    print("\n\n")

    print("Finding the symbol 'SerenaAgent'\n")
    pprint(json.loads(find_symbol_tool.apply("SerenaAgent")))
