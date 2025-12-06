from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.fsharp
class TestFSharpProjectDiscovery:
    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_breadth_first_project_discovery(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """
        Ensure FsAutoComplete is initialized with the repo root and picks up solution/project files.
        """
        assert language_server.is_running()
        # Should have rooted the LS at the repo root (where test_repo lives)
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

        # Verify the project file exists in the repo and is discoverable
        fsproj = repo_path / "TestProject.fsproj"
        assert fsproj.exists(), "Expected test F# project file to exist"

        # Request document symbols from a file to confirm the project was opened
        program_fs = str(repo_path / "src" / "Program.fs")
        symbols = language_server.request_document_symbols(program_fs)
        assert symbols, "Expected symbols from Program.fs after project discovery"

        # Selection range of a type should point at the identifier (not preceding comments)
        calculator_fs = str(repo_path / "src" / "Calculator.fs")
        calculator_symbols = language_server.request_document_symbols(calculator_fs)
        assert calculator_symbols, "Expected symbols from Calculator.fs"
        first = calculator_symbols.root_symbols[0]
        assert first.get("name") == "Calculator"
        sel = first.get("selectionRange")
        assert sel, "Expected selectionRange for Calculator"
        # Line numbers are reported 1-based; the doc comment sits on line 6 in the test file.
        assert sel["start"]["line"] == 6, f"Expected selectionRange to start at line 6, got {sel}"
