import os
from pathlib import Path

import pytest

from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings


@pytest.mark.csharp
def test_managed_sdk_enforced(tmp_path, monkeypatch):
    """Managed .NET SDK directory is enforced (no system dotnet use)."""
    settings = SolidLSPSettings(solidlsp_dir=str(tmp_path / ".serena"))
    log = LanguageServerLogger()

    ls_root = Path(CSharpLanguageServer.ls_resources_dir(settings))
    ls_root.mkdir(parents=True, exist_ok=True)

    fake_sdk_dir = ls_root / "dotnet-sdk-9.0.304"
    fake_sdk_dir.mkdir(parents=True, exist_ok=True)
    fake_dotnet = fake_sdk_dir / ("dotnet.exe" if os.name == "nt" else "dotnet")
    fake_dotnet.write_text("noop")

    # Pre-create fake language server dll location
    rid = "win-x64"
    pkg_ver = os.environ.get("CSHARP_LS_VERSION", "5.0.0-1.25329.6")
    fake_server_dir = ls_root / f"Microsoft.CodeAnalysis.LanguageServer.{rid}.{pkg_ver}"
    fake_server_dir.mkdir(parents=True, exist_ok=True)
    fake_dll = fake_server_dir / "Microsoft.CodeAnalysis.LanguageServer.dll"
    fake_dll.write_text("fake")

    monkeypatch.setattr(
        CSharpLanguageServer,
        "_ensure_dotnet_sdk_from_config",
        classmethod(lambda cls, logger_arg, runtime_dep, settings_arg: str(fake_dotnet)),
    )
    monkeypatch.setattr(
        CSharpLanguageServer,
        "_ensure_language_server",
        classmethod(lambda cls, logger_arg, dep, settings_arg: str(fake_dll)),
    )
    monkeypatch.setattr(CSharpLanguageServer, "_start_server", lambda self: None)

    cfg = LanguageServerConfig(code_language=Language.CSHARP)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "dummy.csproj").write_text("<Project Sdk='Microsoft.NET.Sdk'></Project>")

    server = CSharpLanguageServer(cfg, log, str(workspace), settings)

    assert server.dotnet_dir == str(fake_sdk_dir)
    assert fake_dotnet.exists()
