#!/usr/bin/env python3
"""Test if the Lean 4 reference fix works."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings
from test.conftest import get_repo_path


def test_fix():
    repo_path = get_repo_path(Language.LEAN4)
    basic_lean_path = str(repo_path / "Serena" / "Basic.lean")
    
    config = LanguageServerConfig(code_language=Language.LEAN4)
    logger = LanguageServerLogger(Language.LEAN4.name)
    settings = SolidLSPSettings()
    
    language_server = SolidLanguageServer.create(config, logger, str(repo_path), solidlsp_settings=settings)
    language_server.start()
    
    try:
        with language_server.open_file(basic_lean_path):
            import time
            print("Waiting for file to be indexed...")
            time.sleep(2)
            
            print("Testing request_references with column 0 (should trigger fix):")
            # Try with relative path instead of absolute
            refs = language_server.request_references("Serena/Basic.lean", 7, 0)
            print(f"  Found {len(refs)} references")
            
            if refs:
                print("  References:")
                for ref in refs[:3]:  # First 3
                    print(f"    {ref['uri'].split('/')[-1]} line {ref['range']['start']['line']+1}")
    finally:
        language_server.stop()


if __name__ == "__main__":
    test_fix()