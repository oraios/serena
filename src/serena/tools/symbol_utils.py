"""
Utility functions for compact symbol formatting used across symbol tools and JetBrains tools.
"""

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from typing import Any


def group_symbols_by_kind(
    symbols: Sequence[Mapping[str, Any]],
    kind_key: str,
    name_extractor: Callable[[Mapping[str, Any]], str],
    recurse: Callable[[Sequence[Mapping[str, Any]]], dict[str, list]] | None = None,
) -> dict[str, list]:
    """
    Group symbols by their kind, producing a compact representation.

    For symbols without children, the symbol is represented by just its name.
    For symbols with children, the symbol is represented as ``{name: children_grouped}``.

    :param symbols: list of symbol dictionaries
    :param kind_key: the key in each symbol dict that contains the kind/type
    :param name_extractor: callable to extract the display name from a symbol dict
    :param recurse: callable to recursively group children. If None, children are not
        recursively grouped (they remain as-is).
    :return: a dict mapping kind to a list of symbol representations
    """
    result: dict[str, list] = defaultdict(list)

    for symbol in symbols:
        kind = symbol.get(kind_key, "Unknown")
        name = name_extractor(symbol)
        children = symbol.get("children", [])

        if children and recurse is not None:
            children_dict = recurse(children)
            result[kind].append({name: children_dict})
        else:
            result[kind].append(name)

    return result


def group_refs_by_path_and_kind(
    ref_dicts: Sequence[Mapping[str, Any]],
    path_key: str,
    kind_key: str,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """
    Group referencing symbol dicts first by file path, then by kind.

    The *path_key* and *kind_key* fields are removed from individual entries
    because they are already encoded in the grouping structure.

    :param ref_dicts: list of referencing symbol dictionaries
    :param path_key: dictionary key that contains the relative file path
    :param kind_key: dictionary key that contains the symbol kind/type
    :return: ``{relative_path: {kind: [remaining_symbol_dict, ...]}}``
    """
    by_path: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for ref in ref_dicts:
        path = ref.get(path_key, "unknown")
        by_path[path].append(ref)

    result: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for path, refs in by_path.items():
        by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for ref in refs:
            kind = ref.get(kind_key, "Unknown")
            entry = {k: v for k, v in ref.items() if k != path_key and k != kind_key}
            by_kind[kind].append(entry)
        result[path] = dict(by_kind)

    return result
