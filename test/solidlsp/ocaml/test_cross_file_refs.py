"""
Test cross-file references for OCaml.

Cross-file references require OCaml >= 5.2 and ocaml-lsp-server >= 1.23.0.
On environments without these (e.g. Windows CI with OCaml 4.14), only
same-file references are asserted.
"""

import logging
import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.language_servers.ocaml_lsp_server import OcamlLanguageServer
from solidlsp.ls_config import Language

log = logging.getLogger(__name__)


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
        """
        file_path = os.path.join("lib", "test_repo.ml")

        fib_line = 7
        fib_char = 8

        refs = language_server.request_references(file_path, fib_line, fib_char)

        lib_refs = [ref for ref in refs if "lib/test_repo.ml" in ref.get("uri", "")]
        bin_refs = [ref for ref in refs if "bin/main.ml" in ref.get("uri", "")]
        test_refs = [ref for ref in refs if "test/test_test_repo.ml" in ref.get("uri", "")]

        log.info("Cross-file references result:")
        log.info(f"Total references found: {len(refs)}")
        log.info(f"  lib/test_repo.ml: {len(lib_refs)}")
        log.info(f"  bin/main.ml: {len(bin_refs)}")
        log.info(f"  test/test_test_repo.ml: {len(test_refs)}")

        for ref in refs:
            uri = ref.get("uri", "")
            filename = uri.split("/")[-1]
            line = ref.get("range", {}).get("start", {}).get("line", -1)
            log.info(f"    {filename}:{line}")

        # Same-file references always work
        assert len(lib_refs) >= 3, f"Expected at least 3 references in lib/test_repo.ml (definition + 2 recursive), but got {len(lib_refs)}"

        # Cross-file references require OCaml >= 5.2 and ocaml-lsp-server >= 1.23.0
        if isinstance(language_server, OcamlLanguageServer) and language_server.supports_cross_file_references:
            assert len(refs) >= 9, (
                f"Expected at least 9 total references (3 in lib + 1 in bin + 5 in test), "
                f"but got {len(refs)}. Cross-file references are NOT working!"
            )

            assert len(bin_refs) >= 1, (
                f"Expected at least 1 reference in bin/main.ml, but got {len(bin_refs)}. "
                "Cross-file references are NOT working - bin/main.ml not found!"
            )

            assert len(test_refs) >= 1, (
                f"Expected at least 1 reference in test/test_test_repo.ml, but got {len(test_refs)}. "
                "Cross-file references are NOT working - test file not found!"
            )
