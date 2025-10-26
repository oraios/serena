#!/usr/bin/env python3
"""Test Serena's Fortran capabilities"""

from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.language_servers.fortran_language_server import FortranLanguageServer
from solidlsp.settings import SolidLSPSettings

# Path to your Fortran project
repo_path = "/home/suvarchal/Downloads/serena/serena/test/resources/repos/fortran/test_repo/"

# Initialize language server
config = LanguageServerConfig(code_language=Language.FORTRAN)
logger = LanguageServerLogger()
settings = SolidLSPSettings()

# Create and start the language server
ls = FortranLanguageServer(config, logger, repo_path, settings)
ls.start()

# Find symbols in a file
all_symbols, root_symbols = ls.request_document_symbols("lib/math_utils.f90")

# Print modules found
modules = [s for s in all_symbols if s.get("kind") == 2]
print(f"Found {len(modules)} modules:")
for mod in modules:
    print(f"  - {mod.get('name')}")

# Print functions/subroutines found
functions = [s for s in all_symbols if s.get("kind") == 12]
print(f"Found {len(functions)} functions/subroutines:")
for func in functions:
    print(f"  - {func.get('name')}")

# Cleanup
ls.stop()
