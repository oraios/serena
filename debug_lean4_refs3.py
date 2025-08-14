#!/usr/bin/env python3
"""Debug script to trace Lean 4 reference finding step by step."""

import json
import logging
import os
import sys
from pathlib import Path

# Add serena to path
sys.path.insert(0, str(Path(__file__).parent))

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings
from serena.symbol import LanguageServerSymbolRetriever
from test.conftest import get_repo_path

# Enable debug logging
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s - %(message)s")


def debug_lean4_references():
    """Debug Lean 4 reference finding in detail."""
    repo_path = get_repo_path(Language.LEAN4)
    basic_lean_path = str(repo_path / "Serena" / "Basic.lean")

    # Create language server
    config = LanguageServerConfig(code_language=Language.LEAN4)
    logger = LanguageServerLogger(Language.LEAN4.name)
    settings = SolidLSPSettings()

    language_server = SolidLanguageServer.create(config, logger, str(repo_path), solidlsp_settings=settings)
    language_server.start()

    try:
        # Open file
        with language_server.open_file(basic_lean_path):
            # Create symbol retriever
            retriever = LanguageServerSymbolRetriever(language_server)

            print("=== Step 1: Find Calculator symbol ===")
            symbols = retriever.find_by_name("Calculator", within_relative_path="Serena/Basic.lean")
            print(f"Found {len(symbols)} symbols")

            if symbols:
                calc_symbol = symbols[0]
                print(f"  Symbol: {calc_symbol.name} at {calc_symbol.location}")
                print(f"  Location details:")
                print(f"    relative_path: {calc_symbol.location.relative_path}")
                print(f"    line: {calc_symbol.location.line}")
                print(f"    column: {calc_symbol.location.column}")
                # Check all attributes
                print(f"    All location attributes: {dir(calc_symbol.location)}")

                print("\n=== Step 2: Find references using symbol location ===")
                refs = retriever.find_referencing_symbols_by_location(calc_symbol.location)
                print(f"Found {len(refs)} references by location")

                print("\n=== Step 3: Direct LSP request at different positions ===")
                # Try the actual line where Calculator is defined (line 8, 0-indexed 7)
                for col in [0, 5, 10, 15, 20]:
                    refs = language_server.request_references(basic_lean_path, 7, col)
                    print(f"  Line 8, col {col}: {len(refs)} references")

                print("\n=== Step 4: Check what column the symbol location is using ===")
                # The issue might be that the .ilean file doesn't provide accurate column info
                if calc_symbol.location.column is not None:
                    print(f"  Symbol location column: {calc_symbol.location.column}")
                    refs = language_server.request_references(basic_lean_path, calc_symbol.location.line or 7, calc_symbol.location.column)
                    print(f"  References at symbol's location: {len(refs)}")
    finally:
        language_server.stop()


if __name__ == "__main__":
    debug_lean4_references()
