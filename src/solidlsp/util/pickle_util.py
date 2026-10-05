import builtins
import pickle
from collections.abc import Sequence
from typing import Any


class _SafeUnpickler(pickle.Unpickler):
    _SAFE_BUILTINS = {
        "bool",
        "bytes",
        "bytearray",
        "complex",
        "dict",
        "float",
        "frozenset",
        "int",
        "list",
        "range",
        "set",
        "slice",
        "str",
        "tuple",
    }

    def __init__(self, file, allowed_classes: Sequence[type] = ()):
        super().__init__(file)

        self._allowed_globals = {("builtins", name): getattr(builtins, name) for name in self._SAFE_BUILTINS}

        for cls in allowed_classes:
            self._allowed_globals[(cls.__module__, cls.__qualname__)] = cls

    def find_class(self, module, name):
        try:
            return self._allowed_globals[(module, name)]
        except KeyError:
            raise pickle.UnpicklingError(f"forbidden global: {module}.{name}") from None

    def persistent_load(self, pid):
        raise pickle.UnpicklingError("persistent IDs are not allowed")


class SafePickleLoader:
    def __init__(self, allowed_classes: Sequence[type] = ()):
        self._allowed_classes = allowed_classes

    def load(self, path: str) -> Any:
        with open(path, "rb") as f:
            unpickler = _SafeUnpickler(f, self._allowed_classes)
            return unpickler.load()
