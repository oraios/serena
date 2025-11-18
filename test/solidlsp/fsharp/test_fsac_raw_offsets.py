import json
from pathlib import Path

import pytest

# These tests assert the raw FsAC documentSymbol output we captured in fixtures.
# They validate the observed offset pattern (FsAC anchors to the blank line before doc comments).


@pytest.mark.fsharp
def test_raw_offsets_test_repo_calculator() -> None:
    base = Path(__file__).parents[2] / "resources" / "repos" / "fsharp" / "test_repo"
    data = json.loads((base / "Calculator.fs.008100.json").read_text())
    # Find the Calculator type symbol
    calc = next(item for item in data if item.get("name") == "Calculator")
    # Raw FsAC is 0-based and starts on the blank line before the doc comment (line 5 -> 0-based 5)
    assert calc["range"]["start"]["line"] == 5
    assert calc["selectionRange"]["start"]["line"] == 5
