#!/usr/bin/env python3
"""Manual test of Haskell language server"""
import sys
import logging

# Add src to path
sys.path.insert(0, '/Users/ketema/projects/ametek_chess/submodules/serena/src')

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings

# Configure logging
logging.basicConfig(level=logging.INFO)

# Test repository
repo_path = "test/resources/repos/haskell/test_repo"

# Create language server config
config = LanguageServerConfig(
    code_language=Language.HASKELL,
    ignored_paths=[],
    trace_lsp_communication=False
)

logger = LanguageServerLogger(log_level=logging.INFO)

print(f"Creating Haskell language server for: {repo_path}")

try:
    # Create and start language server
    ls = SolidLanguageServer.create(
        config,
        logger,
        repo_path,
        solidlsp_settings=SolidLSPSettings(
            solidlsp_dir="/Users/ketema/.serena",
            project_data_relative_path=".serena"
        )
    )

    print("Starting language server...")
    ls.start()

    print("\nTest 1: Get symbols from Calculator.hs")
    try:
        symbols, _ = ls.request_document_symbols("src/Calculator.hs")
        symbol_names = [s["name"] for s in symbols]
        print(f"Found symbols: {symbol_names}")

        # Check expected symbols
        expected = ["add", "subtract", "multiply", "divide", "Calculator"]
        for exp in expected:
            if exp in symbol_names:
                print(f"  ✓ Found '{exp}'")
            else:
                print(f"  ✗ Missing '{exp}'")
    except Exception as e:
        print(f"Error getting symbols: {e}")

    print("\nTest 2: Get references to multiply")
    try:
        # multiply is around line 33 (0-indexed: 32)
        refs = ls.request_references("src/Calculator.hs", line=32, column=0)
        print(f"Found {len(refs)} references")
        for ref in refs:
            print(f"  - {ref.get('relativePath', 'unknown')} line {ref.get('range', {}).get('start', {}).get('line', '?')}")
    except Exception as e:
        print(f"Error getting references: {e}")

    print("\nTest 3: Get cross-file references to validateNumber")
    try:
        # validateNumber is on line 8 in Helper.hs (0-indexed: 7)
        refs = ls.request_references("src/Helper.hs", line=7, column=0)
        print(f"Found {len(refs)} references")
        for ref in refs:
            print(f"  - {ref.get('relativePath', 'unknown')} line {ref.get('range', {}).get('start', {}).get('line', '?')}")
    except Exception as e:
        print(f"Error getting cross-file references: {e}")

    print("\nStopping language server...")
    ls.stop()
    print("✓ Test complete!")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
