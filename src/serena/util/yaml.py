import logging
import os
from enum import Enum
from typing import Any

from ruamel.yaml import YAML, CommentToken, StreamMark
from ruamel.yaml.comments import CommentedMap

from serena.constants import SERENA_FILE_ENCODING

log = logging.getLogger(__name__)


def _create_yaml(preserve_comments: bool = False) -> YAML:
    """
    Creates a YAML that can load/save with comments if preserve_comments is True.
    """
    typ = None if preserve_comments else "safe"
    result = YAML(typ=typ)
    result.preserve_quotes = preserve_comments
    return result


class YamlCommentNormalisation(Enum):
    NONE = "none"
    """
    No comment normalisation is performed.
    Comments are kept as parsed by ruamel.yaml.
    """
    LEADING = "leading"
    """
    Document is assumed to have leading comments only, i.e. comments before keys, only full-line comments.
    This normalisation achieves that comments are properly associated with keys as leading comments.
    """
    LEADING_WITH_CONVERSION_FROM_TRAILING = "leading_with_conversion_from_trailing"
    # NOTE: Normalisation for trailing comments was attempted but is extremely hard, because
    #  it is difficult to position the comments properly after values, especially for complex values.


DOC_COMMENT_INDEX_POST = 0
DOC_COMMENT_INDEX_PRE = 1

# item comment indices: (post key, pre key, post value, pre value)
ITEM_COMMENT_INDEX_BEFORE = 1  # (pre-key; must be a list of CommentToken at this index)
ITEM_COMMENT_INDEX_AFTER = 2  # (post-value; must be an instance of CommentToken at this index)


def load_yaml(path: str, comment_normalisation: YamlCommentNormalisation = YamlCommentNormalisation.NONE) -> CommentedMap:
    with open(path, encoding=SERENA_FILE_ENCODING) as f:
        yaml = _create_yaml(preserve_comments=True)
        commented_map: CommentedMap = yaml.load(f)
    normalise_yaml_comments(commented_map, comment_normalisation)
    return commented_map


def normalise_yaml_comments(commented_map: CommentedMap, comment_normalisation: YamlCommentNormalisation) -> None:
    def make_list(comment_entry: Any) -> list:
        if not isinstance(comment_entry, list):
            return [comment_entry]
        return comment_entry

    def make_unit(comment_entry: Any) -> Any:
        """
        Converts a list-valued comment entry into a single comment entry.
        """
        if isinstance(comment_entry, list):
            if len(comment_entry) == 0:
                return None
            elif len(comment_entry) == 1:
                return comment_entry[0]
            else:
                if all(isinstance(item, CommentToken) for item in comment_entry):
                    start_mark = StreamMark(name="", index=0, line=0, column=0)
                    comment_str = "".join(item.value for item in comment_entry)
                    if not comment_str.startswith("\n"):
                        comment_str = "\n" + comment_str
                    return CommentToken(value=comment_str, start_mark=start_mark, end_mark=None)
                else:
                    types = set(type(item) for item in comment_entry)
                    log.warning("Unhandled types in list-valued comment entry: %s; not updating entry", types)
                    return None
        else:
            return comment_entry

    match comment_normalisation:
        case YamlCommentNormalisation.NONE:
            pass
        case YamlCommentNormalisation.LEADING | YamlCommentNormalisation.LEADING_WITH_CONVERSION_FROM_TRAILING:
            # Comments are supposed to be leading comments (i.e., before a key and associated with the key).
            # When ruamel parses a YAML, however, comments belonging to a key may be stored as trailing
            # comments of the previous key or as a document-level comment.
            # Move them accordingly.
            keys = list(commented_map.keys())
            comment_items = commented_map.ca.items
            doc_comment = commented_map.ca.comment
            preceding_comment = None
            for i, key in enumerate(keys):
                current_comment = comment_items.get(key, [None] * 4)
                comment_items[key] = current_comment
                if current_comment[ITEM_COMMENT_INDEX_BEFORE] is None:
                    if i == 0 and doc_comment is not None and doc_comment[DOC_COMMENT_INDEX_PRE] is not None:
                        # move document pre-comment to leading comment of first key
                        current_comment[ITEM_COMMENT_INDEX_BEFORE] = make_list(doc_comment[DOC_COMMENT_INDEX_PRE])
                        doc_comment[DOC_COMMENT_INDEX_PRE] = None
                    elif preceding_comment is not None and preceding_comment[ITEM_COMMENT_INDEX_AFTER] is not None:
                        # move trailing comment of preceding key to leading comment of current key
                        current_comment[ITEM_COMMENT_INDEX_BEFORE] = make_list(preceding_comment[ITEM_COMMENT_INDEX_AFTER])
                        preceding_comment[ITEM_COMMENT_INDEX_AFTER] = None
                preceding_comment = current_comment

            if comment_normalisation == YamlCommentNormalisation.LEADING_WITH_CONVERSION_FROM_TRAILING:
                # Second pass: conversion of trailing comments
                # If a leading comment ends with "\n\n", i.e. it has an empty line between the comment and the key,
                # it was actually intended as a trailing comment for the preceding key, so we associate it with
                # the preceding key instead.
                preceding_comment = None
                for key in keys:
                    current_comment = comment_items.get(key, [None] * 4)
                    if current_comment[ITEM_COMMENT_INDEX_BEFORE] is not None:
                        token_list = make_list(current_comment[ITEM_COMMENT_INDEX_BEFORE])
                        if len(token_list) > 0:
                            last_token = token_list[-1]
                            if isinstance(last_token, CommentToken) and last_token.value.endswith("\n\n"):
                                # move comment to preceding key, removing the empty line
                                if preceding_comment is not None and yaml_comment_entry_is_empty(
                                    preceding_comment[ITEM_COMMENT_INDEX_BEFORE]
                                ):
                                    last_token.value = last_token.value[:-1]
                                    preceding_comment[ITEM_COMMENT_INDEX_BEFORE] = token_list
                                    current_comment[ITEM_COMMENT_INDEX_BEFORE] = None
                    preceding_comment = current_comment
        case _:
            raise ValueError(f"Unhandled comment normalisation: {comment_normalisation}")


def save_yaml(path: str, data: dict | CommentedMap, preserve_comments: bool = True) -> None:
    yaml = _create_yaml(preserve_comments)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=SERENA_FILE_ENCODING) as f:
        yaml.dump(data, f)


def yaml_comment_entry_is_empty(comment_entry: Any) -> bool:
    if comment_entry is None:
        return True
    elif isinstance(comment_entry, list):
        for item in comment_entry:
            if isinstance(item, CommentToken):
                if item.value.strip() != "":
                    return False
            else:
                return False
        return True
    elif isinstance(comment_entry, CommentToken):
        return comment_entry.value.strip() == ""
    else:
        return False


def transfer_missing_yaml_comments_by_index(
    source: CommentedMap, target: CommentedMap, indices: list[int], fully_missing_only: bool = False
) -> None:
    """
    :param source: the source, from which to transfer missing comments
    :param target: the target map, whose comments will be updated
    :param indices: list of comment indices to transfer
    :param fully_missing_only: if True, only transfer comments for keys that have no comment definition at all (newly added)
    """
    for key in target.keys():
        if key in source:
            source_comment = source.ca.items.get(key)
            if source_comment is None:
                continue
            target_comment = target.ca.items.get(key)
            if target_comment is None and fully_missing_only:
                # transfer full comment and we're done
                target.ca.items[key] = source_comment
            else:
                # initialise target comment if needed
                if target_comment is None:
                    target_comment = [None] * 4
                    target.ca.items[key] = target_comment
                # transfer missing comments at specified indices
                for index in indices:
                    if yaml_comment_entry_is_empty(target_comment[index]):
                        target_comment[index] = source_comment[index]


def transfer_missing_yaml_comments(
    source: CommentedMap, target: CommentedMap, comment_normalisation: YamlCommentNormalisation, fully_missing_only: bool = False
) -> None:
    """
    Transfers missing comments from source to target YAML.

    :param source: the source, from which to transfer missing comments
    :param target: the target map, whose comments will be updated.
    :param comment_normalisation: the comment normalisation to assume; if NONE, no comments are transferred
    :param fully_missing_only: if True, only transfer comments for keys that have no comment definition at all (newly added)
    """
    match comment_normalisation:
        case YamlCommentNormalisation.NONE:
            pass
        case YamlCommentNormalisation.LEADING | YamlCommentNormalisation.LEADING_WITH_CONVERSION_FROM_TRAILING:
            transfer_missing_yaml_comments_by_index(source, target, [ITEM_COMMENT_INDEX_BEFORE], fully_missing_only=fully_missing_only)
        case _:
            raise ValueError(f"Unhandled comment normalisation: {comment_normalisation}")
