from typing import Any


# duplicate of interprompt.class_decorators
# We don't want to depend on interprompt for this in serena, so we duplicate it here
def singleton(cls: type[Any]) -> Any:
    instance = None

    def get_instance(*args: Any, **kwargs: Any) -> Any:
        nonlocal instance
        if instance is None:
            instance = cls(*args, **kwargs)
        return instance

    return get_instance
