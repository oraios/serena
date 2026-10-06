# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Any


def singleton(cls: type[Any]) -> Any:
    instance = None

    def get_instance(*args: Any, **kwargs: Any) -> Any:
        nonlocal instance
        if instance is None:
            instance = cls(*args, **kwargs)
        return instance

    return get_instance
