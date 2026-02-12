"""
Utility functions for compact symbol formatting used across symbol tools and JetBrains tools.
"""

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from typing import Any


def group_symbols(
    symbols: Sequence[Mapping[str, Any]],
    group_keys: list[str],
    name_extractor: Callable[[Mapping[str, Any]], str] | None = None,
    recurse_children: bool = False,
) -> dict[str, Any]:
    """
    Group symbol dicts by one or more keys, producing a nested dict structure.

    When *name_extractor* is provided the output uses a **compact** representation:
    leaf symbols are represented by just their name (string), and symbols with
    children are represented as ``{name: grouped_children}`` (only when
    *recurse_children* is ``True``).

    When *name_extractor* is ``None`` the output keeps remaining dict entries
    intact (all *group_keys* are stripped from each entry).

    :param symbols: list of symbol dictionaries
    :param group_keys: ordered list of dict keys to group by.  The first key
        creates the outermost grouping level, the second key the next, etc.
    :param name_extractor: optional callable to extract a display name from a
        symbol dict.  When given, enables compact mode.
    :param recurse_children: only used in compact mode.  If ``True``,
        recursively apply the same grouping to ``children`` entries.
    :return: a nested dict whose depth equals ``len(group_keys)``.  Leaf values
        are lists of symbol representations.
    """
    if not group_keys:
        raise ValueError("group_keys must not be empty")

    return _group_symbols_recursive(
        symbols,
        group_keys=group_keys,
        all_group_keys=set(group_keys),
        name_extractor=name_extractor,
        recurse_children=recurse_children,
    )


def _group_symbols_recursive(
    symbols: Sequence[Mapping[str, Any]],
    group_keys: list[str],
    all_group_keys: set[str],
    name_extractor: Callable[[Mapping[str, Any]], str] | None,
    recurse_children: bool,
) -> dict[str, Any]:
    key = group_keys[0]
    remaining_keys = group_keys[1:]

    grouped: dict[str, list] = defaultdict(list)
    for symbol in symbols:
        group_value = symbol.get(key, "Unknown")
        grouped[group_value].append(symbol)

    if remaining_keys:
        return {
            group_value: _group_symbols_recursive(
                items,
                group_keys=remaining_keys,
                all_group_keys=all_group_keys,
                name_extractor=name_extractor,
                recurse_children=recurse_children,
            )
            for group_value, items in grouped.items()
        }

    # Leaf level - build the final list for each group value
    result: dict[str, list] = {}
    for group_value, items in grouped.items():
        if name_extractor is not None:
            entries: list = []
            for symbol in items:
                name = name_extractor(symbol)
                children = symbol.get("children", [])
                if children and recurse_children:
                    children_dict = _group_symbols_recursive(
                        children,
                        group_keys=group_keys,
                        all_group_keys=all_group_keys,
                        name_extractor=name_extractor,
                        recurse_children=True,
                    )
                    entries.append({name: children_dict})
                else:
                    entries.append(name)
            result[group_value] = entries
        else:
            result[group_value] = [{k: v for k, v in s.items() if k not in all_group_keys} for s in items]

    return result
