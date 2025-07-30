#!/usr/bin/env python3

"""
Test script to verify bash function detection is working correctly.
"""

import sys
import os
sys.path.insert(0, 'src')

from solidlsp.language_servers.bash_language_server import BashLanguageServer
from solidlsp.ls_config import LanguageServerConfig, Language
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings

def test_bash_function_detection():
    # Setup
    logger = LanguageServerLogger(json_format=False, log_level=20)  # INFO level is 20
    config = LanguageServerConfig(code_language=Language.BASH)
    settings = SolidLSPSettings()
    
    # Create bash language server
    bash_server = BashLanguageServer(
        config=config,
        logger=logger,
        repository_root_path=os.getcwd(),
        solidlsp_settings=settings
    )
    
    # Test the regex-based function detection directly
    functions = bash_server._detect_bash_functions(
        "test/resources/repos/bash/test_repo/main.sh",
        include_body=True
    )
    
    print(f"Detected {len(functions)} functions:")
    for func in functions:
        print(f"  - {func['name']} (kind: {func['kind']}) at line {func['location']['range']['start']['line']}")
        if 'body' in func:
            print(f"    Body preview: {func['body'][:100]}...")
    
    return functions

if __name__ == "__main__":
    functions = test_bash_function_detection()
    if functions:
        print("\n✅ Bash function detection working correctly!")
    else:
        print("\n❌ No functions detected")
