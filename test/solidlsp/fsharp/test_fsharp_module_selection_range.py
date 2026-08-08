"""
Regression test for #925: FsAutoComplete's selectionRange for a `module <Name>` declaration
points at the `module` keyword rather than at `<Name>`, so hovering a module reports the
generic keyword's docs instead of the module's own (confirmed by dsyme and MischaPanch in the
issue thread). This pins FSharpLanguageServer._fix_module_selection_range and the
request_document_symbols override directly, without spinning up FsAutoComplete: F# language
server tests are unconditionally disabled (test/conftest.py, category 1, "F# language server is
currently unreliable"), so a live-LS test can never run here or on CI.
"""

from contextlib import contextmanager

from solidlsp import ls_types
from solidlsp.language_servers.fsharp_language_server import FSharpLanguageServer
from solidlsp.ls import DocumentSymbols, SolidLanguageServer


def _bare_fsharp_server() -> FSharpLanguageServer:
    """Instance without running __init__ (no dotnet tool install, no process); same technique
    as test_typescript_timeout_policy.py's _bare_ts_server / test_rename_didopen.py.
    """
    return object.__new__(FSharpLanguageServer)


def _module_symbol(name: str, line: int, start_char: int, end_char: int) -> ls_types.UnifiedSymbolInformation:
    return {
        "name": name,
        "kind": ls_types.SymbolKind.Module,
        "selectionRange": {
            "start": {"line": line, "character": start_char},
            "end": {"line": line, "character": end_char},
        },
        "children": [],
    }


class TestFixModuleSelectionRange:
    def test_top_level_module_declaration(self) -> None:
        # "module Calculator" -- FsAutoComplete reports selectionRange over "module" (0-6)
        server = _bare_fsharp_server()
        symbol = _module_symbol("Calculator", line=0, start_char=0, end_char=6)
        file_content = "module Calculator\n\nlet add a b = a + b\n"

        fixed = server._fix_module_selection_range(symbol, file_content)

        assert fixed["selectionRange"]["start"] == {"line": 0, "character": 7}
        assert fixed["selectionRange"]["end"] == {"line": 0, "character": 17}
        assert file_content.splitlines()[0][7:17] == "Calculator"

    def test_nested_module_declaration_with_equals(self) -> None:
        # "module PersonModule =" -- same keyword-position bug, trailing '='
        server = _bare_fsharp_server()
        symbol = _module_symbol("PersonModule", line=2, start_char=0, end_char=6)
        file_content = "namespace Models\n\nmodule PersonModule =\n    let x = 1\n"

        fixed = server._fix_module_selection_range(symbol, file_content)

        assert fixed["selectionRange"]["start"] == {"line": 2, "character": 7}
        assert fixed["selectionRange"]["end"] == {"line": 2, "character": 19}

    def test_recursive_module_declaration(self) -> None:
        # "module rec Foo" -- the "rec" keyword must not be mistaken for the module name
        server = _bare_fsharp_server()
        symbol = _module_symbol("Foo", line=0, start_char=0, end_char=6)
        file_content = "module rec Foo\n"

        fixed = server._fix_module_selection_range(symbol, file_content)

        assert fixed["selectionRange"]["start"] == {"line": 0, "character": 11}
        assert fixed["selectionRange"]["end"] == {"line": 0, "character": 14}

    def test_already_correct_selection_range_is_left_alone(self) -> None:
        # A future FsAutoComplete release that already points at the identifier must not be
        # rewritten (guards against masking an upstream fix instead of a no-op).
        server = _bare_fsharp_server()
        symbol = _module_symbol("Calculator", line=0, start_char=7, end_char=17)
        file_content = "module Calculator\n"

        fixed = server._fix_module_selection_range(symbol, file_content)

        assert fixed is symbol

    def test_non_module_symbol_is_untouched(self) -> None:
        # Functions/types already select the identifier correctly per MischaPanch (#925); only
        # Module symbols should ever be corrected.
        server = _bare_fsharp_server()
        symbol: ls_types.UnifiedSymbolInformation = {
            "name": "add",
            "kind": ls_types.SymbolKind.Function,
            "selectionRange": {
                "start": {"line": 2, "character": 4},
                "end": {"line": 2, "character": 7},
            },
            "children": [],
        }
        file_content = "module Calculator\n\nlet add a b = a + b\n"

        fixed = server._fix_module_selection_range(symbol, file_content)

        assert fixed is symbol


class TestRequestDocumentSymbolsWiring:
    def test_fixes_every_symbol_in_the_tree_not_just_roots(self, monkeypatch) -> None:
        """End-to-end wiring test: the override must fix nested symbols too, mirroring the
        already-merged fortran_language_server.py recursive-fix pattern this follows.
        """
        outer = _module_symbol("Outer", line=0, start_char=0, end_char=6)
        inner = _module_symbol("Inner", line=1, start_char=4, end_char=10)
        outer["children"] = [inner]

        file_content = "module Outer\n    module Inner =\n        let x = 1\n"

        def fake_super_request_document_symbols(self, relative_file_path, file_buffer=None):
            return DocumentSymbols([outer])

        monkeypatch.setattr(SolidLanguageServer, "request_document_symbols", fake_super_request_document_symbols)

        server = _bare_fsharp_server()

        @contextmanager
        def fake_open_file(relative_file_path):
            yield type("FakeFileData", (), {"contents": file_content})()

        monkeypatch.setattr(server, "open_file", fake_open_file)

        result = server.request_document_symbols("Test.fs")

        root = result.root_symbols[0]
        assert root["selectionRange"]["start"] == {"line": 0, "character": 7}
        child = root["children"][0]
        assert child["selectionRange"]["start"] == {"line": 1, "character": 11}
