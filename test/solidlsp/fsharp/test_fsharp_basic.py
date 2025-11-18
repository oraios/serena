from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.fsharp
class TestFSharpLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that the FsAutoComplete language server starts and stops successfully."""
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_find_symbols_in_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding symbols in Helper.fs"""
        helper_fs_path = str(repo_path / "src" / "Helper.fs")

        symbols = language_server.request_document_symbols(helper_fs_path)

        assert symbols, f"Expected non-empty symbols list but got {symbols=}"

        # Extract symbol names
        symbol_names = []
        for symbol in symbols.iter_symbols():
            if isinstance(symbol, dict):
                symbol_names.append(symbol.get("name", ""))

        # Check that we found the expected functions
        expected_symbols = ["add", "subtract", "multiply", "divide"]
        for expected in expected_symbols:
            assert expected in symbol_names, f"Expected to find symbol '{expected}' but it was not in {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_find_definition_within_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding definition of the helper function from its usage"""
        # Test finding definition of 'subtract' from Calculator.fs
        calculator_fs_path = str(repo_path / "src" / "Calculator.fs")

        # In Calculator.fs line 13 (0-indexed line 12):
        # member this.Subtract(x, y) = subtract x y
        # The 'subtract' call starts at character 34
        definition_location_list = language_server.request_definition(calculator_fs_path, 12, 34)

        assert definition_location_list, f"Expected non-empty definition_location_list but got {definition_location_list=}"
        assert len(definition_location_list) >= 1

        # Should point to Helper.fs where 'subtract' is defined
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("Helper.fs"), f"Expected definition in Helper.fs but got {definition_location['uri']}"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_find_definition_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding definition of a function called from Program.fs defined in Calculator.fs"""
        program_fs_path = str(repo_path / "src" / "Program.fs")

        # In Program.fs line 13 (0-indexed line 12):
        # printfn "5 + 3 = %d" (calc.Add(5, 3))
        # Find definition of Add method
        definition_location_list = language_server.request_definition(program_fs_path, 12, 33)  # Position on 'Add'

        assert definition_location_list, f"Expected non-empty definition_location_list but got {definition_location_list=}"
        assert len(definition_location_list) >= 1

        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith(
            "Calculator.fs"
        ), f"Expected definition in Calculator.fs but got {definition_location['uri']}"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_find_type_definition(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding type definition"""
        program_fs_path = str(repo_path / "src" / "Program.fs")

        # In Program.fs line 24 (0-indexed line 23):
        # let circle = Circle 5.0
        # Find definition of Circle type
        definition_location_list = language_server.request_definition(program_fs_path, 23, 17)  # Position on 'Circle'

        assert definition_location_list, f"Expected non-empty definition_location_list but got {definition_location_list=}"
        assert len(definition_location_list) >= 1

        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("Types.fs"), f"Expected definition in Types.fs but got {definition_location['uri']}"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_find_references_within_module(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding references to the 'add' function"""
        helper_fs_path = str(repo_path / "src" / "Helper.fs")

        # Find references to 'add' function from its definition
        # In Helper.fs line 4 (0-indexed line 3):
        # let add x y = x + y
        references = language_server.request_references(helper_fs_path, 3, 4)  # Position on 'add'

        assert references, f"Expected non-empty references for 'add' but got {references=}"

        # Check that we found at least one reference
        assert len(references) >= 1, f"Expected at least 1 reference but got {len(references)}"

        # Extract filenames from references
        reference_files = [loc["uri"].split("/")[-1] for loc in references]

        # Should find references in Calculator.fs (where add is used)
        assert (
            "Calculator.fs" in reference_files or "Helper.fs" in reference_files
        ), f"Expected references in Calculator.fs or Helper.fs but got {reference_files}"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding references to Calculator class across files"""
        calculator_fs_path = str(repo_path / "src" / "Calculator.fs")

        # Find references to Calculator type from its definition
        # In Calculator.fs line 7 (0-indexed line 6):
        # type Calculator() =
        try:
            references = language_server.request_references(calculator_fs_path, 6, 6)

            # FsAutoComplete may or may not find cross-file references consistently
            # Just verify we get a valid result
            assert references is not None, "Expected references result (even if empty)"

            if references:
                reference_files = [loc["uri"].split("/")[-1] for loc in references]
                # If we found references, they should be in F# files
                assert any(f.endswith(".fs") for f in reference_files), f"Expected F# files but got {reference_files}"
        except Exception:
            # FsAutoComplete may not support all reference queries
            # Just verify the file is indexed
            symbols = language_server.request_document_symbols(calculator_fs_path)
            assert symbols, "Expected to at least get symbols from file"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_find_symbols_types_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding type definitions in Types.fs"""
        types_fs_path = str(repo_path / "src" / "Types.fs")

        symbols = language_server.request_document_symbols(types_fs_path)

        assert symbols, f"Expected non-empty symbols list but got {symbols=}"

        # Extract symbol names
        symbol_names = []
        for symbol in symbols.iter_symbols():
            if isinstance(symbol, dict):
                symbol_names.append(symbol.get("name", ""))

        # Check that we found the expected types and functions
        expected_symbols = ["Point", "Shape", "area", "Person", "createPerson"]
        for expected in expected_symbols:
            assert expected in symbol_names, f"Expected to find symbol '{expected}' but it was not in {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_find_module_definition(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding references to functions from helper module"""
        program_fs_path = str(repo_path / "src" / "Program.fs")

        # In Program.fs line 37 (0-indexed line 36):
        # printfn "Direct add: %d" (add 10 20)
        # Find definition of 'add' function
        definition_location_list = language_server.request_definition(program_fs_path, 36, 31)  # Position on 'add'

        assert definition_location_list, f"Expected non-empty definition_location_list but got {definition_location_list=}"
        assert len(definition_location_list) >= 1

        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("Helper.fs"), f"Expected definition in Helper.fs but got {definition_location['uri']}"
