"""
Tests that Intelephense applies the ``maxFileSize`` setting from ``ls_specific_settings["php"]``.

The tests start a real Intelephense and are therefore gated by the ``php`` marker.
"""

import time
from pathlib import Path

import pytest

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.conftest import start_ls_context


@pytest.mark.php
class TestMaxFileSize:
    MAX_FILE_SIZE = 1000

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

    def test_files_exceeding_max_file_size_not_indexed(self, tmp_path: Path) -> None:
        (tmp_path / "small.php").write_text("<?php\nfunction marker_small() {}\n")
        (tmp_path / "large.php").write_text("<?php\nfunction marker_large() {}\n" + "// padding\n" * self.MAX_FILE_SIZE)

        with start_ls_context(
            LanguageServerId.PHP,
            repo_path=str(tmp_path),
            ls_specific_settings={LanguageServerId.PHP: {"maxFileSize": self.MAX_FILE_SIZE}},
        ) as ls:
            indexed_markers = self._find_indexed_markers(ls, {"marker_small"})

        assert "marker_small" in indexed_markers
        assert "marker_large" not in indexed_markers
