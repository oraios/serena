"""
Interactive tool execution script for Serena's tools.
Choose a tool and pass arguments through the terminal.
"""

import argparse
import json
from pprint import pprint

from serena.agent import SerenaAgent
from serena.config.serena_config import SerenaConfig
from serena.constants import REPO_ROOT
from serena.tools import FindFileTool, FindReferencingSymbolsTool, FindSymbolTool, GetSymbolsOverviewTool, SearchForPatternTool


def display_available_tools():
    """Display the available tools and their descriptions."""
    tools_info = {
        "1": ("FindSymbolTool", "Find symbols by name or pattern"),
        "2": ("FindReferencingSymbolsTool", "Find symbols that reference a given symbol"),
        "3": ("FindFileTool", "Find files by name or pattern"),
        "4": ("SearchForPatternTool", "Search for text patterns in files"),
        "5": ("GetSymbolsOverviewTool", "Get an overview of symbols in the project"),
    }

    print("\n=== Available Tools ===")
    for key, (name, desc) in tools_info.items():
        print(f"{key}. {name}: {desc}")
    print("q. Quit")
    return tools_info


def get_tool_arguments(tool_name):
    """Get arguments for the selected tool."""
    if tool_name == "FindSymbolTool":
        name_path = input("Enter symbol name/pattern: ").strip()
        depth_input = input("Enter depth (default=0): ").strip()
        depth = int(depth_input) if depth_input else 0
        relative_path = input("Enter relative path to restrict search (optional, press Enter to skip): ").strip()
        include_body = input("Include symbol body? (y/N): ").strip().lower() == "y"

        # Include/exclude kinds - show available options
        print("\nAvailable symbol kinds:")
        print("1=file, 2=module, 3=namespace, 4=package, 5=class, 6=method, 7=property, 8=field,")
        print("9=constructor, 10=enum, 11=interface, 12=function, 13=variable, 14=constant,")
        print("15=string, 16=number, 17=boolean, 18=array, 19=object, 20=key, 21=null,")
        print("22=enum member, 23=struct, 24=event, 25=operator, 26=type parameter")

        include_kinds_input = input("Enter include kinds (comma-separated numbers, optional): ").strip()
        include_kinds = [int(k.strip()) for k in include_kinds_input.split(",")] if include_kinds_input else []

        exclude_kinds_input = input("Enter exclude kinds (comma-separated numbers, optional): ").strip()
        exclude_kinds = [int(k.strip()) for k in exclude_kinds_input.split(",")] if exclude_kinds_input else []

        substring_matching = input("Use substring matching? (y/N): ").strip().lower() == "y"

        max_answer_chars_input = input("Enter max answer chars (default=10000): ").strip()
        max_answer_chars = int(max_answer_chars_input) if max_answer_chars_input else 10000

        return {
            "name_path": name_path,
            "depth": depth,
            "relative_path": relative_path,
            "include_body": include_body,
            "include_kinds": include_kinds,
            "exclude_kinds": exclude_kinds,
            "substring_matching": substring_matching,
            "max_answer_chars": max_answer_chars,
        }

    elif tool_name == "FindReferencingSymbolsTool":
        name_path = input("Enter symbol name/path: ").strip()
        relative_path = input("Enter relative path to file containing the symbol: ").strip()

        print("\nAvailable symbol kinds (same as above)")
        include_kinds_input = input("Enter include kinds (comma-separated numbers, optional): ").strip()
        include_kinds = [int(k.strip()) for k in include_kinds_input.split(",")] if include_kinds_input else []

        exclude_kinds_input = input("Enter exclude kinds (comma-separated numbers, optional): ").strip()
        exclude_kinds = [int(k.strip()) for k in exclude_kinds_input.split(",")] if exclude_kinds_input else []

        max_answer_chars_input = input("Enter max answer chars (default=10000): ").strip()
        max_answer_chars = int(max_answer_chars_input) if max_answer_chars_input else 10000

        return {
            "name_path": name_path,
            "relative_path": relative_path,
            "include_kinds": include_kinds,
            "exclude_kinds": exclude_kinds,
            "max_answer_chars": max_answer_chars,
        }

    elif tool_name == "FindFileTool":
        file_mask = input("Enter file mask (e.g., *.py, test*.java): ").strip()
        relative_path = input("Enter relative path to search in (use '.' for project root): ").strip()
        return {"file_mask": file_mask, "relative_path": relative_path}

    elif tool_name == "SearchForPatternTool":
        substring_pattern = input("Enter search pattern (regex): ").strip()

        context_before_input = input("Enter context lines before (default=0): ").strip()
        context_lines_before = int(context_before_input) if context_before_input else 0

        context_after_input = input("Enter context lines after (default=0): ").strip()
        context_lines_after = int(context_after_input) if context_after_input else 0

        paths_include_glob = input("Enter include glob pattern (optional, e.g., *.py): ").strip()
        paths_exclude_glob = input("Enter exclude glob pattern (optional, e.g., *test*): ").strip()
        relative_path = input("Enter relative path to restrict search (optional): ").strip()

        restrict_to_code = input("Restrict search to code files only? (y/N): ").strip().lower() == "y"

        max_answer_chars_input = input("Enter max answer chars (default=10000): ").strip()
        max_answer_chars = int(max_answer_chars_input) if max_answer_chars_input else 10000

        return {
            "substring_pattern": substring_pattern,
            "context_lines_before": context_lines_before,
            "context_lines_after": context_lines_after,
            "paths_include_glob": paths_include_glob,
            "paths_exclude_glob": paths_exclude_glob,
            "relative_path": relative_path,
            "restrict_search_to_code_files": restrict_to_code,
            "max_answer_chars": max_answer_chars,
        }

    elif tool_name == "GetSymbolsOverviewTool":
        relative_path = input("Enter relative path to file: ").strip()
        max_answer_chars_input = input("Enter max answer chars (default=10000): ").strip()
        max_answer_chars = int(max_answer_chars_input) if max_answer_chars_input else 10000
        return {"relative_path": relative_path, "max_answer_chars": max_answer_chars}

    return {}


def execute_tool(agent, tool_name, tool_instance, args):
    """Execute the selected tool with given arguments."""
    try:
        if tool_name == "FindSymbolTool":
            # Filter out empty string values for optional parameters
            kwargs = {}
            if args.get("relative_path"):
                kwargs["relative_path"] = args["relative_path"]
            if args.get("include_kinds"):
                kwargs["include_kinds"] = args["include_kinds"]
            if args.get("exclude_kinds"):
                kwargs["exclude_kinds"] = args["exclude_kinds"]

            result = agent.execute_task(
                lambda: tool_instance.apply(
                    args["name_path"],
                    depth=args["depth"],
                    include_body=args["include_body"],
                    substring_matching=args["substring_matching"],
                    max_answer_chars=args["max_answer_chars"],
                    **kwargs,
                )
            )

        elif tool_name == "FindReferencingSymbolsTool":
            # Filter out empty values for optional parameters
            kwargs = {}
            if args.get("include_kinds"):
                kwargs["include_kinds"] = args["include_kinds"]
            if args.get("exclude_kinds"):
                kwargs["exclude_kinds"] = args["exclude_kinds"]

            result = agent.execute_task(
                lambda: tool_instance.apply(args["name_path"], args["relative_path"], max_answer_chars=args["max_answer_chars"], **kwargs)
            )

        elif tool_name == "FindFileTool":
            result = agent.execute_task(lambda: tool_instance.apply(args["file_mask"], args["relative_path"]))

        elif tool_name == "SearchForPatternTool":
            # Filter out empty values for optional parameters
            kwargs = {}
            if args.get("paths_include_glob"):
                kwargs["paths_include_glob"] = args["paths_include_glob"]
            if args.get("paths_exclude_glob"):
                kwargs["paths_exclude_glob"] = args["paths_exclude_glob"]
            if args.get("relative_path"):
                kwargs["relative_path"] = args["relative_path"]

            result = agent.execute_task(
                lambda: tool_instance.apply(
                    args["substring_pattern"],
                    context_lines_before=args["context_lines_before"],
                    context_lines_after=args["context_lines_after"],
                    restrict_search_to_code_files=args["restrict_search_to_code_files"],
                    max_answer_chars=args["max_answer_chars"],
                    **kwargs,
                )
            )

        elif tool_name == "GetSymbolsOverviewTool":
            result = agent.execute_task(lambda: tool_instance.apply(args["relative_path"], max_answer_chars=args["max_answer_chars"]))
        else:
            print(f"Unknown tool: {tool_name}")
            return

        print("\n=== Result ===")
        pprint(json.loads(result))

    except Exception as e:
        print(f"Error executing tool: {e}")
        import traceback

        traceback.print_exc()


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Interactive tool execution script for Serena's tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python demo_run_tools.py
  uv run python demo_run_tools.py --project /path/to/project
  uv run python demo_run_tools.py --gui-log --web-dashboard
  uv run python demo_run_tools.py --project /path/to/project --trace-lsp --gui-log
  
Available Tools:
  1. FindSymbolTool: Find symbols by name or pattern
  2. FindReferencingSymbolsTool: Find symbols that reference a given symbol
  3. FindFileTool: Find files by name or pattern
  4. SearchForPatternTool: Search for text patterns in files
  5. GetSymbolsOverviewTool: Get an overview of symbols in the project
        """,
    )

    parser.add_argument("--project", type=str, default=REPO_ROOT, help=f"Path to the project directory (default: {REPO_ROOT})")

    parser.add_argument("--gui-log", action="store_true", help="Enable GUI log window (default: False)")

    parser.add_argument("--web-dashboard", action="store_true", help="Enable web dashboard (default: False)")

    parser.add_argument("--trace-lsp", action="store_true", help="Enable LSP communication tracing (default: False)")

    return parser.parse_args()


if __name__ == "__main__":
    # Parse command line arguments
    args = parse_arguments()

    print(f"Initializing Serena agent with project: {args.project}")
    print(f"Configuration: GUI Log={args.gui_log}, Web Dashboard={args.web_dashboard}, LSP Trace={args.trace_lsp}")

    agent = SerenaAgent(
        project=args.project,
        serena_config=SerenaConfig(
            gui_log_window_enabled=args.gui_log, web_dashboard=args.web_dashboard, trace_lsp_communication=args.trace_lsp
        ),
    )

    # Initialize tools
    tools = {
        "FindSymbolTool": agent.get_tool(FindSymbolTool),
        "FindReferencingSymbolsTool": agent.get_tool(FindReferencingSymbolsTool),
        "FindFileTool": agent.get_tool(FindFileTool),
        "SearchForPatternTool": agent.get_tool(SearchForPatternTool),
        "GetSymbolsOverviewTool": agent.get_tool(GetSymbolsOverviewTool),
    }

    print("Serena agent initialized successfully!")

    # Main interactive loop
    while True:
        try:
            tools_info = display_available_tools()
            choice = input("\nSelect a tool (1-5) or 'q' to quit: ").strip().lower()

            if choice == "q":
                print("Goodbye!")
                break

            if choice not in tools_info:
                print("Invalid choice. Please select 1-5 or 'q'.")
                continue

            tool_name = tools_info[choice][0]
            tool_instance = tools[tool_name]

            print(f"\n=== {tool_name} ===")
            args = get_tool_arguments(tool_name)

            print(f"Executing {tool_name} with arguments: {args}")
            execute_tool(agent, tool_name, tool_instance, args)

            input("\nPress Enter to continue...")

        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
        except Exception as e:
            print(f"An error occurred: {e}")
            input("Press Enter to continue...")
