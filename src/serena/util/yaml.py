import os
from enum import Enum
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from serena.constants import SERENA_FILE_ENCODING


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
    LEADING = "leading"
    """
    Document is assumed to have leading comments only, i.e. comments before keys.
    This normalisation achieves that comments are properly associated with keys as leading comments.
    """


DOC_COMMENT_INDEX_POST = 0
DOC_COMMENT_INDEX_PRE = 1

# item comment indices: (post key, pre key, post value, pre value)
ITEM_COMMENT_INDEX_BEFORE = 1  # (pre-key; must be a list at this index)
ITEM_COMMENT_INDEX_AFTER = 2  # (post-value; typically no list at this index)


def load_yaml(path: str, comment_normalisation: YamlCommentNormalisation = YamlCommentNormalisation.NONE) -> CommentedMap:
    with open(path, encoding=SERENA_FILE_ENCODING) as f:
        yaml = _create_yaml(preserve_comments=True)
        commented_map: CommentedMap = yaml.load(f)

    def make_list(comment_entry: Any) -> list:
        if not isinstance(comment_entry, list):
            return [comment_entry]
        return comment_entry

    match comment_normalisation:
        case YamlCommentNormalisation.NONE:
            pass
        case YamlCommentNormalisation.LEADING:
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
        case _:
            raise ValueError(f"Unhandled comment normalisation: {comment_normalisation}")

    return commented_map


def save_yaml(path: str, data: dict | CommentedMap, preserve_comments: bool = True) -> None:
    yaml = _create_yaml(preserve_comments)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=SERENA_FILE_ENCODING) as f:
        yaml.dump(data, f)


def transfer_missing_yaml_comments_by_index(source: CommentedMap, target: CommentedMap, indices: list[int]) -> None:
    """
    :param source: the source, from which to transfer missing comments
    :param target: the target map, whose comments will be updated
    :param indices: list of comment indices to transfer
    """
    for key in target.keys():
        if key in source:
            source_comment = source.ca.items.get(key)
            if source_comment is None:
                continue
            target_comment = target.ca.items.get(key, [None, None, None, None])
            target.ca.items[key] = target_comment
            for index in indices:
                if target_comment[index] is None:
                    target_comment[index] = source_comment[index]


def transfer_missing_yaml_comments(source: CommentedMap, target: CommentedMap, comment_normalisation: YamlCommentNormalisation) -> None:
    """
    Transfers missing comments from source to target YAML.

    :param source: the source, from which to transfer missing comments
    :param target: the target map, whose comments will be updated.
    :param comment_normalisation: the comment normalisation to assume; if NONE, no comments are transferred
    """
    match comment_normalisation:
        case YamlCommentNormalisation.NONE:
            pass
        case YamlCommentNormalisation.LEADING:
            transfer_missing_yaml_comments_by_index(source, target, [ITEM_COMMENT_INDEX_BEFORE])
        case _:
            raise ValueError(f"Unhandled comment normalisation: {comment_normalisation}")
