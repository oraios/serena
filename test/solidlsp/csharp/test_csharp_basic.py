import os
import tempfile
from pathlib import Path
from typing import cast

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.language_servers.csharp_language_server import (
    breadth_first_file_scan,
    find_solution_or_project_file,
)
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind
from solidlsp.ls_utils import SymbolUtils
from test.conftest import find_identifier_position, get_repo_path, language_has_verified_implementation_support
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols


@pytest.mark.csharp
class TestCSharpLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.CSHARP], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        """Test finding symbols in the full symbol tree."""
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Program"), "Program class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Calculator"), "Calculator class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Add"), "Add method not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.CSHARP], indirect=True)
    def test_get_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test getting document symbols from a C# file."""
        file_path = os.path.join("Program.cs")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        # Check that we have symbols
        assert len(symbols) > 0

        # Flatten the symbols if they're nested
        if isinstance(symbols[0], list):
            symbols = symbols[0]

        # Look for expected classes
        class_names = [s.get("name") for s in symbols if s.get("kind") == 5]  # 5 is class
        assert "Program" in class_names
        assert "Calculator" in class_names

    @pytest.mark.parametrize("language_server", [Language.CSHARP], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test finding references using symbol selection range."""
        file_path = os.path.join("Program.cs")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        add_symbol = None
        # Handle nested symbol structure
        symbol_list = symbols[0] if symbols and isinstance(symbols[0], list) else symbols
        for sym in symbol_list:
            # Symbol names are normalized to base form (e.g., "Add" not "Add(int, int) : int")
            if sym.get("name") == "Add":
                add_symbol = sym
                break
        assert add_symbol is not None, "Could not find 'Add' method symbol in Program.cs"
        sel_start = add_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"] + 1)
        assert any("Program.cs" in ref.get("relativePath", "") for ref in refs), (
            "Program.cs should reference Add method (tried all positions in selectionRange)"
        )

    @pytest.mark.parametrize("language_server", [Language.CSHARP], indirect=True)
    def test_nested_namespace_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test getting symbols from nested namespace."""
        file_path = os.path.join("Models", "Person.cs")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        # Check that we have symbols
        assert len(symbols) > 0

        # Flatten the symbols if they're nested
        if isinstance(symbols[0], list):
            symbols = symbols[0]

        # Check that we have the Person class
        assert any(s.get("name") == "Person" and s.get("kind") == 5 for s in symbols)

        # Check for properties and methods (names are normalized to base form)
        symbol_names = [s.get("name") for s in symbols]
        assert "Name" in symbol_names, "Name property not found"
        assert "Age" in symbol_names, "Age property not found"
        assert "Email" in symbol_names, "Email property not found"
        assert "ToString" in symbol_names, "ToString method not found"
        assert "IsAdult" in symbol_names, "IsAdult method not found"

    @pytest.mark.parametrize("language_server", [Language.CSHARP], indirect=True)
    def test_find_referencing_symbols_across_files(self, language_server: SolidLanguageServer) -> None:
        """Test finding references to Calculator.Subtract method across files."""
        # First, find the Subtract method in Program.cs
        file_path = os.path.join("Program.cs")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        # Flatten the symbols if they're nested
        symbol_list = symbols[0] if symbols and isinstance(symbols[0], list) else symbols

        subtract_symbol = None
        for sym in symbol_list:
            # Symbol names are normalized to base form (e.g., "Subtract" not "Subtract(int, int) : int")
            if sym.get("name") == "Subtract":
                subtract_symbol = sym
                break

        assert subtract_symbol is not None, "Could not find 'Subtract' method symbol in Program.cs"

        # Get references to the Subtract method
        sel_start = subtract_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"] + 1)

        # Should find references where the method is called
        ref_files = cast(list[str], [ref.get("relativePath", "") for ref in refs])
        print(f"Found references: {refs}")
        print(f"Reference files: {ref_files}")

        # Check that we have reference in Models/Person.cs where Calculator.Subtract is called
        # Note: New Roslyn version doesn't include the definition itself as a reference (more correct behavior)
        assert any(os.path.join("Models", "Person.cs") in ref_file for ref_file in ref_files), (
            "Should find reference in Models/Person.cs where Calculator.Subtract is called"
        )
        assert len(refs) > 0, "Should find at least one reference"

        # check for a second time, since the first call may trigger initialization and change the state of the LS
        refs_second_call = language_server.request_references(file_path, sel_start["line"], sel_start["character"] + 1)
        assert refs_second_call == refs, "Second call to request_references should return the same results"

    @pytest.mark.parametrize("language_server", [Language.CSHARP], indirect=True)
    def test_hover_includes_type_information(self, language_server: SolidLanguageServer) -> None:
        """Test that hover information is available and includes type information."""
        file_path = os.path.join("Models", "Person.cs")

        # Open the file first
        language_server.open_file(file_path)

        # Test 1: Hover over the Name property (line 6, column 23 - on "Name")
        # Source: public string Name { get; set; }
        hover_info = language_server.request_hover(file_path, 6, 23)

        # Verify hover returns content
        assert hover_info is not None, "Hover should return information for Name property"
        assert isinstance(hover_info, dict), "Hover should be a dict"
        assert "contents" in hover_info, "Hover should have contents"

        contents = hover_info["contents"]
        assert isinstance(contents, dict), "Hover contents should be a dict"
        assert "value" in contents, "Hover contents should have value"
        hover_text = contents["value"]

        # Verify the hover contains property signature with type
        assert "string" in hover_text, f"Hover should include 'string' type, got: {hover_text}"
        assert "Name" in hover_text, f"Hover should include 'Name' property name, got: {hover_text}"

        # Test 2: Hover over the IsAdult method (line 22, column 21 - on "IsAdult")
        # Source: public bool IsAdult()
        hover_method = language_server.request_hover(file_path, 22, 21)

        # Verify method hover returns content
        assert hover_method is not None, "Hover should return information for IsAdult method"
        assert isinstance(hover_method, dict), "Hover should be a dict"
        assert "contents" in hover_method, "Hover should have contents"

        contents = hover_method["contents"]
        assert isinstance(contents, dict), "Hover contents should be a dict"
        assert "value" in contents, "Hover contents should have value"
        method_hover_text = contents["value"]

        # Verify the hover contains method signature with return type
        assert "bool" in method_hover_text, f"Hover should include 'bool' return type, got: {method_hover_text}"
        assert "IsAdult" in method_hover_text, f"Hover should include 'IsAdult' method name, got: {method_hover_text}"

    if language_has_verified_implementation_support(Language.CSHARP):

        @pytest.mark.parametrize("language_server", [Language.CSHARP], indirect=True)
        def test_find_implementations(self, language_server: SolidLanguageServer) -> None:
            repo_path = get_repo_path(Language.CSHARP)
            pos = find_identifier_position(repo_path / "Services" / "IGreeter.cs", "FormatGreeting")
            assert pos is not None, "Could not find IGreeter.FormatGreeting in fixture"

            implementations = language_server.request_implementation("Services/IGreeter.cs", *pos)
            assert implementations, "Expected at least one implementation of IGreeter.FormatGreeting"
            assert any("ConsoleGreeter.cs" in implementation.get("relativePath", "") for implementation in implementations), (
                f"Expected ConsoleGreeter.FormatGreeting in implementations, got: {implementations}"
            )

        @pytest.mark.parametrize("language_server", [Language.CSHARP], indirect=True)
        def test_request_implementing_symbols(self, language_server: SolidLanguageServer) -> None:
            repo_path = get_repo_path(Language.CSHARP)
            pos = find_identifier_position(repo_path / "Services" / "IGreeter.cs", "FormatGreeting")
            assert pos is not None, "Could not find IGreeter.FormatGreeting in fixture"

            implementing_symbols = language_server.request_implementing_symbols("Services/IGreeter.cs", *pos)
            assert implementing_symbols, "Expected implementing symbols for IGreeter.FormatGreeting"
            assert any(
                symbol.get("name") == "FormatGreeting" and "ConsoleGreeter.cs" in symbol["location"].get("relativePath", "")
                for symbol in implementing_symbols
            ), f"Expected ConsoleGreeter.FormatGreeting symbol, got: {implementing_symbols}"


@pytest.mark.csharp
class TestCSharpSolutionProjectOpening:
    """Test C# language server solution and project opening functionality."""

    def test_breadth_first_file_scan(self):
        """Test that breadth_first_file_scan finds files in breadth-first order."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test directory structure
            (temp_path / "file1.txt").touch()
            (temp_path / "subdir1").mkdir()
            (temp_path / "subdir1" / "file2.txt").touch()
            (temp_path / "subdir2").mkdir()
            (temp_path / "subdir2" / "file3.txt").touch()
            (temp_path / "subdir1" / "subdir3").mkdir()
            (temp_path / "subdir1" / "subdir3" / "file4.txt").touch()

            # Scan files
            files = list(breadth_first_file_scan(str(temp_path)))
            filenames = [os.path.basename(f) for f in files]

            # Should find all files
            assert len(files) == 4
            assert "file1.txt" in filenames
            assert "file2.txt" in filenames
            assert "file3.txt" in filenames
            assert "file4.txt" in filenames

            # file1.txt should be found first (breadth-first)
            assert filenames[0] == "file1.txt"

    def test_find_solution_or_project_file_with_solution(self):
        """Test that find_solution_or_project_file prefers .sln files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create both .sln and .csproj files
            solution_file = temp_path / "MySolution.sln"
            project_file = temp_path / "MyProject.csproj"
            solution_file.touch()
            project_file.touch()

            result = find_solution_or_project_file(str(temp_path))

            # Should prefer .sln file
            assert result == str(solution_file)

    def test_find_solution_or_project_file_with_project_only(self):
        """Test that find_solution_or_project_file falls back to .csproj files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create only .csproj file
            project_file = temp_path / "MyProject.csproj"
            project_file.touch()

            result = find_solution_or_project_file(str(temp_path))

            # Should return .csproj file
            assert result == str(project_file)

    def test_find_solution_or_project_file_with_nested_files(self):
        """Test that find_solution_or_project_file finds files in subdirectories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create nested structure
            (temp_path / "src").mkdir()
            solution_file = temp_path / "src" / "MySolution.sln"
            solution_file.touch()

            result = find_solution_or_project_file(str(temp_path))

            # Should find nested .sln file
            assert result == str(solution_file)

    def test_find_solution_or_project_file_returns_none_when_no_files(self):
        """Test that find_solution_or_project_file returns None when no .sln or .csproj files exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create some other files
            (temp_path / "readme.txt").touch()
            (temp_path / "other.cs").touch()

            result = find_solution_or_project_file(str(temp_path))

            # Should return None
            assert result is None

    def test_find_solution_or_project_file_prefers_solution_breadth_first(self):
        """Test that solution files are preferred even when deeper in the tree."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create .csproj at root and .sln in subdirectory
            project_file = temp_path / "MyProject.csproj"
            project_file.touch()

            (temp_path / "src").mkdir()
            solution_file = temp_path / "src" / "MySolution.sln"
            solution_file.touch()

            result = find_solution_or_project_file(str(temp_path))

            # Should still prefer .sln file even though it's deeper
            assert result == str(solution_file)

    def test_solution_and_project_opening_with_real_test_repo(self):
        """Test solution and project opening with the actual C# test repository."""
        # Get the C# test repo path
        test_repo_path = Path(__file__).parent.parent.parent / "resources" / "repos" / "csharp" / "test_repo"

        if not test_repo_path.exists():
            pytest.skip("C# test repository not found")

        # Test solution/project discovery in the real test repo
        result = find_solution_or_project_file(str(test_repo_path))

        # Should find either .sln or .csproj file
        assert result is not None
        assert result.endswith((".sln", ".csproj"))

        # Verify the file actually exists
        assert os.path.exists(result)

    @pytest.mark.parametrize("language_server", [Language.CSHARP], indirect=True)
    def test_bare_symbol_names(self, language_server) -> None:
        all_symbols = request_all_symbols(language_server)
        malformed_symbols = []
        for s in all_symbols:
            if has_malformed_name(s, period_allowed=s["kind"] == SymbolKind.Namespace):
                malformed_symbols.append(s)
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )
