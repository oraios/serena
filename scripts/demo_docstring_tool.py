"""
This script demonstrates how to use Serena's tools locally, useful
for testing or development. Here the tools will be operating on the serena repo itself.

This demo showcases both traditional symbol finding and the new signature/docstring
retrieval capabilities.
"""

import json

from serena.agent import *
from serena.constants import REPO_ROOT


@dataclass
class InMemorySerenaConfig(SerenaConfigBase):
    """
    In-memory implementation of Serena configuration with the GUI disabled.
    """

    gui_log_window_enabled: bool = False
    web_dashboard: bool = False


def demo_basic_symbol_finding(agent):
    """Demonstrate basic symbol finding without signature/docstring."""
    print("=" * 60)
    print("1. BASIC SYMBOL FINDING")
    print("=" * 60)

    find_tool = agent.get_tool(FindSymbolTool)
    print("Finding symbols named 'SerenaAgent' (basic mode):")
    result = find_tool.apply(name_path="SerenaAgent")
    symbols = json.loads(result)

    for symbol in symbols[:2]:  # Show first 2 results
        print(f"  - {symbol['name_path']} ({symbol['kind']}) in {symbol['relative_path']}")
    print()


def demo_signature_and_docstring_retrieval(agent):
    """Demonstrate new signature and docstring retrieval features."""
    print("=" * 60)
    print("2. SIGNATURE & DOCSTRING RETRIEVAL")
    print("=" * 60)

    find_tool = agent.get_tool(FindSymbolTool)

    # Find symbols with signature and docstring information
    print("Finding symbols with signature and docstring information:")
    result = find_tool.apply(name_path="SerenaAgent/__init__", include_signature=True, include_docstring=True)
    symbols = json.loads(result)

    for symbol in symbols[:1]:  # Show first result in detail
        print(f"\n📍 Symbol: {symbol['name_path']}")
        print(f"   📂 File: {symbol['relative_path']}")
        print(f"   🏷️  Kind: {symbol['kind']}")

        if symbol.get("signature"):
            signature = symbol["signature"]
            print("   ✍️  Signature:")
            # Display multiline signatures with proper indentation
            for line in signature.split("\n"):
                print(f"       {line}")
        else:
            print("   ✍️  Signature: Not available")

        if symbol.get("docstring"):
            # Truncate long docstrings for demo
            docstring = symbol["docstring"]
            if len(docstring) > 200:
                docstring = docstring[:200] + "..."
            print(f"   📝 Documentation: {docstring}")
        else:
            print("   📝 Documentation: Not available")
    print()


def demo_symbols_overview_with_docs(agent):
    """Demonstrate symbols overview with signature/docstring."""
    print("=" * 60)
    print("3. SYMBOLS OVERVIEW WITH DOCUMENTATION")
    print("=" * 60)

    overview_tool = agent.get_tool(GetSymbolsOverviewTool)

    # Get overview of a specific file with signature/docstring
    print("Getting symbols overview for symbol.py with documentation:")
    result = overview_tool.apply(relative_path="src/serena/symbol.py", include_signature=True, include_docstring=True)
    overview = json.loads(result)

    # Show a few symbols from the overview
    file_path = "src/serena/symbol.py"
    if file_path in overview:
        symbols = overview[file_path][:3]  # Show first 3 symbols

        for symbol in symbols:
            print(f"\n🔍 {symbol['name_path']} (Kind: {symbol['kind']})")

            if symbol.get("signature"):
                signature = symbol["signature"]
                if len(signature) > 100:
                    signature = signature[:100] + "..."
                print(f"   ✍️  {signature}")

            if symbol.get("docstring"):
                docstring = symbol["docstring"]
                if len(docstring) > 100:
                    docstring = docstring[:100] + "..."
                print(f"   📝 {docstring}")
    print()


def demo_symbol_references(agent):
    """Demonstrate finding symbol references (existing functionality)."""
    print("=" * 60)
    print("4. SYMBOL REFERENCES (EXISTING FEATURE)")
    print("=" * 60)

    find_refs_tool = agent.get_tool(FindReferencingSymbolsTool)
    print("Finding references to 'SyncLanguageServer':")
    result = find_refs_tool.apply(name_path="SyncLanguageServer", relative_path="src/multilspy/language_server.py")
    references = json.loads(result)

    print(f"Found {len(references)} references:")
    for ref in references[:3]:  # Show first 3 references
        print(f"  - {ref['relative_path']}:{ref.get('line', 'unknown')}")
    print()


if __name__ == "__main__":
    print("🚀 SERENA TOOLS DEMONSTRATION")
    print("Showcasing symbol finding with signature and docstring retrieval")
    print()

    # Initialize agent with the current Serena repository
    agent = SerenaAgent(project=REPO_ROOT, serena_config=InMemorySerenaConfig())

    try:
        # Run demonstration scenarios
        demo_basic_symbol_finding(agent)
        demo_signature_and_docstring_retrieval(agent)
        demo_symbols_overview_with_docs(agent)
        demo_symbol_references(agent)

        print("=" * 60)
        print("✅ DEMONSTRATION COMPLETE")
        print("=" * 60)
        print("The new signature and docstring features provide rich semantic")
        print("information that can help with code understanding and documentation.")

    except Exception as e:
        print(f"❌ Demo failed with error: {e}")
        print("This might happen if the language server is not available or")
        print("if there are issues with the current codebase state.")
