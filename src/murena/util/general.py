import os
from dataclasses import MISSING, Field
from typing import Any, Literal, cast, overload

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from murena.constants import MURENA_FILE_ENCODING


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
    with open(path, encoding=MURENA_FILE_ENCODING) as f:
        yaml = _create_YAML(preserve_comments)
        return yaml.load(f)


def save_yaml(path: str, data: dict | CommentedMap, preserve_comments: bool = False) -> None:
    yaml = _create_YAML(preserve_comments)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=MURENA_FILE_ENCODING) as f:
        yaml.dump(data, f)


def get_dataclass_default(cls: type, field_name: str) -> Any:
    """
    Gets the default value of a dataclass field.

    :param cls: The dataclass type.
    :param field_name: The name of the field.
    :return: The default value of the field (either from default or default_factory).
    """
    field = cast(Field, cls.__dataclass_fields__[field_name])  # type: ignore[attr-defined]

    if field.default is not MISSING:
        return field.default

    if field.default_factory is not MISSING:  # default_factory is a function
        return field.default_factory()

    raise AttributeError(f"{field_name} has no default")
