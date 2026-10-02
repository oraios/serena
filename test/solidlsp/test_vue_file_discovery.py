# SPDX-License-Identifier: MIT
"""Vue companion file discovery respects the project's ignore patterns without starting an LSP."""

from pathlib import Path

import pathspec
import pytest

from solidlsp.language_servers.vue_language_server import VueLanguageServer
from solidlsp.ls_config import LanguageServerId


class _VueDiscoveryServer(VueLanguageServer):
    """Minimal discovery server without runtime dependencies or language-server processes."""

    def __init__(self, root: Path, ignored_paths: tuple[str, ...]) -> None:
        self.repository_root_path = str(root)
        self.ls_id = LanguageServerId.VUE
        self._ignore_spec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, ignored_paths)


@pytest.mark.parametrize(
    ("ignored_paths", "excluded_file"),
    [
        (("library-release-files/*",), "library-release-files/release/package/src/Button.vue"),
        (("**/vendor/**",), "apps/api/vendor/package/Button.vue"),
        (("src/Generated.vue",), "src/Generated.vue"),
        ((), "apps/web/node_modules/package/Button.vue"),
        ((), "apps/web/dist/Button.vue"),
        ((), "apps/web/.nuxt/Button.vue"),
    ],
)
def test_vue_discovery_excludes_ignored_files(tmp_path: Path, ignored_paths: tuple[str, ...], excluded_file: str) -> None:
    # create a source component and an ignored component
    for relative_path in ("src/App.vue", excluded_file):
        file_path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("<template><div /></template>\n")

    server = _VueDiscoveryServer(tmp_path, ignored_paths)

    assert server._find_all_vue_files() == [str(Path("src/App.vue"))]


def test_vue_discovery_preserves_reincluded_files(tmp_path: Path) -> None:
    # create two components with one explicitly included by the ignore patterns
    for name in ("Keep.vue", "Skip.vue"):
        file_path = tmp_path / "src" / name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("<template><div /></template>\n")

    server = _VueDiscoveryServer(tmp_path, ("src/*.vue", "!src/Keep.vue"))

    assert server._find_all_vue_files() == [str(Path("src/Keep.vue"))]
