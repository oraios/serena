"""
Regression tests covering runtime dependency setup logic for the GDScript language server.
"""

import os
import pathlib

from solidlsp.language_servers.gdscript_language_server import GDScriptLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import FileUtils, PlatformId, PlatformUtils
from solidlsp.settings import SolidLSPSettings


def test_setup_runtime_dependencies_extracts_zip_on_macos(monkeypatch, tmp_path):
    """Ensure macOS runtime extraction uses archive unpacking and fallback copy if symlinks fail."""
    # Force environment to simulate macOS and no pre-installed Godot.
    monkeypatch.setattr(GDScriptLanguageServer, "_get_gdscript_lsp_path", staticmethod(lambda: None))
    monkeypatch.setattr(PlatformUtils, "get_platform_id", lambda: PlatformId.OSX_x64)

    download_calls: list[tuple[str, str, str]] = []

    def fake_download(logger, url: str, target_path: str, archive_type: str) -> None:
        download_calls.append((url, target_path, archive_type))
        target = pathlib.Path(target_path)
        target.mkdir(parents=True, exist_ok=True)
        binary = target / "Godot.app" / "Contents" / "MacOS" / "Godot"
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_bytes(b"binary-data")

    monkeypatch.setattr(FileUtils, "download_and_extract_archive", fake_download)

    # Force the symlink creation path to exercise the copy fallback branch on systems without symlink support.
    def fail_symlink(*_args, **_kwargs):
        raise OSError("symlinks disabled")

    monkeypatch.setattr(os, "symlink", fail_symlink)

    solidlsp_dir = tmp_path / "solidlsp"
    settings = SolidLSPSettings(solidlsp_dir=str(solidlsp_dir), project_data_relative_path=".serena")
    config = LanguageServerConfig(code_language=Language.GDSCRIPT)
    logger = LanguageServerLogger()

    resolved_path = pathlib.Path(GDScriptLanguageServer._setup_runtime_dependencies(logger, config, settings))  # type: ignore[arg-type]

    expected_godot_dir = pathlib.Path(settings.ls_resources_dir) / "GDScriptLanguageServer" / "godot"
    expected_binary_path = expected_godot_dir / "Godot.app" / "Contents" / "MacOS" / "Godot"

    assert download_calls and download_calls[0][2] == "zip"
    assert expected_binary_path.exists(), "Binary from fake download should exist after extraction."
    assert resolved_path.exists(), "Executable path should have been created."
    assert resolved_path.read_bytes() == expected_binary_path.read_bytes()
