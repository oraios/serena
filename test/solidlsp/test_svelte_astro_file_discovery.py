# SPDX-License-Identifier: MIT
"""Svelte and Astro companion file discovery respects the project's ignore patterns without starting an LSP."""

from pathlib import Path

import pathspec
import pytest

from solidlsp.language_servers.astro_language_server import AstroLanguageServer
from solidlsp.language_servers.svelte_language_server import SvelteLanguageServer
from solidlsp.ls_config import LanguageServerId


class _SvelteDiscoveryServer(SvelteLanguageServer):
    """Minimal discovery server without runtime dependencies or language-server processes."""

    def __init__(self, root: Path, ignored_paths: tuple[str, ...]) -> None:
        self.repository_root_path = self.repo_path = str(root)
        self.ls_id = LanguageServerId.SVELTE
        self._ignore_spec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, ignored_paths)

    def find_files(self) -> list[str]:
        return self._find_all_svelte_files()


class _AstroDiscoveryServer(AstroLanguageServer):
    """Minimal discovery server without runtime dependencies or language-server processes."""

    def __init__(self, root: Path, ignored_paths: tuple[str, ...]) -> None:
        self.repository_root_path = self.repo_path = str(root)
        self.ls_id = LanguageServerId.ASTRO
        self._ignore_spec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, ignored_paths)

    def find_files(self) -> list[str]:
        return self._find_all_astro_files()


SERVERS = [(_SvelteDiscoveryServer, "svelte"), (_AstroDiscoveryServer, "astro")]


@pytest.mark.parametrize(("server_cls", "ext"), SERVERS)
@pytest.mark.parametrize(
    ("ignored_paths", "excluded_dir"),
    [
        (("/dist",), "dist"),
        (("**/vendor/**",), "apps/api/vendor/package"),
        (("src/Generated.*",), None),
        ((), "packages/ui/dist"),
        ((), "apps/web/build"),
        ((), "apps/web/node_modules/package"),
    ],
)
def test_discovery_excludes_ignored_files(
    tmp_path: Path, server_cls: type, ext: str, ignored_paths: tuple[str, ...], excluded_dir: str | None
) -> None:
    excluded_file = f"{excluded_dir}/Button.{ext}" if excluded_dir else f"src/Generated.{ext}"
    for relative_path in (f"src/App.{ext}", excluded_file):
        file_path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("<div />\n")

    server = server_cls(tmp_path, ignored_paths)

    assert server.find_files() == [str(Path(f"src/App.{ext}"))]


@pytest.mark.parametrize(("server_cls", "ext"), SERVERS)
def test_discovery_preserves_reincluded_files(tmp_path: Path, server_cls: type, ext: str) -> None:
    for name in ("Keep", "Skip"):
        file_path = tmp_path / "src" / f"{name}.{ext}"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("<div />\n")

    server = server_cls(tmp_path, (f"src/*.{ext}", f"!src/Keep.{ext}"))

    assert server.find_files() == [str(Path(f"src/Keep.{ext}"))]
