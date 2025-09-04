"""Tests for automatic runtimeconfig.json generation logic in CSharpLanguageServer.

These validate that:
 1. A runtimeconfig is generated when missing (default behavior).
 2. Dry-run mode logs intent but does not create the file.
 3. Generation can be disabled via env var.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings


class CapturingLogger(LanguageServerLogger):  # minimal capture helper
    def __init__(self):  # type: ignore[override]
        super().__init__()
        self.messages: list[tuple[str, int]] = []

    def log(self, message: str, level: int, sanitized_error_message: str = "", stacklevel: int = 2):  # type: ignore[override]
        self.messages.append((message, level))
        super().log(message, level, sanitized_error_message=sanitized_error_message, stacklevel=stacklevel)


def _make_fake_layout(tmp_path: Path):
    """Create a fake dotnet + server layout and return (dotnet_exe, server_dll)."""
    dotnet_dir = tmp_path / "dotnet-sdk-9.0.304"
    dotnet_dir.mkdir(parents=True, exist_ok=True)
    (dotnet_dir / "shared" / "Microsoft.NETCore.App" / "9.0.1").mkdir(parents=True, exist_ok=True)
    dotnet_exe = dotnet_dir / ("dotnet.exe" if os.name == "nt" else "dotnet")
    dotnet_exe.write_text("stub")

    server_dir = tmp_path / "Microsoft.CodeAnalysis.LanguageServer.win-x64.5.0.0-1.25329.6"
    server_dir.mkdir(parents=True, exist_ok=True)
    server_dll = server_dir / "Microsoft.CodeAnalysis.LanguageServer.dll"
    server_dll.write_text("stubdll")
    # Provide minimal deps file so TFM inference triggers
    deps = {"targets": {"net9.0/win-x64": {}}}
    (server_dir / "Microsoft.CodeAnalysis.LanguageServer.deps.json").write_text(json.dumps(deps))
    return dotnet_exe, server_dll


@pytest.fixture
def common(tmp_path, monkeypatch):
    """Setup shared fake layout + patched ensure_server_installed returning our stub paths."""
    dotnet_exe, server_dll = _make_fake_layout(tmp_path)
    cfg = LanguageServerConfig(code_language=Language.CSHARP)  # actual value not used by patched base init
    settings = SolidLSPSettings(solidlsp_dir=str(tmp_path / ".serena"))
    logger = CapturingLogger()
    with patch.object(CSharpLanguageServer, "_ensure_server_installed", return_value=(str(dotnet_exe), str(server_dll))):
        with patch("solidlsp.language_servers.csharp_language_server.SolidLanguageServer.__init__", return_value=None):
            yield {
                "tmp_path": tmp_path,
                "server_dir": server_dll.parent,
                "dotnet_dir": dotnet_exe.parent,
                "cfg": cfg,
                "settings": settings,
                "logger": logger,
            }


def test_runtimeconfig_generated_by_default(common, monkeypatch):
    env_backup = {k: os.environ.get(k) for k in ["CSHARP_LS_GENERATE_RUNTIME_CONFIG", "CSHARP_LS_GENERATE_RUNTIME_CONFIG_DRY_RUN"]}
    try:
        # Ensure defaults (generation enabled, not dry run)
        os.environ.pop("CSHARP_LS_GENERATE_RUNTIME_CONFIG", None)
        os.environ.pop("CSHARP_LS_GENERATE_RUNTIME_CONFIG_DRY_RUN", None)
        CSharpLanguageServer(common["cfg"], common["logger"], str(common["tmp_path"] / "ws"), common["settings"])
        runtimeconfig = common["server_dir"] / "Microsoft.CodeAnalysis.LanguageServer.runtimeconfig.json"
        assert runtimeconfig.exists(), "runtimeconfig should be generated when missing by default"
        data = json.loads(runtimeconfig.read_text())
        assert data.get("runtimeOptions", {}).get("tfm") == "net9.0"
        assert data["runtimeOptions"]["framework"]["name"] == "Microsoft.NETCore.App"
    finally:
        for k, v in env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_runtimeconfig_dry_run(common):
    env_backup = {k: os.environ.get(k) for k in ["CSHARP_LS_GENERATE_RUNTIME_CONFIG", "CSHARP_LS_GENERATE_RUNTIME_CONFIG_DRY_RUN"]}
    try:
        os.environ["CSHARP_LS_GENERATE_RUNTIME_CONFIG"] = "1"
        os.environ["CSHARP_LS_GENERATE_RUNTIME_CONFIG_DRY_RUN"] = "1"
        CSharpLanguageServer(common["cfg"], common["logger"], str(common["tmp_path"] / "ws2"), common["settings"])
        runtimeconfig = common["server_dir"] / "Microsoft.CodeAnalysis.LanguageServer.runtimeconfig.json"
        assert not runtimeconfig.exists(), "Dry run should not write runtimeconfig file"
        assert any("(DryRun) Would generate runtimeconfig" in m for m, _ in common["logger"].messages)
    finally:
        for k, v in env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_runtimeconfig_generation_disabled(common):
    env_backup = {k: os.environ.get(k) for k in ["CSHARP_LS_GENERATE_RUNTIME_CONFIG", "CSHARP_LS_GENERATE_RUNTIME_CONFIG_DRY_RUN"]}
    try:
        os.environ["CSHARP_LS_GENERATE_RUNTIME_CONFIG"] = "0"
        CSharpLanguageServer(common["cfg"], common["logger"], str(common["tmp_path"] / "ws3"), common["settings"])
        runtimeconfig = common["server_dir"] / "Microsoft.CodeAnalysis.LanguageServer.runtimeconfig.json"
        assert not runtimeconfig.exists(), "Generation disabled should not create runtimeconfig"
        # Should have logged missing runtimeconfig warning
        assert any("RuntimeConfig missing" in m for m, _ in common["logger"].messages)
    finally:
        for k, v in env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
