"""
The facade, i.e. the object through which REPL code accesses a group of related operations.
"""

# SPDX-License-Identifier: GPL-3.0-or-later

import inspect
import logging
from abc import ABC
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from serena.config.serena_config import ApiInclusionDefinition
from serena.project import Project

if TYPE_CHECKING:
    from serena.agent import SerenaAgent
    from serena.code_editor import CodeEditor
    from serena.tools import Tool

log = logging.getLogger(__name__)
TCallable = TypeVar("TCallable", bound=Callable[..., Any])

SUCCESS_RESULT = "OK"
"""the result returned by operations which have no result other than their success"""


@dataclass(kw_only=True, frozen=True)
class FacadeMethodInfo:
    """
    The metadata of a method exposed through a facade (see `facade_method`), mirroring the tool markers.
    """

    name: str
    """the name of the method"""
    optional: bool = False
    """whether the method is disabled by default and must be enabled explicitly"""
    beta: bool = False
    """whether the method is in beta (not yet fully stable)"""
    can_edit: bool = False
    """whether the method can modify the codebase (relevant for read-only contexts)"""
    corresponding_tool: "type[Tool] | None" = None
    """the classic tool offering the same functionality, if any"""

    def get_corresponding_tool_name(self) -> str | None:
        """
        :return: the name of the corresponding tool, or None if there is none
        """
        return self.corresponding_tool.get_name_from_cls() if self.corresponding_tool is not None else None


_FACADE_METHOD_INFO_ATTR = "__facade_method_info__"


def facade_method(
    *, optional: bool = False, beta: bool = False, can_edit: bool = False, corresponding_tool: "type[Tool] | None" = None
) -> Callable[[TCallable], TCallable]:
    """
    Marks a method of a `FacadeApi` as exposed through the facade, attaching the given metadata.
    The decorator only annotates the method (it does not wrap it), such that signature and docstring remain intact.

    :param optional: whether the method is disabled by default and must be enabled explicitly
    :param beta: whether the method is in beta
    :param can_edit: whether the method can modify the codebase
    :param corresponding_tool: the classic tool offering the same functionality, if any
    :return: the decorator
    """

    def decorator(method: TCallable) -> TCallable:
        info = FacadeMethodInfo(
            name=method.__name__, optional=optional, beta=beta, can_edit=can_edit, corresponding_tool=corresponding_tool
        )
        setattr(method, _FACADE_METHOD_INFO_ATTR, info)
        return method

    return decorator


def get_facade_method_info(method: Callable[..., Any]) -> FacadeMethodInfo | None:
    """
    :param method: a (bound or unbound) method
    :return: the metadata attached via `facade_method`, or None if the method is not exposed
    """
    return getattr(method, _FACADE_METHOD_INFO_ATTR, None)


class FacadeApi(ABC):
    """
    The implementation of a facade's functionality.

    API design principles:

      * A method is exposed to the LLM if and only if it is decorated with `facade_method`, which also carries
        the method's metadata (optional, beta, can_edit). Undecorated methods are never exposed, regardless of their name.
      * On the objects returned by API methods (which are not decorated), the name determines visibility:
        names with a trailing underscore (e.g. `symbols_`, `to_dict_`) are public within Serena (e.g. for use by
        classic tools or other facade implementations) but are not meant to be called from REPL code, whereas
        names without leading or trailing underscore constitute the LLM-facing interface.
        The same convention applies to non-exposed helper methods of API classes.
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

    def _create_code_editor(self) -> "CodeEditor":
        """
        :return: a code editor for the active project, using the active language backend
        """
        from serena.code_editor import JetBrainsCodeEditor, LanguageServerCodeEditor
        from serena.symbol import LanguageServerSymbolRetriever

        project = self._get_project()
        backend = self._agent.get_language_backend()
        if backend.is_lsp():
            return LanguageServerCodeEditor(LanguageServerSymbolRetriever(project))
        elif backend.is_jetbrains():
            return JetBrainsCodeEditor(project)
        else:
            raise ValueError(f"Unsupported language backend: {backend}")


class FacadeMethod:
    """
    A method of a facade, which delegates to a method of the underlying implementation and which can be
    enabled or disabled; only enabled methods are accessible from REPL code.
    """

    def __init__(self, name: str, implementation: Callable[..., Any], info: FacadeMethodInfo, enabled: bool) -> None:
        """
        :param name: the method's name
        :param implementation: the implementation to delegate to
        :param info: the method's metadata
        :param enabled: whether the method is initially enabled
        """
        self.name = name
        self._implementation = implementation
        self.info = info
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


class ApiScope:
    """
    The scope of APIs available to the LLM, i.e. which facade methods are enabled, as determined by
    applying a sequence of inclusion/exclusion definitions (from the global configuration, the context,
    the active modes and the project configuration) to the methods' default enablement.
    """

    class FacadeScope:
        """
        The scope of a single facade: whether the facade as a whole is included, and which of its methods
        were explicitly included/excluded (a method is never in both sets).
        If the facade is not included, it is opt-in, i.e. only explicitly included methods are enabled.
        """

        def __init__(self) -> None:
            self.is_included = True
            self.method_inclusions: set[str] = set()
            self.method_exclusions: set[str] = set()

        def exclude_facade(self) -> None:
            self.is_included = False
            self.method_inclusions = set()
            self.method_exclusions = set()

        def include_facade(self) -> None:
            self.is_included = True

        def exclude_method(self, method_name: str) -> None:
            self.method_inclusions.discard(method_name)
            self.method_exclusions.add(method_name)

        def include_method(self, method_name: str) -> None:
            self.method_exclusions.discard(method_name)
            self.method_inclusions.add(method_name)

    def __init__(self) -> None:
        self._facade_scopes: dict[str, ApiScope.FacadeScope] = {}
        self._editing_excluded = False

    def _get_facade_scope(self, facade_name: str) -> "ApiScope.FacadeScope":
        if facade_name not in self._facade_scopes:
            self._facade_scopes[facade_name] = ApiScope.FacadeScope()
        return self._facade_scopes[facade_name]

    def process(self, definition: ApiInclusionDefinition) -> None:
        """
        Applies the given definition, exclusions first, then inclusions (such that inclusions take precedence
        within a definition; across definitions, later definitions take precedence).

        :param definition: the definition to apply
        """

        def apply(api_ref: str, *, excluded: bool) -> None:
            components = api_ref.split(".")
            if len(components) > 2:
                log.warning("Ignoring invalid API reference '%s' in %s (expected 'facade' or 'facade.method')", api_ref, definition)
                return
            facade_scope = self._get_facade_scope(components[0])
            if len(components) == 1:
                facade_scope.exclude_facade() if excluded else facade_scope.include_facade()
            else:
                facade_scope.exclude_method(components[1]) if excluded else facade_scope.include_method(components[1])

        for api_exclusion in definition.excluded_apis:
            apply(api_exclusion, excluded=True)
        for api_inclusion in definition.included_apis:
            apply(api_inclusion, excluded=False)

    def exclude_editing(self) -> None:
        """
        Excludes all methods which can edit the codebase (read-only operation), regardless of other inclusions.
        """
        self._editing_excluded = True

    def is_facade_enabled(self, facade_name: str) -> bool:
        facade_scope = self._get_facade_scope(facade_name)
        return facade_scope.is_included or len(facade_scope.method_inclusions) > 0

    def is_method_enabled(self, facade_name: str, method_info: FacadeMethodInfo) -> bool:
        """
        :param facade_name: the name of the facade
        :param method_info: the method's metadata
        :return: whether the method is enabled: optional methods (and all methods of an excluded facade) must be
            explicitly included, other methods are enabled unless explicitly excluded; if editing is excluded,
            editing methods are always disabled
        """
        if self._editing_excluded and method_info.can_edit:
            return False
        facade_scope = self._get_facade_scope(facade_name)
        if method_info.optional or not facade_scope.is_included:
            return method_info.name in facade_scope.method_inclusions
        else:
            return method_info.name not in facade_scope.method_exclusions


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
    def from_api(api: FacadeApi, api_scope: ApiScope) -> "Facade":
        """
        Creates a facade wrapping the given implementation.

        :param api: the implementation; each of its methods decorated with `facade_method` becomes a facade method
        :param api_scope: API scope definition determining which methods are enabled
        :return: the facade
        """
        facade_name = api.get_name_()
        methods = []
        for name, member in inspect.getmembers(api, predicate=inspect.ismethod):
            method_info = get_facade_method_info(member)
            if method_info is None:
                continue
            is_enabled = api_scope.is_method_enabled(facade_name, method_info)
            methods.append(FacadeMethod(name, member, method_info, enabled=is_enabled))
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
