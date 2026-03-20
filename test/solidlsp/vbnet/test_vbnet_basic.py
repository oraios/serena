import os
import tempfile
from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.language_servers.vbnet_language_server import (
    VBNetLanguageServer,
    breadth_first_file_scan,
    find_solution_or_project_file,
)
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_utils import SymbolUtils
from solidlsp.settings import SolidLSPSettings


@pytest.mark.vbnet
class TestVBNetLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.VBNET], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Module1"), "Module1 not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Calculator"), "Calculator class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Add"), "Add method not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.VBNET], indirect=True)
    def test_get_document_symbols(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("Module1.vb")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        assert len(symbols) > 0

        if isinstance(symbols[0], list):
            symbols = symbols[0]

        names = [s.get("name") for s in symbols]
        assert "Calculator" in names

    @pytest.mark.parametrize("language_server", [Language.VBNET], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("Module1.vb")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        symbol_list = symbols[0] if symbols and isinstance(symbols[0], list) else symbols
        add_symbol = None
        for sym in symbol_list:
            if sym.get("name") == "Add":
                add_symbol = sym
                break
        assert add_symbol is not None, "Could not find 'Add' method symbol in Module1.vb"
        sel_start = add_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"] + 1)
        assert any("Module1.vb" in ref.get("relativePath", "") for ref in refs), "Module1.vb should reference Add method"

    @pytest.mark.parametrize("language_server", [Language.VBNET], indirect=True)
    def test_nested_namespace_symbols(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("Models", "Person.vb")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        assert len(symbols) > 0

        if isinstance(symbols[0], list):
            symbols = symbols[0]

        assert any(s.get("name") == "Person" for s in symbols)

        symbol_names = [s.get("name") for s in symbols]
        assert "Name" in symbol_names, "Name property not found"
        assert "Age" in symbol_names, "Age property not found"
        assert "Email" in symbol_names, "Email property not found"
        assert "ToString" in symbol_names, "ToString method not found"
        assert "IsAdult" in symbol_names, "IsAdult method not found"

    @pytest.mark.parametrize("language_server", [Language.VBNET], indirect=True)
    def test_find_referencing_symbols_across_files(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("Module1.vb")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        symbol_list = symbols[0] if symbols and isinstance(symbols[0], list) else symbols

        subtract_symbol = None
        for sym in symbol_list:
            if sym.get("name") == "Subtract":
                subtract_symbol = sym
                break

        assert subtract_symbol is not None, "Could not find 'Subtract' method symbol in Module1.vb"

        sel_start = subtract_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"] + 1)

        ref_files = cast(list[str], [ref.get("relativePath", "") for ref in refs])

        assert any(
            os.path.join("Models", "Person.vb") in ref_file for ref_file in ref_files
        ), "Should find reference in Models/Person.vb where Calculator.Subtract is called"
        assert len(refs) > 0, "Should find at least one reference"

        refs_second_call = language_server.request_references(file_path, sel_start["line"], sel_start["character"] + 1)
        assert refs_second_call == refs, "Second call to request_references should return the same results"


@pytest.mark.vbnet
class TestVBNetSolutionProjectOpening:
    def test_breadth_first_file_scan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            (temp_path / "file1.txt").touch()
            (temp_path / "subdir1").mkdir()
            (temp_path / "subdir1" / "file2.txt").touch()
            (temp_path / "subdir2").mkdir()
            (temp_path / "subdir2" / "file3.txt").touch()
            (temp_path / "subdir1" / "subdir3").mkdir()
            (temp_path / "subdir1" / "subdir3" / "file4.txt").touch()

            files = list(breadth_first_file_scan(str(temp_path)))
            filenames = [os.path.basename(f) for f in files]

            assert len(files) == 4
            assert "file1.txt" in filenames
            assert "file2.txt" in filenames
            assert "file3.txt" in filenames
            assert "file4.txt" in filenames

            assert filenames[0] == "file1.txt"

    def test_find_solution_or_project_file_with_solution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            solution_file = temp_path / "MySolution.sln"
            project_file = temp_path / "MyProject.vbproj"
            solution_file.touch()
            project_file.touch()

            result = find_solution_or_project_file(str(temp_path))

            assert result == str(solution_file)

    def test_find_solution_or_project_file_with_project_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            project_file = temp_path / "MyProject.vbproj"
            project_file.touch()

            result = find_solution_or_project_file(str(temp_path))

            assert result == str(project_file)

    def test_find_solution_or_project_file_returns_none_when_no_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            (temp_path / "readme.txt").touch()
            (temp_path / "other.vb").touch()

            result = find_solution_or_project_file(str(temp_path))

            assert result is None

    def test_solution_and_project_opening_with_real_test_repo(self):
        test_repo_path = Path(__file__).parent.parent.parent / "resources" / "repos" / "vbnet" / "test_repo"

        if not test_repo_path.exists():
            pytest.skip("VB.NET test repository not found")

        result = find_solution_or_project_file(str(test_repo_path))

        assert result is not None
        assert result.endswith((".sln", ".vbproj"))
        assert os.path.exists(result)

    def test_vbnet_url_construction(self):
        from solidlsp.language_servers.vbnet_language_server import _RUNTIME_DEPENDENCIES, _VBNET_VERSION

        for dep in _RUNTIME_DEPENDENCIES:
            assert dep.url is not None
            assert _VBNET_VERSION in dep.url
            assert "LaunchCG/roslyn-vbnet-languageserver" in dep.url
            assert dep.binary_name == "Microsoft.CodeAnalysis.LanguageServer.dll"

    @patch("solidlsp.language_servers.vbnet_language_server.VBNetLanguageServer.DependencyProvider._ensure_server_installed")
    @patch("solidlsp.language_servers.vbnet_language_server.VBNetLanguageServer._start_server")
    def test_vbnet_language_server_logs_solution_discovery(self, mock_start_server, mock_ensure_server_installed):
        mock_ensure_server_installed.return_value = ("/usr/bin/dotnet", "/path/to/server.dll")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            solution_file = temp_path / "TestSolution.sln"
            solution_file.touch()

            mock_config = Mock(spec=LanguageServerConfig)
            mock_config.ignored_paths = []

            mock_settings = Mock(spec=SolidLSPSettings)
            mock_settings.ls_resources_dir = "/tmp/test_ls_resources"
            mock_settings.project_data_path = str(temp_path / "project_data")

            VBNetLanguageServer(mock_config, str(temp_path), mock_settings)
