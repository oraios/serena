import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language

pytestmark = pytest.mark.svelte


class TestSvelteReferences:
    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_references_across_svelte_and_typescript(self, language_server: SolidLanguageServer) -> None:
        refs = language_server.request_references(os.path.join("src", "lib", "components", "Words.svelte"), 1, 17)
        ref_paths = {ref["relativePath"].replace("\\", "/") for ref in refs}

        assert "src/routes/(sverdle)/words.server.ts" in ref_paths
        assert "src/lib/game.ts" in ref_paths
        assert "src/routes/(sverdle)/+page.svelte" in ref_paths

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_references_from_typescript_file(self, language_server: SolidLanguageServer) -> None:
        refs = language_server.request_references(os.path.join("src", "lib", "game.ts"), 3, 13)
        ref_paths = {ref["relativePath"].replace("\\", "/") for ref in refs}

        assert "src/routes/(sverdle)/+page.server.ts" in ref_paths
