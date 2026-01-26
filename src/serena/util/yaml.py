import os
from typing import Literal, overload

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from serena.constants import SERENA_FILE_ENCODING


def _create_YAML(preserve_comments: bool = False) -> YAML:
    """
    Creates a YAML that can load/save with comments if preserve_comments is True.
    """
    typ = None if preserve_comments else "safe"
    result = YAML(typ=typ)
    result.preserve_quotes = preserve_comments
    return result


@overload
def load_yaml(path: str, preserve_comments: Literal[False]) -> dict: ...
@overload
def load_yaml(path: str, preserve_comments: Literal[True]) -> CommentedMap: ...
def load_yaml(path: str, preserve_comments: bool = False) -> dict | CommentedMap:
    with open(path, encoding=SERENA_FILE_ENCODING) as f:
        yaml = _create_YAML(preserve_comments)
        return yaml.load(f)


def save_yaml(path: str, data: dict | CommentedMap, preserve_comments: bool = False) -> None:
    yaml = _create_YAML(preserve_comments)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=SERENA_FILE_ENCODING) as f:
        yaml.dump(data, f)
