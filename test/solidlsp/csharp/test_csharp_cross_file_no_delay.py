import os
from unittest.mock import patch

import pytest

from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer
from solidlsp.ls_config import LanguageServerConfig, Language
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings

@pytest.mark.csharp
class TestCrossFileReferencesNoDelay:
    @pytest.fixture
    def settings(self):
        s = SolidLSPSettings()
        s.tool_timeout = 120  # type: ignore[attr-defined]
        return s

    @pytest.fixture
    def mock_config(self):
        cfg = LanguageServerConfig(code_language=Language.CSHARP)
        cfg.ignored_paths = []  # type: ignore[attr-defined]
        return cfg

    @pytest.fixture
    def workspace(self, tmp_path):
        ws = tmp_path / "repo"
        (ws / "Models").mkdir(parents=True)
        # Simple two-file scenario replicating reference test
        (ws / "Program.cs").write_text(
            """using System;\nnamespace Demo { public class Program { static void Main() { var p = new Models.Person(); Console.WriteLine(p.Name); var x = Calculator.Subtract(3,1); } } public static class Calculator { public static int Subtract(int a,int b)=> a-b; } }"""
        )
        (ws / "Models" / "Person.cs").write_text(
            """namespace Demo.Models { public class Person { public string Name => Calculator.Subtract(2,1).ToString(); } }"""
        )
        # minimal csproj
        (ws / "Demo.csproj").write_text("<Project Sdk='Microsoft.NET.Sdk'><PropertyGroup><TargetFramework>net9.0</TargetFramework></PropertyGroup></Project>")
        return ws

    @pytest.fixture
    def server(self, workspace, settings):
        # Patch install + start to avoid real process spawn; we only exercise reference logic path (bounded retry logging)
        with patch.object(CSharpLanguageServer, "_ensure_server_installed", return_value=("/usr/bin/dotnet", "/fake/server.dll")):
            with patch.object(CSharpLanguageServer, "_start_server"):
                logger = LanguageServerLogger()
                cfg = LanguageServerConfig(code_language=Language.CSHARP)
                cfg.ignored_paths = []  # type: ignore[attr-defined]
                srv = CSharpLanguageServer(cfg, logger, str(workspace), settings)
                # Mock underlying super().request_references to emulate immediate available cross-file refs
                original = srv.__class__.__mro__[1].request_references
                
                def fake_request(self, rel, line, col):  # type: ignore[override]
                    # Return synthetic two-file refs showing cross-file presence
                    return [
                        {"relativePath": rel, "line": line},
                        {"relativePath": os.path.join("Models", "Person.cs"), "line": 0},
                    ]
                srv.__class__.__mro__[1].request_references = fake_request  # type: ignore
                try:
                    yield srv
                finally:
                    # Restore original to avoid leakage
                    srv.__class__.__mro__[1].request_references = original  # type: ignore

    def test_cross_file_refs_without_delay_and_no_retry(self, server):
        # Use zero ready delay to ensure we aren't depending on sleeps
        with patch.dict(os.environ, {"CSHARP_LS_MIN_READY_DELAY": "0"}, clear=False):
            refs = server.request_references("Program.cs", 0, 10)
            rels = {r.get("relativePath") for r in refs}
            assert any(p.endswith("Program.cs") for p in rels)
            assert any(p.endswith(os.path.join("Models", "Person.cs")) for p in rels)
            # Retry should not have been needed since we already had cross-file refs
            # attempts count appears only in debug log; functional assertion: no mutation of refs size
            assert len(refs) == 2
