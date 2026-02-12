"""Tests for symbol_utils grouping functions."""

from serena.tools.symbol_utils import group_refs_by_path_and_kind, group_symbols_by_kind


class TestGroupSymbolsByKind:
    def test_empty_list(self) -> None:
        result = group_symbols_by_kind([], kind_key="kind", name_extractor=lambda s: s.get("name", "unknown"))
        assert result == {}

    def test_simple_grouping(self) -> None:
        symbols = [
            {"name": "foo", "kind": "Function"},
            {"name": "bar", "kind": "Function"},
            {"name": "MyClass", "kind": "Class"},
        ]
        result = group_symbols_by_kind(symbols, kind_key="kind", name_extractor=lambda s: s["name"])
        assert dict(result) == {
            "Function": ["foo", "bar"],
            "Class": ["MyClass"],
        }

    def test_with_children_and_recurse(self) -> None:
        symbols = [
            {
                "name": "MyClass",
                "kind": "Class",
                "children": [
                    {"name": "method_a", "kind": "Method"},
                    {"name": "method_b", "kind": "Method"},
                ],
            },
            {"name": "helper", "kind": "Function"},
        ]

        def recurse(children):
            return group_symbols_by_kind(children, kind_key="kind", name_extractor=lambda s: s["name"], recurse=recurse)

        result = group_symbols_by_kind(symbols, kind_key="kind", name_extractor=lambda s: s["name"], recurse=recurse)
        assert dict(result) == {
            "Class": [{"MyClass": {"Method": ["method_a", "method_b"]}}],
            "Function": ["helper"],
        }

    def test_missing_kind_defaults_to_unknown(self) -> None:
        symbols = [{"name": "foo"}]
        result = group_symbols_by_kind(symbols, kind_key="kind", name_extractor=lambda s: s["name"])
        assert dict(result) == {"Unknown": ["foo"]}

    def test_custom_kind_key(self) -> None:
        symbols = [
            {"name_path": "MyClass", "type": "CLASS"},
            {"name_path": "helper", "type": "FUNCTION"},
        ]
        result = group_symbols_by_kind(symbols, kind_key="type", name_extractor=lambda s: s["name_path"].split("/")[-1])
        assert dict(result) == {
            "CLASS": ["MyClass"],
            "FUNCTION": ["helper"],
        }

    def test_children_without_recurse(self) -> None:
        """When recurse is None, symbols with children are still added by name (not recursed)."""
        symbols = [
            {
                "name": "MyClass",
                "kind": "Class",
                "children": [{"name": "method_a", "kind": "Method"}],
            },
        ]
        result = group_symbols_by_kind(symbols, kind_key="kind", name_extractor=lambda s: s["name"], recurse=None)
        assert dict(result) == {"Class": ["MyClass"]}


class TestGroupRefsByPathAndKind:
    def test_empty_list(self) -> None:
        result = group_refs_by_path_and_kind([], path_key="relative_path", kind_key="kind")
        assert result == {}

    def test_single_ref(self) -> None:
        refs = [
            {"relative_path": "src/foo.py", "kind": "Function", "name_path": "my_func", "content_around_reference": "..."},
        ]
        result = group_refs_by_path_and_kind(refs, path_key="relative_path", kind_key="kind")
        assert result == {
            "src/foo.py": {
                "Function": [{"name_path": "my_func", "content_around_reference": "..."}],
            },
        }

    def test_multiple_files_and_kinds(self) -> None:
        refs = [
            {"relative_path": "a.py", "kind": "Function", "name_path": "func_a"},
            {"relative_path": "a.py", "kind": "Class", "name_path": "ClassA"},
            {"relative_path": "b.py", "kind": "Function", "name_path": "func_b"},
            {"relative_path": "a.py", "kind": "Function", "name_path": "func_c"},
        ]
        result = group_refs_by_path_and_kind(refs, path_key="relative_path", kind_key="kind")
        assert result == {
            "a.py": {
                "Function": [{"name_path": "func_a"}, {"name_path": "func_c"}],
                "Class": [{"name_path": "ClassA"}],
            },
            "b.py": {
                "Function": [{"name_path": "func_b"}],
            },
        }

    def test_path_and_kind_removed_from_entries(self) -> None:
        refs = [
            {"relative_path": "x.py", "kind": "Method", "name_path": "foo", "info": "some info"},
        ]
        result = group_refs_by_path_and_kind(refs, path_key="relative_path", kind_key="kind")
        entry = result["x.py"]["Method"][0]
        assert "relative_path" not in entry
        assert "kind" not in entry
        assert entry == {"name_path": "foo", "info": "some info"}

    def test_custom_keys(self) -> None:
        """Test with JetBrains-style keys (type instead of kind)."""
        refs = [
            {"relative_path": "src/Main.java", "type": "CLASS", "name_path": "Main"},
        ]
        result = group_refs_by_path_and_kind(refs, path_key="relative_path", kind_key="type")
        assert result == {
            "src/Main.java": {
                "CLASS": [{"name_path": "Main"}],
            },
        }

    def test_missing_path_defaults_to_unknown(self) -> None:
        refs = [{"kind": "Function", "name_path": "foo"}]
        result = group_refs_by_path_and_kind(refs, path_key="relative_path", kind_key="kind")
        assert "unknown" in result

    def test_missing_kind_defaults_to_unknown(self) -> None:
        refs = [{"relative_path": "a.py", "name_path": "foo"}]
        result = group_refs_by_path_and_kind(refs, path_key="relative_path", kind_key="kind")
        assert result == {"a.py": {"Unknown": [{"name_path": "foo"}]}}
