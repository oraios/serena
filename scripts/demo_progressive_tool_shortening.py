"""
Demonstrates the progressive shortening of tool results when max_answer_chars is exceeded.
It exercises all tools that use _limit_length with shortened_results,
printing the full result, then progressively tighter max_answer_chars
to show the successive shortening stages. Both LSP and JetBrains backends
are tested (JB is skipped if no IDE is running).
"""

import json
from pprint import pprint

from serena.agent import SerenaAgent
from serena.config.serena_config import LanguageBackend, SerenaConfig
from serena.constants import REPO_ROOT
from serena.tools import (
    FindReferencingSymbolsTool,
    FindSymbolTool,
    GetSymbolsOverviewTool,
    JetBrainsFindReferencingSymbolsTool,
    JetBrainsFindSymbolTool,
    JetBrainsGetSymbolsOverviewTool,
    SearchForPatternTool,
)

SEPARATOR = "=" * 80

# symbol with many references across multiple files, good for testing shortening
REF_SYMBOL = "_limit_length"
REF_FILE = "src/serena/tools/tools_base.py"

# file with many symbols, good for testing overview shortening
OVERVIEW_FILE = "src/serena/tools/tools_base.py"


def run_with_shrinking(agent: SerenaAgent, label: str, fn, char_limits: list[int]) -> None:
    """Run a tool call at several max_answer_chars limits and print results."""
    for limit in char_limits:
        tag = f"{label} (max_answer_chars={limit})"
        print(f"\n{SEPARATOR}")
        print(tag)
        print(SEPARATOR)
        result = agent.execute_task(lambda lim=limit: fn(lim))
        n = len(result)
        print(f"[length={n}]")
        try:
            pprint(json.loads(result), width=200)
        except (json.JSONDecodeError, ValueError):
            print(result)


def run_lsp_tools(agent: SerenaAgent) -> None:
    print("\n\n### LSP BACKEND ###\n")

    # LSP: FindReferencingSymbolsTool — three shortening stages:
    #   1. refs without context lines  2. per-file counts  3. total summary
    lsp_refs = agent.get_tool(FindReferencingSymbolsTool)
    run_with_shrinking(
        agent,
        "LSP FindReferencingSymbolsTool",
        lambda lim: lsp_refs.apply(REF_SYMBOL, REF_FILE, max_answer_chars=lim),
        char_limits=[50000, 3000, 500, 200],
    )

    # LSP: FindSymbolTool — one shortening stage: names with kind only
    lsp_find = agent.get_tool(FindSymbolTool)
    run_with_shrinking(
        agent,
        "LSP FindSymbolTool (depth=1)",
        lambda lim: lsp_find.apply("Tool", relative_path=REF_FILE, depth=1, max_answer_chars=lim),
        char_limits=[50000, 200],
    )

    # LSP: FindSymbolTool with max_matches exceeded — tests the early-return shortened path
    print(f"\n{SEPARATOR}")
    print("LSP FindSymbolTool (max_matches=1, broad search)")
    print(SEPARATOR)
    result = agent.execute_task(lambda: lsp_find.apply("apply", max_matches=1))
    print(f"[length={len(result)}]")
    print(result)

    # LSP: GetSymbolsOverviewTool — two shortening stages for depth>0:
    #   1. depth-0 overview  2. counts by kind
    # one stage for depth==0: counts by kind
    lsp_overview = agent.get_tool(GetSymbolsOverviewTool)
    run_with_shrinking(
        agent,
        "LSP GetSymbolsOverviewTool (depth=1)",
        lambda lim: lsp_overview.apply(OVERVIEW_FILE, depth=1, max_answer_chars=lim),
        char_limits=[50000, 500, 200],
    )
    run_with_shrinking(
        agent,
        "LSP GetSymbolsOverviewTool (depth=0)",
        lambda lim: lsp_overview.apply(OVERVIEW_FILE, depth=0, max_answer_chars=lim),
        char_limits=[50000, 200],
    )


def run_backend_independent_tools(agent: SerenaAgent) -> None:
    print("\n\n### BACKEND-INDEPENDENT TOOLS ###\n")

    # SearchForPatternTool — three shortening stages:
    #   1. match lines per file (no context)  2. match counts per file  3. total summary
    search_tool = agent.get_tool(SearchForPatternTool)
    run_with_shrinking(
        agent,
        "SearchForPatternTool (with context)",
        lambda lim: search_tool.apply(
            "_limit_length",
            context_lines_before=1,
            context_lines_after=1,
            relative_path="src/serena/tools",
            max_answer_chars=lim,
        ),
        char_limits=[50000, 1000, 200],
    )


def run_jb_tools(agent: SerenaAgent) -> None:
    print("\n\n### JETBRAINS BACKEND ###\n")

    # JB: FindReferencingSymbolsTool — two shortening stages:
    #   1. per-file counts  2. total summary
    jb_refs = agent.get_tool(JetBrainsFindReferencingSymbolsTool)
    run_with_shrinking(
        agent,
        "JB FindReferencingSymbolsTool",
        lambda lim: jb_refs.apply(REF_SYMBOL, REF_FILE, max_answer_chars=lim),
        char_limits=[50000, 500, 200],
    )

    # JB: FindSymbolTool — one shortening stage: names with kind only
    jb_find = agent.get_tool(JetBrainsFindSymbolTool)
    run_with_shrinking(
        agent,
        "JB FindSymbolTool (depth=1)",
        lambda lim: jb_find.apply("Tool", relative_path=REF_FILE, depth=1, max_answer_chars=lim),
        char_limits=[50000, 200],
    )

    # JB: FindSymbolTool with max_matches exceeded — tests the early-return shortened path
    print(f"\n{SEPARATOR}")
    print("JB FindSymbolTool (max_matches=1, broad search)")
    print(SEPARATOR)
    result = agent.execute_task(lambda: jb_find.apply("apply", max_matches=1))
    print(f"[length={len(result)}]")
    print(result)

    # JB: GetSymbolsOverviewTool — two shortening stages for depth>0:
    #   1. depth-0 overview  2. counts by type
    # two stages for depth==0: grouped symbols, then counts by type
    jb_overview = agent.get_tool(JetBrainsGetSymbolsOverviewTool)
    run_with_shrinking(
        agent,
        "JB GetSymbolsOverviewTool (depth=1)",
        lambda lim: jb_overview.apply(OVERVIEW_FILE, depth=1, max_answer_chars=lim),
        char_limits=[50000, 500, 200],
    )
    run_with_shrinking(
        agent,
        "JB GetSymbolsOverviewTool (depth=0)",
        lambda lim: jb_overview.apply(OVERVIEW_FILE, depth=0, max_answer_chars=lim),
        char_limits=[50000, 200],
    )


def make_agent(backend: LanguageBackend) -> SerenaAgent:
    config = SerenaConfig.from_config_file()
    config.web_dashboard = False
    config.language_backend = backend
    return SerenaAgent(project=REPO_ROOT, serena_config=config)


if __name__ == "__main__":
    # LSP backend
    lsp_agent = make_agent(LanguageBackend.LSP)
    try:
        run_lsp_tools(lsp_agent)
        run_backend_independent_tools(lsp_agent)
    finally:
        lsp_agent.on_shutdown()

    # JetBrains backend (requires a running IDE)
    try:
        jb_agent = make_agent(LanguageBackend.JETBRAINS)
        try:
            run_jb_tools(jb_agent)
        finally:
            jb_agent.on_shutdown()
    except Exception as e:
        print(f"\nJetBrains backend not available, skipping: {e}")
