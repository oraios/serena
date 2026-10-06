"""
Unit tests for the removal of outdated Expert installs in ``ElixirTools``.

These tests do not start Expert and do not require Elixir to be installed.
"""

import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from _pytest.logging import LogCaptureFixture

from solidlsp.language_servers.elixir_tools.elixir_tools import ElixirTools
from solidlsp.ls_utils import FileUtils

pytestmark = pytest.mark.elixir

OUTDATED_LINUX_AMD64_SHA256 = "643a492ff972246668b0ca356a84c3d0a0f5feeae0ab5dc1b9a126876ed460e4"


def _make_fake_expert_install(root: Path) -> tuple[Path, Path]:
    expert_dir = root / "expert"
    expert_dir.mkdir()
    binary_path = expert_dir / "expert_linux_amd64"
    binary_path.write_bytes(b"fake expert binary")
    return expert_dir, binary_path


class TestRemoveOutdatedExpertInstall:
    def test_outdated_install_is_removed(self, tmp_path: Path, caplog: LogCaptureFixture) -> None:
        expert_dir, binary_path = _make_fake_expert_install(tmp_path)
        with (
            patch.object(FileUtils, "calculate_sha256", return_value=OUTDATED_LINUX_AMD64_SHA256),
            caplog.at_level(logging.WARNING),
        ):
            ElixirTools._remove_outdated_expert_install(str(expert_dir), str(binary_path))

        assert not expert_dir.exists()
        assert "outdated Expert binary" in caplog.text

    def test_current_install_is_kept(self, tmp_path: Path) -> None:
        expert_dir, binary_path = _make_fake_expert_install(tmp_path)
        ElixirTools._remove_outdated_expert_install(str(expert_dir), str(binary_path))

        assert binary_path.exists()

    def test_missing_install_is_noop(self, tmp_path: Path) -> None:
        expert_dir = tmp_path / "expert"
        ElixirTools._remove_outdated_expert_install(str(expert_dir), str(expert_dir / "expert"))

        assert not expert_dir.exists()
