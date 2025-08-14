#!/usr/bin/env python3
"""Final debug to confirm the line number issue."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings
from test.conftest import get_repo_path


def main():
    repo_path = get_repo_path(Language.LEAN4)
    basic_lean_path = str(repo_path / "Serena" / "Basic.lean")

    config = LanguageServerConfig(code_language=Language.LEAN4)
    logger = LanguageServerLogger(Language.LEAN4.name)
    settings = SolidLSPSettings()

    language_server = SolidLanguageServer.create(config, logger, str(repo_path), solidlsp_settings=settings)
    language_server.start()

    try:
        with language_server.open_file(basic_lean_path):
            print("=== Checking document symbols ===")
            symbols = language_server.request_document_symbols(basic_lean_path)

            # Find Calculator symbol
            calc_sym = None
            for sym_list in symbols:
                for sym in sym_list:
                    if sym.get("name") == "Calculator":
                        calc_sym = sym
                        break

            if calc_sym:
                print(f"Calculator symbol found:")
                print(f"  Range: line {calc_sym['range']['start']['line']}, col {calc_sym['range']['start']['character']} (0-indexed)")
                print(
                    f"  Location: line {calc_sym['location']['range']['start']['line']}, col {calc_sym['location']['range']['start']['character']} (0-indexed)"
                )

                # Now test references at the correct line
                print("\n=== Testing references at corrected line ===")
                # The symbol says line 6, but we know it's actually line 7
                correct_line = 7
                col = calc_sym["range"]["start"]["character"]

                refs = language_server.request_references(basic_lean_path, correct_line, col)
                print(f"References at line {correct_line}, col {col}: {len(refs)} found")

                # Also test at the line the symbol claims
                claimed_line = calc_sym["range"]["start"]["line"]
                refs2 = language_server.request_references(basic_lean_path, claimed_line, col)
                print(f"References at line {claimed_line}, col {col}: {len(refs2)} found")

    finally:
        language_server.stop()


if __name__ == "__main__":
    main()
