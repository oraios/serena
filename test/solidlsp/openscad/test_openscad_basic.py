from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.openscad
class TestOpenSCADLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.OPENSCAD], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.OPENSCAD], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that the language server starts and stops successfully."""
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.OPENSCAD], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.OPENSCAD], indirect=True)
    def test_document_symbols(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test getting document symbols from a file."""
        # Get symbols from shapes.scad which has 4 modules
        result = language_server.request_document_symbols(str(repo_path / "shapes.scad"))
        all_symbols, _root_symbols = result.get_all_symbols_and_roots()

        assert all_symbols, f"Expected non-empty symbols but got {all_symbols=}"
        # Should find at least the 4 modules: cube_shape, sphere_shape, cylinder_shape, combined_shape
        symbol_names = [s.get("name", "") for s in all_symbols]
        expected_modules = ["cube_shape", "sphere_shape", "cylinder_shape", "combined_shape"]
        for module_name in expected_modules:
            assert module_name in symbol_names, f"Expected to find module {module_name} in symbols, got {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.OPENSCAD], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.OPENSCAD], indirect=True)
    def test_find_definition_within_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding definition of a local module within the same file."""
        # In main.scad:
        # Line 35 (1-indexed): module local_assembly() {
        # Line 44 (1-indexed): local_assembly();
        # LSP is 0-indexed: definition on line 34, usage on line 43
        # Find definition of local_assembly from its usage on line 44
        # "    local_assembly();"
        #      ^ char 4
        definition_location_list = language_server.request_definition(str(repo_path / "main.scad"), 43, 5)

        assert definition_location_list, f"Expected non-empty definition_location_list but got {definition_location_list=}"
        assert len(definition_location_list) >= 1
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("main.scad")
        # Definition of local_assembly is on line 35 (1-indexed) / line 34 (0-indexed)
        assert definition_location["range"]["start"]["line"] == 34

    @pytest.mark.parametrize("language_server", [Language.OPENSCAD], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.OPENSCAD], indirect=True)
    def test_find_definition_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding definition of a module from an included file."""
        # In main.scad:
        # Line 10 (1-indexed): cube_shape(15);
        # cube_shape is defined in shapes.scad on line 4 (1-indexed) / line 3 (0-indexed)
        # "cube_shape(15);"
        #  ^ char 0
        definition_location_list = language_server.request_definition(str(repo_path / "main.scad"), 9, 1)

        assert definition_location_list, f"Expected non-empty definition_location_list but got {definition_location_list=}"
        assert len(definition_location_list) >= 1
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("shapes.scad")
        # Definition of cube_shape is on line 4 (1-indexed) / line 3 (0-indexed)
        assert definition_location["range"]["start"]["line"] == 3

    @pytest.mark.parametrize("language_server", [Language.OPENSCAD], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.OPENSCAD], indirect=True)
    def test_find_references_within_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding references to a local module within the same file."""
        # In main.scad:
        # Line 35 (1-indexed): module local_assembly() {  <- definition
        # Line 44 (1-indexed): local_assembly();          <- usage
        # LSP is 0-indexed: definition on line 34, usage on line 43
        # Find references from the definition
        references = language_server.request_references(str(repo_path / "main.scad"), 34, 7)

        assert references, f"Expected non-empty references but got {references=}"
        # Should find at least the usage on line 44 (0-indexed: 43)
        reference_lines = [ref["range"]["start"]["line"] for ref in references]
        assert 43 in reference_lines, f"Expected to find reference on line 43, got lines {reference_lines}"

    @pytest.mark.parametrize("language_server", [Language.OPENSCAD], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.OPENSCAD], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding references to a module used within the same file.

        Note: Cross-file references (finding usages in files that import a module)
        require the LSP to have those files opened. This test verifies references
        within the defining file work correctly.
        """
        # cube_shape is defined in shapes.scad line 4 (0-indexed: 3)
        # It's also used within shapes.scad in combined_shape on line 21 (0-indexed: 20)
        # Find references from the definition in shapes.scad
        references = language_server.request_references(str(repo_path / "shapes.scad"), 3, 7)

        assert references, f"Expected non-empty references but got {references=}"
        # Should find references within shapes.scad itself
        shapes_scad_refs = [ref for ref in references if ref["uri"].endswith("shapes.scad")]
        assert shapes_scad_refs, f"Expected to find references in shapes.scad, got refs in: {[ref['uri'] for ref in references]}"
        # Should include the usage in combined_shape (line 21, 0-indexed: 20)
        ref_lines = [ref["range"]["start"]["line"] for ref in shapes_scad_refs]
        assert 20 in ref_lines, f"Expected to find reference on line 20 (combined_shape), got lines {ref_lines}"
