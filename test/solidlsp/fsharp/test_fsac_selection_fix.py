from solidlsp.language_servers.fsautocomplete_server import FsAutoCompleteServer


def test_fix_selection_range_shifts_blank_before_doc_comment() -> None:
    lines = [
        "module Test\n",  # 0
        "\n",  # 1 blank
        "/// Doc for Foo\n",  # 2
        "type Foo = { X: int }\n",  # 3
    ]
    sym = {
        "name": "Foo",
        "range": {"start": {"line": 1, "character": 0}, "end": {"line": 3, "character": 18}},
        "selectionRange": {"start": {"line": 1, "character": 0}, "end": {"line": 3, "character": 18}},
        "location": {"range": {"start": {"line": 1, "character": 0}, "end": {"line": 3, "character": 18}}},
    }
    fixed = FsAutoCompleteServer._fix_selection_range(sym, lines)
    # range/location/selection move to doc comment line (2)
    assert fixed["range"]["start"]["line"] == 2
    assert fixed["location"]["range"]["start"]["line"] == 2
    assert fixed["selectionRange"]["start"]["line"] == 2
    # End lines shift by the same delta
    assert fixed["range"]["end"]["line"] == 4
    assert fixed["selectionRange"]["end"]["line"] == 4
    assert fixed["location"]["range"]["end"]["line"] == 4


def test_fix_selection_range_keeps_zero_based_and_column() -> None:
    lines = ["module Test\n", "type Bar = { Y: int }\n"]
    sym = {
        "name": "Bar",
        "range": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 20}},
        "selectionRange": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 20}},
    }
    fixed = FsAutoCompleteServer._fix_selection_range(sym, lines)
    assert fixed["range"]["start"]["line"] == 1
    assert fixed["selectionRange"]["start"]["line"] == 1
    assert fixed["range"]["start"]["character"] == lines[1].find("Bar")
    assert fixed["selectionRange"]["start"]["character"] == lines[1].find("Bar")


def test_fix_selection_range_aligns_identifier_and_keeps_range_on_doc_comment() -> None:
    lines = [
        "module Test\n",  # 0
        "\n",  # 1 blank
        "/// Doc for Calculator\n",  # 2
        "type Calculator() =\n",  # 3
        "    member _.Add x y = x + y\n",  # 4
    ]
    sym = {
        "name": "Calculator",
        "range": {"start": {"line": 1, "character": 0}, "end": {"line": 4, "character": 30}},
        "selectionRange": {"start": {"line": 1, "character": 0}, "end": {"line": 4, "character": 30}},
        "location": {"range": {"start": {"line": 1, "character": 0}, "end": {"line": 4, "character": 30}}},
    }
    fixed = FsAutoCompleteServer._fix_selection_range(sym, lines)
    # Range/selection anchored to doc comment line (2)
    assert fixed["range"]["start"]["line"] == 2
    assert fixed["location"]["range"]["start"]["line"] == 2
    assert fixed["selectionRange"]["start"]["line"] == 2
    # End line also shifts by one to stay aligned with the span
    assert fixed["range"]["end"]["line"] == 5
    assert fixed["selectionRange"]["end"]["line"] == 5


def test_fix_selection_range_noop_for_newer_fsac() -> None:
    lines = ["\n", "/// Doc\n", "type Foo = { X: int }\n"]
    sym = {
        "name": "Foo",
        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 2, "character": 18}},
        "selectionRange": {"start": {"line": 0, "character": 0}, "end": {"line": 2, "character": 18}},
    }
    fixed = FsAutoCompleteServer._fix_selection_range(sym, lines, fsac_version="0.100.0")
    assert fixed["range"]["start"]["line"] == 0
    assert fixed["selectionRange"]["start"]["line"] == 0


def test_fix_selection_range_applies_for_old_fsac_versions() -> None:
    lines = ["\n", "/// Doc\n", "type Foo = { X: int }\n"]
    sym = {
        "name": "Foo",
        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 2, "character": 18}},
        "selectionRange": {"start": {"line": 0, "character": 0}, "end": {"line": 2, "character": 18}},
    }
    fixed = FsAutoCompleteServer._fix_selection_range(sym, lines, fsac_version="0.81.0")
    assert fixed["range"]["start"]["line"] == 1
    assert fixed["selectionRange"]["start"]["line"] == 1


def test_fix_selection_ranges_recurses_children() -> None:
    lines = ["\n", "/// Doc\n", "type Parent() =\n", "    member _.Child() = ()\n"]
    parent = {
        "name": "Parent",
        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 3, "character": 10}},
        "selectionRange": {"start": {"line": 0, "character": 0}, "end": {"line": 3, "character": 10}},
        "children": [
            {
                "name": "Child",
                "range": {"start": {"line": 3, "character": 4}, "end": {"line": 3, "character": 25}},
                "selectionRange": {"start": {"line": 3, "character": 4}, "end": {"line": 3, "character": 25}},
            }
        ],
    }
    fixed = FsAutoCompleteServer._fix_selection_ranges([parent], lines)
    parent_fixed = fixed[0]
    assert parent_fixed["range"]["start"]["line"] == 1
    assert parent_fixed["selectionRange"]["start"]["line"] == 1
    child_fixed = parent_fixed["children"][0]
    assert child_fixed["selectionRange"]["start"]["line"] == 3


def test_convert_ranges_to_one_based() -> None:
    sym = {
        "name": "Foo",
        "range": {"start": {"line": 1, "character": 0}, "end": {"line": 2, "character": 10}},
        "selectionRange": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 5}},
        "location": {"range": {"start": {"line": 1, "character": 0}, "end": {"line": 2, "character": 10}}},
        "children": [],
    }
    converted = FsAutoCompleteServer._convert_ranges_to_one_based([sym])[0]
    assert converted["range"]["start"]["line"] == 2
    assert converted["selectionRange"]["start"]["line"] == 2
    assert converted["location"]["range"]["start"]["line"] == 2
