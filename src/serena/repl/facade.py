"""
The facade, i.e. the object through which REPL code accesses a group of related operations.
"""

# SPDX-License-Identifier: GPL-3.0-or-later

import inspect
import logging
import re
import typing
from abc import ABC
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeVar

import typing_extensions

from serena.config.serena_config import ApiInclusionDefinition
from serena.project import Project

from .representable import RepresentableViaRenderer

if TYPE_CHECKING:
    from serena.agent import SerenaAgent
    from serena.code_editor import CodeEditor
    from serena.tools import Tool

    from .external_project import ExternalProjectExecution

log = logging.getLogger(__name__)
TCallable = TypeVar("TCallable", bound=Callable[..., Any])

SUCCESS_RESULT = "OK"
"""the result returned by operations which have no result other than their success"""


def format_annotation(annotation: Any) -> str:
    """
    :param annotation: a type annotation (or a signature/annotation string)
    :return: the annotation rendered without module paths (e.g. `list[LanguageServerSymbol]`), such that type names
        match the names by which the types can be looked up
    """
    text = annotation if isinstance(annotation, str) else inspect.formatannotation(annotation)
    return re.sub(r"\b(?:[A-Za-z_]\w*\.)+([A-Za-z_]\w*)", r"\1", text)


def format_signature(callable_: Callable[..., Any]) -> str:
    """
    :param callable_: the callable
    :return: the signature rendered without module paths in annotations
    """
    return format_annotation(str(inspect.signature(callable_)))


def extract_referenced_classes(annotation: Any) -> list[type]:
    """
    :param annotation: a (resolved) type annotation
    :return: the user-defined classes appearing in the annotation (recursively, e.g. in `list[X] | None`), in order of
        appearance; builtins, typing constructs and classes from the standard library are excluded
    """
    classes: list[type] = []

    def visit(a: Any) -> None:
        if isinstance(a, type):
            module = getattr(a, "__module__", "")
            if module not in ("builtins", "typing", "collections.abc", "abc") and not module.startswith("_") and a not in classes:
                classes.append(a)
        for arg in typing.get_args(a):
            visit(arg)

    visit(annotation)
    return classes


def get_annotated_classes(callable_: Callable[..., Any]) -> list[type]:
    """
    :param callable_: a function or method
    :return: the user-defined classes appearing in the annotations of its parameters and return type
    """
    try:
        hints = typing.get_type_hints(callable_)
    except Exception:  # unresolvable forward references
        return []
    classes: list[type] = []
    for hint in hints.values():
        classes.extend(c for c in extract_referenced_classes(hint) if c not in classes)
    return classes


@dataclass
class ReferencedType:
    """
    A type that is referenced by a facade's methods (returned by them, contained in their results or used as a parameter
    type), whose interface the LLM can inspect via `info`.
    All types reachable through annotations are discovered automatically; an explicit declaration is needed only in order
    to curate the type's presentation (the members to describe, inclusion in the facade's description).
    """

    cls: type
    """the type"""
    provide_info_with_facade: bool = False
    """whether the type's full description is included in the facade's description (rather than just its name)"""
    members: Sequence[str] | None = None
    """
    the LLM-facing members (attributes, properties, methods) to describe; if None, all members admitted by the naming
    convention (no leading or trailing underscore) which are documented are described. Explicitly listed methods are
    described even if undocumented, as the listing is the documentation decision.
    """

    _CAPABILITIES: typing.ClassVar[dict[str, str]] = {
        "__len__": "len()",
        "__iter__": "iteration",
        "__getitem__": "indexing",
        "__enter__": "use in a `with` statement",
    }

    @property
    def name(self) -> str:
        return self.cls.__name__

    def _get_member_names(self) -> list[str]:
        if self.members is not None:
            return list(self.members)
        names = set(typing.get_type_hints(self.cls))
        names.update(n for n in dir(self.cls) if not n.startswith("_"))
        # exclude the representation mechanism, which is not meant to be used from REPL code
        names.difference_update(dir(RepresentableViaRenderer))
        return sorted(n for n in names if not n.startswith("_") and not n.endswith("_"))

    def get_referenced_classes(self) -> list[type]:
        """
        :return: the user-defined classes appearing in the annotations of the described members (attributes, properties,
            method parameters and return types), in order of appearance (each class at most once, excluding the type itself)
        """
        if self.is_enum():
            return []
        classes: list[type] = []
        type_hints = typing.get_type_hints(self.cls)
        if self.is_typed_dict():
            for hint in type_hints.values():
                classes.extend(c for c in extract_referenced_classes(hint) if c is not self.cls and c not in classes)
            return classes
        for member_name in self._get_member_names():
            member = inspect.getattr_static(self.cls, member_name, None)
            if isinstance(member, property) and member.fget is not None:
                found = get_annotated_classes(member.fget)
            elif inspect.isfunction(member):
                found = get_annotated_classes(member)
            elif member_name in type_hints:
                found = extract_referenced_classes(type_hints[member_name])
            else:
                found = []
            classes.extend(c for c in found if c is not self.cls and c not in classes)
        return classes

    def is_enum(self) -> bool:
        return isinstance(self.cls, type) and issubclass(self.cls, Enum)

    def is_typed_dict(self) -> bool:
        # NOTE: TypedDicts defined via typing_extensions are not recognised by typing.is_typeddict
        return typing.is_typeddict(self.cls) or typing_extensions.is_typeddict(self.cls)

    def _describe_typed_dict(self) -> str:
        parts = [f"type {self.name} (a dict with the following keys)"]
        if self.cls.__doc__ and not self.cls.__doc__.startswith(self.name + "("):  # NOTE: the default docstring is uninformative
            parts.append(f"  {inspect.cleandoc(self.cls.__doc__).replace(chr(10), chr(10) + '  ')}")
        type_hints = typing.get_type_hints(self.cls)
        member_names = self.members if self.members is not None else list(type_hints)
        parts.append(
            "keys:\n" + "\n".join(f"  {name}: {format_annotation(type_hints[name])}" for name in member_names if name in type_hints)
        )
        return "\n".join(parts) + "\n"

    def _describe_enum(self) -> str:
        parts = [f"enum {self.name}"]
        if self.cls.__doc__:
            parts.append(f"  {inspect.cleandoc(self.cls.__doc__).replace(chr(10), chr(10) + '  ')}")
        parts.append("members:\n" + "\n".join(f"  {self.name}.{member.name} = {member.value!r}" for member in self.cls))  # type: ignore[attr-defined]
        return "\n".join(parts) + "\n"

    @staticmethod
    def _first_doc_line(obj: Any) -> str:
        doc = inspect.getdoc(obj) or ""
        first_line = doc.splitlines()[0] if doc else ""
        return first_line.removeprefix(":return:").strip()

    def describe(self) -> str:
        """
        :return: the type's documentation: its docstring, attributes/properties with their types and methods with their
            signatures and documentation; for enums, the members with their values
        """
        if self.is_enum():
            return self._describe_enum()
        if self.is_typed_dict():
            return self._describe_typed_dict()
        attributes: list[str] = []
        methods: list[str] = []
        type_hints = typing.get_type_hints(self.cls)
        for member_name in self._get_member_names():
            member = inspect.getattr_static(self.cls, member_name, None)
            if isinstance(member, property):
                fget = member.fget
                annotation = inspect.signature(fget).return_annotation if fget is not None else inspect.Signature.empty
                type_str = f": {format_annotation(annotation)}" if annotation is not inspect.Signature.empty else ""
                doc = self._first_doc_line(member)
                attributes.append(f"  {member_name}{type_str}" + (f"  # {doc}" if doc else ""))
            elif inspect.isfunction(member):
                doc = inspect.getdoc(member)
                if doc is None and self.members is None:
                    continue
                signature = format_signature(member).replace("(self, ", "(", 1).replace("(self)", "()", 1)
                methods.append(f"  {member_name}{signature}" + (f"\n    {doc.replace(chr(10), chr(10) + '    ')}" if doc else ""))
            elif member_name in type_hints:
                attributes.append(f"  {member_name}: {format_annotation(type_hints[member_name])}")
            else:
                attributes.append(f"  {member_name}")

        # assemble the description
        parts = [f"type {self.name}"]
        if self.cls.__doc__:  # NOTE: the class' own docstring (inspect.getdoc would fall back to base class docstrings)
            doc = inspect.cleandoc(self.cls.__doc__)
            parts.append(f"  {doc.replace(chr(10), chr(10) + '  ')}")
        if attributes:
            parts.append("attributes:\n" + "\n".join(attributes))
        if methods:
            parts.append("methods:\n" + "\n".join(methods))
        capabilities = [text for dunder, text in self._CAPABILITIES.items() if dunder in dir(self.cls) and dunder not in dir(object)]
        if capabilities:
            parts.append("supports: " + ", ".join(capabilities))
        return "\n".join(parts) + "\n"


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
    niche: bool = False
    """
    whether the method is rarely needed, such that the facade's description only summarises it (first line of its
    documentation and a pointer to its full documentation) in order to keep the description compact
    """
    uses_project_server: bool = False
    """
    whether the method requires the project's language servers and must therefore be executed in the project server
    when an external project is queried (see `ExternalProjectContext`).
    Edit operations are always executed in the project server, regardless of this flag, since they implicitly
    use the CodeEditor, which requires language servers when using the LSP backend.
    Polymorphic edit operations therefore must not set this flag to True.
    """
    corresponding_tool: "type[Tool] | None" = None
    """the classic tool offering the same functionality, if any"""

    def get_corresponding_tool_name(self) -> str | None:
        """
        :return: the name of the corresponding tool, or None if there is none
        """
        return self.corresponding_tool.get_name_from_cls() if self.corresponding_tool is not None else None


_FACADE_METHOD_INFO_ATTR = "__facade_method_info__"


def facade_method(
    *,
    optional: bool = False,
    beta: bool = False,
    can_edit: bool = False,
    niche: bool = False,
    uses_project_server: bool = False,
    corresponding_tool: "type[Tool] | None" = None,
) -> Callable[[TCallable], TCallable]:
    """
    Marks a method of a `FacadeApi` as exposed through the facade, attaching the given metadata.
    The decorator only annotates the method (it does not wrap it), such that signature and docstring remain intact.

    :param optional: whether the method is disabled by default and must be enabled explicitly
    :param beta: whether the method is in beta
    :param can_edit: whether the method can modify the codebase
    :param niche: whether the method is rarely needed (its documentation is then only summarised in the facade's description)
    :param uses_project_server: whether the method must be executed remotely in the project server when an external project is queried
    :param corresponding_tool: the classic tool offering the same functionality, if any
    :return: the decorator
    """

    def decorator(method: TCallable) -> TCallable:
        info = FacadeMethodInfo(
            name=method.__name__,
            optional=optional,
            beta=beta,
            can_edit=can_edit,
            niche=niche,
            uses_project_server=uses_project_server,
            corresponding_tool=corresponding_tool,
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

    def __init__(self, agent: "SerenaAgent", name: str, description: str, types: Sequence[ReferencedType] = ()) -> None:
        """
        :param agent: the agent providing access to the project and its resources
        :param name: the attribute name under which the facade is accessible from the REPL entrypoint
        :param description: a one-line description of the functionality offered by the facade
        :param types: declarations for referenced types whose presentation is to be curated (see `ReferencedType`);
            types reachable through annotations need not be declared in order to be documentable
        """
        self._agent = agent
        self._name = name
        self._description = description
        self._types = list(types)

    def get_name_(self) -> str:
        return self._name

    def get_description_(self) -> str:
        return self._description

    def get_referenced_types_(self) -> list[ReferencedType]:
        return self._types

    def _get_project(self) -> Project:
        return self._agent.get_active_project_or_raise()

    def _create_code_editor(self) -> "CodeEditor":
        """
        :return: a code editor for the active project, using the active language backend
        """
        project = self._get_project()
        backend = self._agent.get_language_backend()
        return backend.create_code_editor(project)


class FacadeMethod:
    """
    A method of a facade, which delegates to a method of the underlying implementation and which can be
    enabled or disabled; only enabled methods are accessible from REPL code.
    """

    def __init__(self, parent: "Facade", implementation: Callable[..., Any], info: FacadeMethodInfo, enabled: bool) -> None:
        """
        :param parent: the facade the method belongs to
        :param implementation: the implementation to delegate to
        :param info: the method's metadata (including the method's name)
        :param enabled: whether the method is initially enabled
        """
        self.parent = parent
        self._implementation = implementation
        self.info = info
        self.enabled = enabled

    @property
    def name(self) -> str:
        return self.info.name

    @property
    def facade_name(self) -> str:
        return self.parent.name

    @property
    def qualified_name(self) -> str:
        """
        :return: the name under which the method is accessible from REPL code (facade name and method name)
        """
        return f"{self.facade_name}.{self.name}"

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        external_project_execution = self.parent.get_external_project_()
        if external_project_execution is not None:
            external_project_execution.check_call_permission(self)
            if external_project_execution.is_called_remotely(self):
                return external_project_execution.call_remotely(self.facade_name, self.name, args, kwargs)
        return self._implementation(*args, **kwargs)

    def get_implementation_(self) -> Callable[..., Any]:
        return self._implementation

    def get_referenced_return_types(self) -> list[ReferencedType]:
        """
        :return: the types referenced by the facade which appear in the method's return type annotation
        """
        return_annotation = format_annotation(inspect.signature(self._implementation).return_annotation)
        return self._find_referenced_types(return_annotation)

    def get_referenced_parameter_types(self) -> list[ReferencedType]:
        """
        :return: the types referenced by the facade which appear in the annotations of the method's parameters
        """
        parameters = inspect.signature(self._implementation).parameters.values()
        return self._find_referenced_types(" ".join(format_annotation(p.annotation) for p in parameters))

    def _find_referenced_types(self, annotation_text: str) -> list[ReferencedType]:
        return [t for t in self.parent.get_types() if re.search(rf"\b{re.escape(t.name)}\b", annotation_text)]

    def get_summary(self) -> str:
        """
        :return: the first line of the method's documentation
        """
        doc = inspect.getdoc(self._implementation)
        return doc.splitlines()[0] if doc else "(no documentation)"

    def describe(self) -> str:
        """
        :return: the method's signature and documentation, with pointers to the documentation of the referenced types
            appearing in its return type and parameter annotations
        """
        signature = format_signature(self._implementation)
        doc = inspect.getdoc(self._implementation) or "(no documentation)"
        text = f"{self.qualified_name}{signature}\n{doc}\n"
        referenced = self.get_referenced_return_types()
        referenced += [t for t in self.get_referenced_parameter_types() if t not in referenced]
        if referenced:
            pointers = ", ".join(f'`s.info("{t.name}")`' for t in referenced)
            text += f"Type documentation: {pointers}\n"
        return text

    def describe_summary(self) -> str:
        """
        :return: the method's name and the first line of its documentation, with a pointer to its full documentation
        """
        return f'{self.qualified_name}: {self.get_summary()} [full documentation: `s.info("{self.qualified_name}")`]\n'


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
            self._is_included: bool | None = None
            self.method_inclusions: set[str] = set()
            self.method_exclusions: set[str] = set()

        def exclude_facade(self) -> None:
            self._is_included = False
            self.method_inclusions = set()
            self.method_exclusions = set()

        def include_facade(self) -> None:
            self._is_included = True

        def is_facade_included(self, is_facade_optional: bool) -> bool:
            if is_facade_optional:
                return self._is_included is True
            else:
                return self._is_included is not False

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

    def is_method_enabled(self, facade_name: str, method_info: FacadeMethodInfo, is_facade_optional: bool) -> bool:
        """
        :param facade_name: the name of the facade
        :param method_info: the method's metadata
        :param is_facade_optional: whether the facade is optional (disabled by default and must be enabled explicitly)
        :return: whether the method is enabled: optional methods (and all methods of a facade which is not included,
            i.e. an excluded facade or an optional facade that was not explicitly included) must be explicitly
            included, other methods are enabled unless explicitly excluded; if editing is excluded, editing
            methods are always disabled
        """
        if self._editing_excluded and method_info.can_edit:
            return False
        facade_scope = self._get_facade_scope(facade_name)
        # A method that would be disabled because the facade it is part of is not included
        # or the method itself is optional must be explicitly included in order to be enabled.
        if not facade_scope.is_facade_included(is_facade_optional) or method_info.optional:
            return method_info.name in facade_scope.method_inclusions
        # A method that is not optional and whose facade is included is enabled unless it is explicitly excluded.
        else:
            return method_info.name not in facade_scope.method_exclusions


class Facade:
    """
    A named group of related operations which an LLM can invoke from REPL code.
    """

    def __init__(self, name: str, description: str, is_optional: bool = False, types: Sequence[ReferencedType] = ()) -> None:
        # NOTE: attributes are set via object.__setattr__ because __getattr__ is overridden
        object.__setattr__(self, "_is_optional", is_optional)
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_description", description)
        object.__setattr__(self, "_methods", {})
        object.__setattr__(self, "_types", {t.name: t for t in types})
        object.__setattr__(self, "_external_project", None)

    def set_external_project_(self, external_project: "ExternalProjectExecution | None") -> None:
        """
        :param external_project: the context of the external project being queried (None if the active project is used)
        """
        object.__setattr__(self, "_external_project", external_project)

    def get_external_project_(self) -> "ExternalProjectExecution | None":
        return self._external_project

    def _add_method(self, method: FacadeMethod) -> None:
        assert method.parent is self
        self._methods[method.name] = method

    @staticmethod
    def from_api(api: FacadeApi, api_scope: ApiScope, *, is_optional: bool = False) -> "Facade":
        """
        Creates a facade wrapping the given implementation.

        :param api: the implementation; each of its methods decorated with `facade_method` becomes a facade method
        :param api_scope: API scope definition determining which methods are enabled
        :param is_optional: whether the facade is optional (disabled by default and must be enabled explicitly)
        :return: the facade
        """
        facade = Facade(api.get_name_(), api.get_description_(), is_optional, api.get_referenced_types_())
        for name, member in inspect.getmembers(api, predicate=inspect.ismethod):
            method_info = get_facade_method_info(member)
            if method_info is None:
                continue
            is_enabled = api_scope.is_method_enabled(facade.name, method_info, is_facade_optional=is_optional)
            facade._add_method(FacadeMethod(facade, member, method_info, enabled=is_enabled))
        facade._discover_referenced_types()
        return facade

    def is_enabled(self) -> bool:
        """
        :return: whether the facade is enabled
        """
        return len(self.get_enabled_methods()) > 0

    def is_optional(self) -> bool:
        """
        :return: whether the facade is optional, i.e. disabled unless it is explicitly included
        """
        return self._is_optional

    def _discover_referenced_types(self) -> None:
        """
        Adds referenced types for all classes reachable (transitively) through the annotations of the facade's methods
        and of the referenced types' members, such that every type an LLM may encounter can be documented.
        Explicitly declared types take precedence (they may curate members and carry flags).
        """
        # seed the worklist with the classes referenced by the declared types and by the methods
        pending: list[type] = []
        for referenced_type in self._types.values():
            pending.extend(referenced_type.get_referenced_classes())
        for method in self._methods.values():
            pending.extend(get_annotated_classes(method.get_implementation_()))

        # add undeclared classes, following their references in turn
        while pending:
            cls = pending.pop(0)
            if cls.__name__ in self._types:
                continue
            referenced_type = ReferencedType(cls)
            self._types[cls.__name__] = referenced_type
            pending.extend(referenced_type.get_referenced_classes())

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def enabled_method_names(self) -> list[str]:
        return [m.name for m in self._methods.values() if m.enabled]

    def get_enabled_methods(self) -> list[FacadeMethod]:
        """
        :return: the list of enabled methods
        """
        return [m for m in self._methods.values() if m.enabled]

    def get_methods(self) -> list[FacadeMethod]:
        """
        :return: the list of all methods, regardless of whether they are enabled (e.g. for changing their enabled state)
        """
        return list(self._methods.values())

    def get_types(self) -> list[ReferencedType]:
        """
        :return: the types referenced by the facade's methods
        """
        return list(self._types.values())

    def get_type(self, type_name: str) -> ReferencedType | None:
        """
        :param type_name: the name of the type
        :return: the referenced type, or None if the facade does not reference a type of that name
        """
        return self._types.get(type_name)

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
            as well as its referenced types (in full if so declared, otherwise by name)
        """
        parts = [f"Facade '{self._name}': {self._description}", ""]
        enabled_methods = self.get_enabled_methods()
        for method in enabled_methods:
            if not method.info.niche:
                parts.append(method.describe())
        niche_methods = [m for m in enabled_methods if m.info.niche]
        if niche_methods:
            parts.append("Rarely needed methods (documented on request):\n" + "".join(m.describe_summary() for m in niche_methods))
        for referenced_type in self._types.values():
            if referenced_type.provide_info_with_facade:
                parts.append(referenced_type.describe())
        result_type_names = sorted(
            {t.name for m in enabled_methods for t in m.get_referenced_return_types() if not t.provide_info_with_facade}
        )
        if result_type_names:
            parts.append(
                "Result types: "
                + ", ".join(result_type_names)
                + ' (request documentation via `s.info("<type name>")` only if you intend to process results in code)'
            )
        return "\n".join(parts)

    def describe_member(self, member_name: str) -> str:
        """
        :param member_name: the name of one of the facade's enabled methods or referenced types
        :return: the member's documentation
        """
        method = self._get_enabled_method(member_name)
        if method is not None:
            return method.describe()
        referenced_type = self._types.get(member_name)
        if referenced_type is not None:
            return referenced_type.describe()
        raise ValueError(
            f"Facade '{self._name}' has no method or type '{member_name}'. "
            f"Available methods: {self.enabled_method_names}; types: {list(self._types)}"
        )
