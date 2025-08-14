#!/usr/bin/env python3
"""Debug script to understand Lean 4 reference finding behavior."""

import json
import os
import sys
from pathlib import Path

# Add serena to path
sys.path.insert(0, str(Path(__file__).parent))

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings
from test.conftest import get_repo_path


def debug_lean4_references():
    """Debug Lean 4 reference finding."""
    repo_path = get_repo_path(Language.LEAN4)
    basic_lean_path = str(repo_path / "Serena" / "Basic.lean")
    logic_lean_path = str(repo_path / "Serena" / "Logic.lean")
    main_lean_path = str(repo_path / "Main.lean")

    # Create language server
    config = LanguageServerConfig(code_language=Language.LEAN4)
    logger = LanguageServerLogger(Language.LEAN4.name)
    settings = SolidLSPSettings()

    language_server = SolidLanguageServer.create(config, logger, str(repo_path), solidlsp_settings=settings)
    language_server.start()

    try:
        # Open files
        with (
            language_server.open_file(basic_lean_path),
            language_server.open_file(logic_lean_path),
            language_server.open_file(main_lean_path),
        ):
            # Wait a bit for files to be indexed
            import time

            time.sleep(1)

            print("=== Testing references for Calculator structure ===")
            # Line 8: structure Calculator where
            refs = language_server.request_references(basic_lean_path, 7, 10)  # 0-indexed
            print(f"References from Calculator definition: {len(refs)} found")
            for i, ref in enumerate(refs):
                print(f"  {i + 1}. {ref['uri'].split('/')[-1]} line {ref['range']['start']['line'] + 1}")

            print("\n=== Testing references for Calculator.add ===")
            # Line 12: def Calculator.add
            refs = language_server.request_references(basic_lean_path, 11, 4)  # 0-indexed
            print(f"References from Calculator.add: {len(refs)} found")
            for i, ref in enumerate(refs):
                print(f"  {i + 1}. {ref['uri'].split('/')[-1]} line {ref['range']['start']['line'] + 1}")

            print("\n=== Testing references from usage in Main.lean ===")
            # Line 13 in Main.lean: let calc := Calculator.new
            refs = language_server.request_references(main_lean_path, 12, 20)  # 0-indexed, on 'Calculator'
            print(f"References from Calculator usage in Main.lean: {len(refs)} found")
            for i, ref in enumerate(refs):
                print(f"  {i + 1}. {ref['uri'].split('/')[-1]} line {ref['range']['start']['line'] + 1}")

            print("\n=== Testing document symbols in Basic.lean ===")
            symbols = language_server.request_document_symbols(basic_lean_path)
            print(f"Document symbols: {len(symbols)} found")
            if symbols:
                # Check what type symbols is
                print(f"Symbols type: {type(symbols)}, first element type: {type(symbols[0])}")
                for i, sym in enumerate(symbols[:5]):  # First 5
                    if isinstance(sym, dict):
                        print(f"  {i + 1}. {sym.get('name', 'NO NAME')} ({sym.get('kind', 'NO KIND')})")
                    else:
                        print(f"  {i + 1}. {sym}")

            print("\n=== Checking what's at line 8 in Basic.lean (Calculator definition) ===")
            # Try different column positions to see what works
            for col in [0, 5, 10, 15]:
                refs = language_server.request_references(basic_lean_path, 7, col)  # 0-indexed
                print(f"  Column {col}: {len(refs)} references")
    finally:
        language_server.stop()


if __name__ == "__main__":
    debug_lean4_references()
