"""
This script demonstrates how to use Serena's tools locally, useful
for testing or development. Here the tools will be operation the serena repo itself.
"""

from serena.agent import SerenaAgent
from serena.analytics import RegisteredTokenCountEstimator
from serena.config.serena_config import LanguageBackend, SerenaConfig
from serena.constants import REPO_ROOT
from serena.tools import (
    ExecuteSerenaCodeTool,
    FindFileTool,
    FindReferencingSymbolsTool,
    GetSymbolsOverviewTool,
    JetBrainsFindSymbolTool,
    SearchForPatternTool,
)

# Find usages of `get_context` method of all classes with `Agent` in their name
# TODO:
#  1. We shouldn't have to do `if isinstance(..., str): json.loads(...)`
#  2. Overview doesn't have a clear interface - sometimes values are strings (if no children present), sometimes dicts
#     That's not necessarily wrong (it saves tokens) but for this particular application it makes parsing more cumbersome.
#     Maybe rethink?
#  3. For some reason we get `You passed a file explicitly, but it is ignored. This is probably an error. File: src\serena\agent.py`
#     The code still works, I don't understand why this warning is triggered.
#  4. See todo in cmd_tools.py (about switching the backend to LSP)
demo_code = """
import json
from pprint import pprint
from pathlib import Path

matches = serena_agent.apply_tool("search_for_pattern", substring_pattern="class .*?Agent", restrict_search_to_code_files=True)
if isinstance(matches, str):
    matches = json.loads(matches)
    
candidate_files = list(matches)
# contains tuples of (file_path, name_path) for all run methods found
get_context_methods = []

for file_path in candidate_files:
    symbols_overview = serena_agent.apply_tool("get_symbols_overview", relative_path=file_path, depth=1)
    if isinstance(symbols_overview, str):
        symbols_overview = json.loads(symbols_overview)
    for cls_overview in symbols_overview.get("Class", []):
        if isinstance(cls_overview, str):
            continue # no members
        if isinstance(cls_overview, str):
            cls_overview = json.loads(cls_overview)
        cls_name, children = list(cls_overview.items())[0]  # has only one key which is the symbol name
        methods = children.get("Method", [])
        if "get_context" in methods:
            get_context_methods.append((str(Path(file_path)), cls_name+"/get_context"))
            
print(get_context_methods)
for file_path, name_path in get_context_methods:
    usages = serena_agent.apply_tool("find_referencing_symbols", name_path=name_path, relative_path=file_path)
    print(f"Usages of {name_path} in {file_path}:")
    pprint(usages)
"""

if __name__ == "__main__":
    serena_config = SerenaConfig.from_config_file()
    serena_config.language_backend = LanguageBackend.LSP
    serena_config.web_dashboard = False
    serena_config.token_count_estimator = RegisteredTokenCountEstimator.CHAR_COUNT.name
    serena_config.included_optional_tools = ["execute_serena_code"]
    agent = SerenaAgent(project=REPO_ROOT, serena_config=serena_config)

    # apply a tool
    find_symbol_tool = agent.get_tool(JetBrainsFindSymbolTool)
    find_refs_tool = agent.get_tool(FindReferencingSymbolsTool)
    find_file_tool = agent.get_tool(FindFileTool)
    search_pattern_tool = agent.get_tool(SearchForPatternTool)
    overview_tool = agent.get_tool(GetSymbolsOverviewTool)
    execute_code_tool = agent.get_tool(ExecuteSerenaCodeTool)

    result = agent.execute_task(lambda: execute_code_tool.apply(demo_code))
    print(result)
    # pprint(json.loads(result))
    # input("Press Enter to continue...")
