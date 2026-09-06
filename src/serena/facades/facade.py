"""
The facade, i.e. the object through which REPL code accesses a group of related operations.
"""

# SPDX-License-Identifier: GPL-3.0-or-later

import inspect
from abc import ABC
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from serena.project import Project

if TYPE_CHECKING:
    from serena.agent import SerenaAgent

SUCCESS_RESULT = "OK"
"""the result returned by operations which have no result other than their success"""


class FacadeApi(ABC):
    """
    The implementation of a facade's functionality.

    API design principle: a member's name determines its visibility to the LLM.

      * Names without a leading underscore and without a trailing underscore (e.g. `find_symbol`) constitute the
        LLM-facing interface. Every such method of a concrete implementation is a candidate for exposure through
        a `Facade`; which of them are actually exposed is decided by the facade.
      * Names with a trailing underscore (e.g. `symbols_`, `to_dict_`) are public within Serena (e.g. for use by
        classic tools or other facade implementations) but are never exposed to the LLM. Use this for functionality
        which is not meant to be called from REPL code, in particular on the objects returned by API methods.
      * Names with a leading underscore are private, as usual.
    """

    def __init__(self, agent: "SerenaAgent", name: str, description: str) -> None:
        """
        :param agent: the agent providing access to the project and its resources
        :param name: the attribute name under which the facade is accessible from the REPL entrypoint
        :param description: a one-line description of the functionality offered by the facade
        """
        self._agent = agent
        self._name = name
        self._description = description

    def get_name_(self) -> str:
        return self._name

    def get_description_(self) -> str:
        return self._description

    def _get_project(self) -> Project:
        return self._agent.get_active_project_or_raise()


class FacadeMethod:
    """
    A method of a facade, which delegates to a method of the underlying implementation and which can be
    enabled or disabled; only enabled methods are accessible from REPL code.
    """

    def __init__(self, name: str, implementation: Callable[..., Any], enabled: bool = True) -> None:
        self.name = name
        self._implementation = implementation
        self.enabled = enabled

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._implementation(*args, **kwargs)

    def describe(self, facade_name: str) -> str:
        """
        :param facade_name: the name of the facade the method belongs to
        :return: the method's signature and documentation
        """
        signature = inspect.signature(self._implementation)
        doc = inspect.getdoc(self._implementation) or "(no documentation)"
        return f"{facade_name}.{self.name}{signature}\n{doc}\n"


class Facade:
    """
    A named group of related operations which an LLM can invoke from REPL code.
    """

    def __init__(self, name: str, description: str, methods: Iterable[FacadeMethod]) -> None:
        # NOTE: attributes are set via object.__setattr__ because __getattr__ is overridden
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_description", description)
        object.__setattr__(self, "_methods", {m.name: m for m in methods})

    @staticmethod
    def _is_exposable_member_name(name: str) -> bool:
        """
        :param name: the name of a member of a facade implementation
        :return: whether the member may be exposed through a facade, i.e. whether its name has neither a leading
            nor a trailing underscore (see `FacadeApi` for the naming principle)
        """
        return not name.startswith("_") and not name.endswith("_")

    @staticmethod
    def from_api(api: FacadeApi, enabled_methods: Iterable[str] | None = None) -> "Facade":
        """
        Creates a facade wrapping the given implementation.

        :param api: the implementation; each of its LLM-facing methods (see `_is_exposable_member_name`) becomes a facade method
        :param enabled_methods: the names of the methods to enable; if None, all methods are enabled
        :return: the facade
        """
        enabled = None if enabled_methods is None else set(enabled_methods)
        methods = [
            FacadeMethod(name, member, enabled=enabled is None or name in enabled)
            for name, member in inspect.getmembers(api, predicate=inspect.ismethod)
            if Facade._is_exposable_member_name(name)
        ]
        return Facade(api.get_name_(), api.get_description_(), methods)

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def enabled_method_names(self) -> list[str]:
        return [m.name for m in self._methods.values() if m.enabled]

    def get_method(self, method_name: str) -> FacadeMethod:
        """
        :param method_name: the name of the method
        :return: the method, regardless of whether it is enabled (e.g. for changing its enabled state)
        """
        if method_name not in self._methods:
            raise ValueError(f"Facade '{self._name}' has no method '{method_name}'")
        return self._methods[method_name]

    def _get_enabled_method(self, name: str) -> FacadeMethod | None:
        method = self._methods.get(name)
        return method if method is not None and method.enabled else None

    def _no_such_method_message(self, name: str) -> str:
        return f"Facade '{self._name}' has no method '{name}'. Available methods: {self.enabled_method_names}"

    def __getattr__(self, name: str) -> Any:
        # delegate attribute access to enabled methods only (called only if regular attribute lookup fails)
        method = self._get_enabled_method(name)
        if method is None:
            raise AttributeError(self._no_such_method_message(name))
        return method

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(f"Facade '{self._name}' is read-only")

    def describe(self) -> str:
        """
        :return: a description of the facade listing all of its enabled methods with their signatures and documentation
        """
        parts = [f"Facade '{self._name}': {self._description}", ""]
        for method in self._methods.values():
            if method.enabled:
                parts.append(method.describe(self._name))
        return "\n".join(parts)

    def describe_method(self, method_name: str) -> str:
        """
        :param method_name: the name of one of the facade's enabled methods
        :return: the method's signature and documentation
        """
        method = self._get_enabled_method(method_name)
        if method is None:
            raise ValueError(self._no_such_method_message(method_name))
        return method.describe(self._name)
