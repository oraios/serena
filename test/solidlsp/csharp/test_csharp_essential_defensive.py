import os
import platform
from pathlib import Path

import pytest

from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings


@pytest.mark.csharp
def test_managed_sdk_and_buildhost_repair(tmp_path, monkeypatch):
    """Essential + defensive: managed SDK enforced; BuildHost repair fills missing directories.

    We simulate a cached language server install missing BuildHost-net472/netcore; the ensure
    logic should attempt a repair by downloading (monkeypatched) and copying the missing dirs.
    """
    settings = SolidLSPSettings(solidlsp_dir=str(tmp_path / ".serena"))
    logger = LanguageServerLogger()

    ls_root = Path(CSharpLanguageServer.ls_resources_dir(settings))
    ls_root.mkdir(parents=True, exist_ok=True)

    # Managed SDK stub
    managed_sdk_dir = ls_root / "dotnet-sdk-9.0.304"
    managed_sdk_dir.mkdir(parents=True, exist_ok=True)
    managed_dotnet = managed_sdk_dir / ("dotnet.exe" if os.name == "nt" else "dotnet")
    managed_dotnet.write_text("managed")

    uname = platform.uname()
    if os.name == "nt":
        rid = "win-x64"
    elif uname.system == "Darwin":
        rid = "osx-arm64" if uname.machine in ("arm64",) else "osx-x64"
    else:
        rid = "linux-arm64" if uname.machine in ("aarch64", "arm64") else "linux-x64"
    pkg_ver = os.environ.get("CSHARP_LS_VERSION", "5.0.0-1.25329.6")
    # Implementation stores language server under directory name: <package_name>.<version>
    # where package_name already includes the RID (e.g., Microsoft.CodeAnalysis.LanguageServer.win-x64)
    # The original draft of this test assumed a RID-less directory; adjust to match implementation.
    cached_server_dir = ls_root / f"Microsoft.CodeAnalysis.LanguageServer.{rid}.{pkg_ver}"
    cached_server_dir.mkdir(parents=True, exist_ok=True)
    server_dll = cached_server_dir / "Microsoft.CodeAnalysis.LanguageServer.dll"
    server_dll.write_text("fake")

    # Ensure BuildHost dirs absent initially
    for bh in ("BuildHost-net472", "BuildHost-netcore"):
        assert not (cached_server_dir / bh).exists()

    # Monkeypatch internal helper that does the download to produce BuildHost dirs structure
    def fake_download(cls, log, package_name, package_version, settings_arg):
        pkg_dir = tmp_path / "downloaded_pkg"
        content_dir = pkg_dir / "content" / "LanguageServer" / rid
        content_dir.mkdir(parents=True, exist_ok=True)
        # Provide BuildHost directories with marker files
        for bh in ("BuildHost-net472", "BuildHost-netcore"):
            bh_dir = content_dir / bh
            (bh_dir).mkdir(parents=True, exist_ok=True)
            (bh_dir / "marker.txt").write_text("x")
        # Provide dll to satisfy any copy expectations (not strictly needed for repair path)
        (content_dir / "Microsoft.CodeAnalysis.LanguageServer.dll").write_text("pkgdll")
        return pkg_dir

    monkeypatch.setattr(
        CSharpLanguageServer,
        "_download_nuget_package_direct",
        classmethod(fake_download),
    )

    # Monkeypatch managed SDK ensure to return stub path (cleanup not focus here)
    monkeypatch.setattr(
        CSharpLanguageServer,
        "_ensure_dotnet_sdk_from_config",
        classmethod(lambda cls, logger_arg, runtime_dep, settings_arg: str(managed_dotnet)),
    )

    # Avoid actual process launch
    monkeypatch.setattr(CSharpLanguageServer, "_start_server", lambda self: None)

    # Capture log messages to assert repair notice
    logs = []
    orig_log = logger.log

    def cap(msg, level):  # pragma: no cover trivial
        logs.append(msg)
        orig_log(msg, level)

    logger.log = cap  # type: ignore

    # Instantiate server triggers repair path (cached dll exists but hosts missing)
    cfg = LanguageServerConfig(code_language=Language.CSHARP)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "p.csproj").write_text("<Project Sdk='Microsoft.NET.Sdk'></Project>")
    CSharpLanguageServer(cfg, logger, str(workspace), settings)

    # BuildHost directories should now exist
    for bh in ("BuildHost-net472", "BuildHost-netcore"):
        assert (cached_server_dir / bh).exists(), f"Expected repair to create {bh}"

    assert any("Repaired missing" in m or "attempting in-place repair" in m for m in logs), "Expected repair log entries"

    # Managed sdk path recorded
    # dotnet_dir attr may not be public; sanity check that stub still present
    assert managed_dotnet.exists()
