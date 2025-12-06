import json
from pathlib import Path

import pytest

from solidlsp.ls_config import Language
from test.conftest import create_ls


@pytest.mark.fsharp
def test_doc_comments_with_blank_and_whitespace_lines() -> None:
    """
    Ensure doc comments with preceding whitespace/blank lines are anchored correctly (1-based).
    """
    repo_path = Path(__file__).parents[2] / "resources" / "repos" / "fsharp" / "test_repo"
    ls = create_ls(Language.FSHARP, str(repo_path), log_level=0)
    ls.start()
    try:
        symbols = ls.request_document_symbols("src/WhitespaceDoc.fs")
        lines = (repo_path / "src" / "WhitespaceDoc.fs").read_text().splitlines()
        targets = {
            "SpacedRecord": "Doc for SpacedRecord",
            "TabbedClass": "Doc for TabbedClass",
            "MultiLineDoc": "First line of multi",
        }
        found = 0
        for sym in symbols.iter_symbols():
            name = sym.get("name")
            if name not in targets:
                continue
            expected_line = next(i for i, line in enumerate(lines, start=1) if targets[name] in line)
            assert sym["range"]["start"]["line"] == expected_line, json.dumps(sym, indent=2)
            assert sym["selectionRange"]["start"]["line"] == expected_line, json.dumps(sym, indent=2)
            found += 1
        assert found == len(targets), "Did not find all targets in WhitespaceDoc.fs"
    finally:
        ls.stop()
