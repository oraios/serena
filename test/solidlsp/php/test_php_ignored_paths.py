"""
Tests that Intelephense does not index the directories matched by the ignored paths.

Intelephense indexes all PHP files below the repository root on its own, so without exclusions an
ignored directory with a large amount of PHP code (e.g. further checkouts of the repository) is
indexed in full. The tests start a real Intelephense and are therefore gated by the ``php`` marker.
"""

import time
from pathlib import Path

import pytest

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.conftest import start_ls_context


@pytest.mark.php
class TestIgnoredPathsExcludedFromIndex:
    @staticmethod
    def _create_repo(root: Path) -> None:
        for rel_dir_path in ("src", "src/build", "build", "build (old)", "vendor/lib"):
            dir_path = root / rel_dir_path
            dir_path.mkdir(parents=True)
            (dir_path / "functions.php").write_text(f"<?php\nfunction {TestIgnoredPathsExcludedFromIndex._marker(rel_dir_path)}() {{}}\n")
        (root / ".gitignore").write_text("/vendor/\n/build (old)/\n")

    @staticmethod
    def _marker(rel_dir_path: str) -> str:
        return "marker_" + "".join(c if c.isalnum() else "_" for c in rel_dir_path)

    @staticmethod
    def _find_indexed_markers(ls: SolidLanguageServer, expected_markers: set[str]) -> set[str]:
        # the workspace is indexed in the background, so wait until all files expected in the index are present
        indexed_markers: set[str] = set()
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            symbols = ls.server.send.workspace_symbol({"query": "marker_"}) or []
            indexed_markers = {symbol["name"] for symbol in symbols}
            if expected_markers <= indexed_markers:
                break
            time.sleep(1)
        return indexed_markers

    def test_ignored_directories_not_indexed(self, tmp_path: Path) -> None:
        self._create_repo(tmp_path)

        with start_ls_context(LanguageServerId.PHP, repo_path=str(tmp_path), ignored_paths=["/build"]) as ls:
            # vendor is gitignored, yet indexed, because the project's sources depend on its types
            expected_markers = {self._marker("src"), self._marker("src/build"), self._marker("vendor/lib")}
            indexed_markers = self._find_indexed_markers(ls, expected_markers)

        assert expected_markers <= indexed_markers
        assert self._marker("build") not in indexed_markers
        assert self._marker("build (old)") not in indexed_markers
