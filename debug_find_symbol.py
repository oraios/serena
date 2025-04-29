import json
import subprocess
from pprint import pprint

from serena.agent import *

if __name__ == "__main__":
    agent = SerenaAgent(project_file_path="/home/mpanchen/Projects/oraios/serena/c_demo/.serena/project.yml")
    overview_tool = agent.get_tool(GetSymbolsOverviewTool)
    find_symbol_tool = agent.get_tool(FindSymbolTool)
    pprint(json.loads(find_symbol_tool.apply("", within_relative_path="Xge.h", include_kinds=[5], substring_matching=True, include_body=True)))
