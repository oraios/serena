from dataclasses import MISSING, Field
from typing import Any, cast


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
