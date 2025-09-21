import os
import shutil
from pathlib import Path

import pytest

from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings


@pytest.mark.csharp
def test_system_dotnet_is_ignored_and_legacy_cleaned(tmp_path, monkeypatch):
    """Regression test: even if a system dotnet is on PATH, the managed SDK is used.

    Also verifies that legacy dotnet-runtime-* directories are removed after ensuring
    the managed SDK (cleanup side-effect).
    """
    settings = SolidLSPSettings(solidlsp_dir=str(tmp_path / ".serena"))
    logger = LanguageServerLogger()

    # Prepare language server resource root
    ls_root = Path(CSharpLanguageServer.ls_resources_dir(settings))
    ls_root.mkdir(parents=True, exist_ok=True)

    # Create a legacy runtime directory that should be cleaned up
    legacy_runtime = ls_root / "dotnet-runtime-8.0.5"
    legacy_runtime.mkdir(parents=True, exist_ok=True)

    # Fake system dotnet path (should be ignored)
    system_dotnet_dir = tmp_path / "system-dotnet"
    system_dotnet_dir.mkdir()
    system_dotnet_path = system_dotnet_dir / ("dotnet.exe" if os.name == "nt" else "dotnet")
    system_dotnet_path.write_text("noop")

    # Managed SDK directory we expect to be used
    managed_sdk_dir = ls_root / "dotnet-sdk-9.0.304"
    managed_sdk_dir.mkdir(parents=True, exist_ok=True)
    managed_dotnet = managed_sdk_dir / ("dotnet.exe" if os.name == "nt" else "dotnet")
    managed_dotnet.write_text("managed")

    # Create fake language server dll directory & dll
    rid = "win-x64" if os.name == "nt" else ("linux-x64" if os.uname().machine in ("x86_64", "amd64") else "linux-arm64")
    pkg_ver = os.environ.get("CSHARP_LS_VERSION", "5.0.0-1.25329.6")
    fake_server_dir = ls_root / f"Microsoft.CodeAnalysis.LanguageServer.{rid}.{pkg_ver}"
    fake_server_dir.mkdir(parents=True, exist_ok=True)
    fake_dll = fake_server_dir / "Microsoft.CodeAnalysis.LanguageServer.dll"
    fake_dll.write_text("fake")

    # Monkeypatch shutil.which to simulate a system dotnet presence
    monkeypatch.setattr(shutil, "which", lambda name: str(system_dotnet_path) if name == "dotnet" else None)

    # Patch the internal install routine to (a) perform legacy cleanup side-effect and (b) return managed path
    def _fake_ensure_from_config(cls, logger_arg, runtime_dep, settings_arg):
        # Simulate cleanup the real function would do
        cls._cleanup_legacy_dotnet_runtimes(logger_arg, settings_arg, preserve_dir=managed_sdk_dir)
        return str(managed_dotnet)

    monkeypatch.setattr(
        CSharpLanguageServer,
        "_ensure_dotnet_sdk_from_config",
        classmethod(_fake_ensure_from_config),
    )
    monkeypatch.setattr(
        CSharpLanguageServer,
        "_ensure_language_server",
        classmethod(lambda cls, logger_arg, dep, settings_arg: str(fake_dll)),
    )
    # Avoid starting a real process
    monkeypatch.setattr(CSharpLanguageServer, "_start_server", lambda self: None)

    # Capture log messages
    logged_messages = []
    orig_log = logger.log

    def capture(msg, level):  # pragma: no cover - trivial wrapper
        logged_messages.append((level, msg))
        orig_log(msg, level)

    logger.log = capture  # type: ignore[assignment]

    # Instantiate server (this triggers dependency ensure logic)
    cfg = LanguageServerConfig(code_language=Language.CSHARP)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "proj.csproj").write_text("<Project Sdk='Microsoft.NET.Sdk'></Project>")
    server = CSharpLanguageServer(cfg, logger, str(workspace), settings)

    # Assertions
    assert server.dotnet_dir == str(managed_sdk_dir), "Managed SDK directory must be used"
    assert legacy_runtime.exists() is False, "Legacy runtime directory should have been cleaned up"
    # Ensure log contains ignore message
    assert any("Ignoring system dotnet" in m for _, m in logged_messages), "Expected log about ignoring system dotnet"

    # Sanity: system path untouched
    assert system_dotnet_path.exists(), "System dotnet placeholder should remain (not modified)"
