"""
Test to prove cross-file references work.
"""

import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.ocaml
class TestCrossFileReferences:
    @pytest.mark.parametrize("language_server", [Language.OCAML], indirect=True)
    def test_fib_has_cross_file_references(self, language_server: SolidLanguageServer) -> None:
        """Test that fib function references are found across multiple files.

        The `fib` function is defined in lib/test_repo.ml and used in:
        - lib/test_repo.ml (definition + 2 recursive calls)
        - bin/main.ml (1 call)
        - test/test_test_repo.ml (5 references)

        Total: 9 references across 3 files.

        This test WILL FAIL if cross-file references aren't working!
        """
        file_path = os.path.join("lib", "test_repo.ml")

        # Find references to `fib` at line 8, char 8 (0-indexed)
        fib_line = 7
        fib_char = 8

        refs = language_server.request_references(file_path, fib_line, fib_char)

        # Get counts per file
        lib_refs = [ref for ref in refs if ref.get("uri", "").endswith(os.path.join("lib", "test_repo.ml"))]
        bin_refs = [ref for ref in refs if ref.get("uri", "").endswith(os.path.join("bin", "main.ml"))]
        test_refs = [ref for ref in refs if ref.get("uri", "").endswith(os.path.join("test", "test_test_repo.ml"))]

        # Print what we got for debugging
        print("\n=== Cross-file references result ===")
        print(f"Total references found: {len(refs)}")
        print(f"  lib/test_repo.ml: {len(lib_refs)}")
        print(f"  bin/main.ml: {len(bin_refs)}")
        print(f"  test/test_test_repo.ml: {len(test_refs)}")

        for ref in refs:
            uri = ref.get("uri", "")
            filename = uri.split("/")[-1]
            line = ref.get("range", {}).get("start", {}).get("line", -1)
            print(f"    {filename}:{line}")

        # ASSERTIONS - These will FAIL without OCaml 5.2+
        assert len(refs) >= 9, (
            f"Expected at least 9 total references (3 in lib + 1 in bin + 5 in test), "
            f"but got {len(refs)}. Cross-file references are NOT working!"
        )

        assert len(lib_refs) >= 3, f"Expected at least 3 references in lib/test_repo.ml (definition + 2 recursive), but got {len(lib_refs)}"

        assert len(bin_refs) >= 1, (
            f"Expected at least 1 reference in bin/main.ml, but got {len(bin_refs)}. "
            "Cross-file references are NOT working - bin/main.ml not found!"
        )

        assert len(test_refs) >= 1, (
            f"Expected at least 1 reference in test/test_test_repo.ml, but got {len(test_refs)}. "
            "Cross-file references are NOT working - test file not found!"
        )

        print("\n=== Cross-file references WORKING! ===")
