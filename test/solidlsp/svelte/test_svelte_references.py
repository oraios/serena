import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId

pytestmark = pytest.mark.svelte


class TestSvelteReferences:
    @pytest.mark.parametrize("language_server", [LanguageServerId.SVELTE], indirect=True)
    def test_references_across_svelte_and_typescript(self, language_server: SolidLanguageServer) -> None:
        refs = language_server.request_references(os.path.join("src", "lib", "components", "Words.svelte"), 1, 17)
        ref_paths = {ref["relativePath"].replace("\\", "/") for ref in refs}  # type: ignore

        assert "src/routes/(sverdle)/words.server.ts" in ref_paths, sorted(ref_paths)
        assert "src/lib/game.ts" in ref_paths, sorted(ref_paths)
        assert "src/routes/(sverdle)/+page.svelte" in ref_paths, sorted(ref_paths)

    @pytest.mark.parametrize("language_server", [LanguageServerId.SVELTE], indirect=True)
    def test_references_from_typescript_file(self, language_server: SolidLanguageServer) -> None:
        refs = language_server.request_references(os.path.join("src", "lib", "game.ts"), 3, 13)
        ref_paths = {ref["relativePath"].replace("\\", "/") for ref in refs}  # type: ignore

        assert "src/routes/(sverdle)/+page.server.ts" in ref_paths, sorted(ref_paths)

    @pytest.mark.parametrize("language_server", [LanguageServerId.SVELTE], indirect=True)
    def test_references_from_typescript_file_exclude_imports_of_other_symbols(self, language_server: SolidLanguageServer) -> None:
        # guards against imports and usages of other symbols of the module being reported as references (#2120);
        # a preceding .svelte request is needed for the svelte LS to answer .ts requests at all
        language_server.request_references(os.path.join("src", "lib", "components", "Words.svelte"), 1, 17)
        refs = language_server.request_references(os.path.join("src", "lib", "roles.ts"), 8, 16)
        ref_paths = {ref["relativePath"].replace("\\", "/") for ref in refs}  # type: ignore

        assert "src/lib/components/RoleList.svelte" in ref_paths, sorted(ref_paths)
        assert "src/lib/components/RoleCheck.svelte" not in ref_paths, sorted(ref_paths)
        assert "src/lib/permissions.ts" not in ref_paths, sorted(ref_paths)
