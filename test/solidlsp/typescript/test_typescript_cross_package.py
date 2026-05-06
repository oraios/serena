"""Tests for cross-package TypeScript references using additional_workspace_folders."""

from pathlib import Path

import pytest

from solidlsp.ls_config import Language
from test.conftest import start_ls_context

CROSS_PKG_DIR = Path(__file__).parent.parent.parent / "resources" / "repos" / "typescript"
PACKAGE_A = str(CROSS_PKG_DIR / "cross_package_a")
PACKAGE_B = str(CROSS_PKG_DIR / "cross_package_b")


@pytest.mark.typescript
class TestCrossPackageReferences:
    """Verify that find_referencing_symbols works across package boundaries
    when additional_workspace_folders is configured.
    """

    def test_cross_package_find_references(self) -> None:
        """Starting from package_a, with package_b as additional workspace,
        references in package_b should be discovered.
        """
        with start_ls_context(
            Language.TYPESCRIPT,
            repo_path=PACKAGE_A,
            additional_workspace_folders=[PACKAGE_B],
        ) as ls:
            symbols = ls.request_document_symbols("shared_utils.ts").get_all_symbols_and_roots()
            shared_fn = None
            for sym in symbols[0]:
                if sym.get("name") == "sharedUtilityFunction":
                    shared_fn = sym
                    break
            assert shared_fn is not None, "Could not find 'sharedUtilityFunction' in shared_utils.ts"

            sel_start = shared_fn["selectionRange"]["start"]
            refs = ls.request_references("shared_utils.ts", sel_start["line"], sel_start["character"])

            ref_paths = [r.get("relativePath", "") for r in refs]
            cross_package_refs = [p for p in ref_paths if "cross_package_b" in p or "consumer.ts" in p]
            assert len(cross_package_refs) > 0, (
                f"Expected cross-package reference from package_b/consumer.ts, but only found refs in: {ref_paths}"
            )

    def test_cross_package_referencing_symbols(self) -> None:
        """Test the higher-level request_referencing_symbols across packages."""
        with start_ls_context(
            Language.TYPESCRIPT,
            repo_path=PACKAGE_A,
            additional_workspace_folders=[PACKAGE_B],
        ) as ls:
            symbols = ls.request_document_symbols("shared_utils.ts").get_all_symbols_and_roots()
            shared_class = None
            for sym in symbols[0]:
                if sym.get("name") == "SharedClass":
                    shared_class = sym
                    break
            assert shared_class is not None, "Could not find 'SharedClass' in shared_utils.ts"

            sel_start = shared_class["selectionRange"]["start"]
            ref_symbols = ls.request_referencing_symbols(
                "shared_utils.ts",
                sel_start["line"],
                sel_start["character"],
                include_imports=True,
                include_file_symbols=True,
            )

            ref_files = [
                r.symbol["location"]["relativePath"]
                for r in ref_symbols
                if "location" in r.symbol and "relativePath" in r.symbol["location"]
            ]
            cross_refs = [p for p in ref_files if "cross_package_b" in p or "consumer.ts" in p]
            assert len(cross_refs) > 0, f"Expected cross-package referencing symbol from package_b, but only found refs in: {ref_files}"

    def test_without_additional_workspace_no_cross_refs(self) -> None:
        """Baseline: without additional_workspace_folders, cross-package refs should NOT appear."""
        with start_ls_context(
            Language.TYPESCRIPT,
            repo_path=PACKAGE_A,
        ) as ls:
            symbols = ls.request_document_symbols("shared_utils.ts").get_all_symbols_and_roots()
            shared_fn = None
            for sym in symbols[0]:
                if sym.get("name") == "sharedUtilityFunction":
                    shared_fn = sym
                    break
            assert shared_fn is not None

            sel_start = shared_fn["selectionRange"]["start"]
            refs = ls.request_references("shared_utils.ts", sel_start["line"], sel_start["character"])
            ref_paths = [r.get("relativePath", "") for r in refs]
            cross_package_refs = [p for p in ref_paths if "cross_package_b" in p or "consumer.ts" in p]
            assert len(cross_package_refs) == 0, (
                f"Without additional_workspace_folders, should NOT find cross-package refs, but found: {cross_package_refs}"
            )
