# SPDX-License-Identifier: MIT
"""Unit tests for ``SolidLanguageServer.request_referencing_symbols`` driven by scripted LSP responses.

No language markers: the language server process is replaced by a test double, so these run in catch-all.
"""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

from solidlsp import ls_types
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig, LanguageServerId
from solidlsp.ls_process import LanguageServerInterface
from solidlsp.lsp_protocol_handler.server import StringDict
from solidlsp.settings import SolidLSPSettings

_TARGET_SOURCE = "def run():\n    return 1\n"
_CALLER_SOURCE = "import target\n\n\ndef run():\n    return target.run()\n"


class _ScriptedLanguageServer(SolidLanguageServer):
    """Language server whose LSP requests are answered from scripted responses instead of a real server process."""

    def __init__(self, repository_root_path: Path, references: list[dict], document_symbols: dict[str, list[dict]]) -> None:
        """
        :param repository_root_path: the root of the repository containing the referenced files.
        :param references: the ``textDocument/references`` response (in the order given).
        :param document_symbols: the ``textDocument/documentSymbol`` responses, keyed by file URI.
        """
        self._references = references
        self._document_symbols = document_symbols
        settings = SolidLSPSettings(solidlsp_dir=str(repository_root_path / ".solidlsp"), project_data_path=str(repository_root_path))
        super().__init__(LanguageServerConfig(LanguageServerId.PYTHON), str(repository_root_path), None, "python", settings)
        self.server_started = True

    def _create_language_server_interface(self, logging_fn: Callable[[str, str, StringDict | str], None] | None) -> LanguageServerInterface:
        server = MagicMock()
        server.send.references.side_effect = lambda _params: self._references
        server.send.document_symbol.side_effect = lambda params: self._document_symbols[params["textDocument"]["uri"]]
        return server

    def _start_server(self) -> None:
        raise AssertionError("Not used in this test")

    def _create_base_initialize_params(self) -> dict:
        return {}

    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 0


def _range(start_line: int, start_col: int, end_line: int, end_col: int) -> dict:
    return {"start": {"line": start_line, "character": start_col}, "end": {"line": end_line, "character": end_col}}


def _function_symbol(name: str, range_d: dict, selection_range: dict) -> dict:
    return {"name": name, "kind": ls_types.SymbolKind.Function, "range": range_d, "selectionRange": selection_range, "children": []}


def test_referencing_symbols_with_same_name_as_target_listed_after_its_declaration(tmp_path: Path) -> None:
    """Callers named like the target (``first.run`` and ``second.run`` calling ``target.run``) are all returned
    when the language server lists them after the target's declaration (as e.g. the Gleam LS does).
    """
    for name, source in (("target", _TARGET_SOURCE), ("first", _CALLER_SOURCE), ("second", _CALLER_SOURCE)):
        (tmp_path / f"{name}.py").write_text(source, encoding="utf-8")
    uri = {name: (tmp_path / f"{name}.py").as_uri() for name in ("target", "first", "second")}

    # the declaration `run` (line 0, col 4) comes first, followed by the calls `target.run()` (line 4, col 18)
    references = [
        {"uri": uri["target"], "range": _range(0, 4, 0, 7)},
        {"uri": uri["first"], "range": _range(4, 18, 4, 21)},
        {"uri": uri["second"], "range": _range(4, 18, 4, 21)},
    ]
    document_symbols = {
        uri["target"]: [_function_symbol("run", _range(0, 0, 1, 12), _range(0, 4, 0, 7))],
        uri["first"]: [_function_symbol("run", _range(3, 0, 4, 23), _range(3, 4, 3, 7))],
        uri["second"]: [_function_symbol("run", _range(3, 0, 4, 23), _range(3, 4, 3, 7))],
    }
    language_server = _ScriptedLanguageServer(tmp_path, references, document_symbols)

    refs = language_server.request_referencing_symbols("target.py", 0, 4, include_imports=False)

    callers = {(ref.symbol["location"]["relativePath"], ref.symbol["name"]) for ref in refs}
    assert callers == {("first.py", "run"), ("second.py", "run")}, f"Expected both same-named callers, got {callers}"
