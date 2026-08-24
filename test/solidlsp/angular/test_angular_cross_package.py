"""Cross-package Angular references via ``additional_workspace_folders``.

``cross_package_lib`` sits outside the Angular app and implements the app's ``Greeter``
interface. ngserver loads projects lazily, per opened document, so references from the app
into that package only appear once the extra workspace folder has been activated by opening
a file in it — which is what ``_activate_additional_workspaces`` does at startup.
"""

from pathlib import Path

import pytest

from serena.util.text_utils import find_text_coordinates
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.conftest import start_ls_context
from test.solidlsp.conftest import read_repo_file

ANGULAR_REPOS_DIR = Path(__file__).parent.parent.parent / "resources" / "repos" / "angular"
APP = str(ANGULAR_REPOS_DIR / "test_repo")
LIB = str(ANGULAR_REPOS_DIR / "cross_package_lib")

INTERFACE_FILE = "src/app/greeter.interface.ts"


def _greeter_interface_refs(ls: SolidLanguageServer) -> list[str]:
    coords = find_text_coordinates(read_repo_file(ls, INTERFACE_FILE), r"interface (Greeter)")
    assert coords is not None, "Could not locate the Greeter interface declaration"
    refs = ls.request_references(INTERFACE_FILE, coords.line, coords.col + 1)
    return [r.get("relativePath", "") for r in refs]


@pytest.mark.angular
class TestAngularCrossPackageReferences:
    def test_references_reach_additional_workspace_folder(self) -> None:
        with start_ls_context(LanguageServerId.ANGULAR, repo_path=APP, additional_workspace_folders=[LIB]) as ls:
            ref_paths = _greeter_interface_refs(ls)
        assert any("external-greeter.ts" in p for p in ref_paths), (
            f"Expected a reference from the additional workspace folder, got: {ref_paths}"
        )

    def test_referencing_symbols_reach_additional_workspace_folder(self) -> None:
        """The `find_referencing_symbols` path: the symbol containing the reference has to be read
        back out of the external file, which only works if the companion TS server was configured
        with the same workspace folders as ngserver.
        """
        with start_ls_context(LanguageServerId.ANGULAR, repo_path=APP, additional_workspace_folders=[LIB]) as ls:
            coords = find_text_coordinates(read_repo_file(ls, INTERFACE_FILE), r"interface (Greeter)")
            assert coords is not None
            referencing = ls.request_referencing_symbols(INTERFACE_FILE, coords.line, coords.col + 1, include_imports=True)
            names = {r.symbol.get("name") for r in referencing}
        assert "ExternalGreeter" in names, f"Expected the implementing class from the extra package, got: {names}"

    def test_no_cross_package_references_without_additional_workspace_folder(self) -> None:
        """Baseline: the extra folder is invisible unless it is configured."""
        with start_ls_context(LanguageServerId.ANGULAR, repo_path=APP) as ls:
            ref_paths = _greeter_interface_refs(ls)
        assert not any("external-greeter.ts" in p for p in ref_paths), (
            f"Did not expect references outside the app workspace, got: {ref_paths}"
        )
