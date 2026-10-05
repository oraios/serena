"""
The REPL through which an LLM executes Python code against Serena's facades.
"""

# SPDX-License-Identifier: GPL-3.0-or-later

import ast
import logging
import re
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..session import SerenaSession
from .external_project import ExternalProjectExecution
from .facade import ApiScope, Facade, FacadeMethod, ReferencedType
from .representable import Representable

if TYPE_CHECKING:
    from ..tools.tools_base import Tool

log = logging.getLogger(__name__)


class FacadeAvailabilityInfo:
    """
    Represents information on the availability of facades and the methods therein
    """

    @dataclass
    class FacadeInfo:
        name: str
        is_enabled: bool
        methods: list["FacadeAvailabilityInfo.MethodInfo"]

    @dataclass
    class MethodInfo:
        name: str
        is_enabled: bool

    def __init__(self):
        self.facades: list[FacadeAvailabilityInfo.FacadeInfo] = []

    def add_facade(self, facade: Facade):
        methods_info = [FacadeAvailabilityInfo.MethodInfo(name=method.name, is_enabled=method.enabled) for method in facade.get_methods()]
        self.facades.append(FacadeAvailabilityInfo.FacadeInfo(name=facade.name, is_enabled=facade.is_enabled(), methods=methods_info))


class SerenaReplEntrypoint:
    """
    Represents the entrypoint object for the REPL. It holds the configured facades as attributes
    and offers progressive disclosure of their interfaces via `info`.
    """

    def __init__(self, facades: list[Facade], api_scope: ApiScope) -> None:
        """
        :param facades: the candidate facades
        :param api_scope: the API scope, which determines which of the facades are made available
        """
        self._facades: dict[str, Facade] = {}
        self._current_session: SerenaSession | None = None
        self._current_namespace: dict[str, Any] | None = None
        self._facade_availability_info = FacadeAvailabilityInfo()
        registered_facade_names = []
        for facade in facades:
            self._facade_availability_info.add_facade(facade)
            if facade.is_enabled():
                if facade.name in self._facades:
                    raise ValueError(f"Duplicate facade name: {facade.name}")
                self._facades[facade.name] = facade
                setattr(self, facade.name, facade)
                registered_facade_names.append(facade.name)
        log.info("Registered %d/%d facades: %s", len(registered_facade_names), len(facades), registered_facade_names)

    def get_facade_availability_info(self) -> FacadeAvailabilityInfo:
        """
        :return: the availability of all facades and their methods (enabled or disabled)
        """
        return self._facade_availability_info

    def get_enabled_methods(self) -> list[FacadeMethod]:
        """
        :return: the list of all enabled methods across all facades
        """
        return [method for facade in self._facades.values() for method in facade.get_enabled_methods()]

    def is_tool_function_available(self, tool_class: "type[Tool]") -> bool:
        """
        Checks whether any of the enabled methods corresponds to the given tool class.

        :param tool_class: the tool class to check for
        :return: whether any enabled method corresponds to the given tool class
        """
        for method in self.get_enabled_methods():
            if method.info.corresponding_tool == tool_class:
                return True
        return False

    def set_external_project_(self, external_project: "ExternalProjectExecution | None") -> None:
        """
        :param external_project: the context of the external project being queried by the currently executing code
            (None if the active project is used); propagated to all facades
        """
        for facade in self._facades.values():
            facade.set_external_project_(external_project)

    def get_external_project_(self) -> "ExternalProjectExecution | None":
        external_projects = {facade.get_external_project_() for facade in self._facades.values()}
        return next(iter(external_projects)) if external_projects else None

    def set_current_session_(self, session: SerenaSession | None, namespace: dict[str, Any] | None) -> None:
        """
        :param session: the session on whose behalf code is being executed (None if no code is being executed)
        :param namespace: the namespace of the execution (None if no code is being executed)
        """
        self._current_session = session
        self._current_namespace = namespace

    def _get_persisted_items(self) -> dict[str, Any]:
        assert self._current_namespace is not None, "No code execution in progress"
        return {
            name: value
            for name, value in self._current_namespace.items()
            if name != SerenaRepl.ENTRYPOINT_NAME and SerenaRepl.is_persisted_name(name)
        }

    def vars(self) -> str:
        """
        Lists the variables and functions which persist in the session's namespace across executions.

        :return: the listing (name, type and a short representation per item)
        """
        items = self._get_persisted_items()
        if not items:
            return "No persisted variables."
        lines = []
        for name, value in items.items():
            summary = value.__name__ if callable(value) and hasattr(value, "__name__") else repr(value)
            if len(summary) > 80:
                summary = summary[:77] + "..."
            lines.append(f"{name}: {type(value).__name__} = {summary}")
        return "\n".join(lines)

    def clear(self) -> str:
        """
        Removes all persisted variables and functions from the session's namespace.

        :return: a message indicating the number of removed items
        """
        items = self._get_persisted_items()
        assert self._current_namespace is not None
        for name in items:
            del self._current_namespace[name]
        return f"Removed {len(items)} persisted item(s)."

    def _get_facade(self, name: str) -> Facade:
        if name not in self._facades:
            raise ValueError(f"Unknown facade '{name}'. Available facades: {list(self._facades)}")
        return self._facades[name]

    def get_facade_(self, name: str) -> Facade:
        """
        :param name: the facade's name
        :return: the facade
        """
        return self._get_facade(name)

    def overview(self) -> str:
        """
        :return: the list of available facades, each with a one-line description and the names of its methods
            (with the result type of methods returning objects that can be processed in code)
        """

        def method_entry(method: FacadeMethod) -> str:
            return_types = method.get_referenced_return_types()
            return method.name + (f" -> {'|'.join(t.name for t in return_types)}" if return_types else "")

        return "\n".join(
            f"s.{facade.name}: {facade.description}\n  methods: {', '.join(method_entry(m) for m in facade.get_enabled_methods())}"
            for facade in self._facades.values()
        )

    def info(self, *items: str) -> str:
        """
        Provides documentation on the available functionality.

        :param items: the items to document; if none are given, an overview of all facades is provided.
            Each item is either a facade name (e.g. "lsp") for the documentation of all of the facade's methods and types,
            a dotted path (e.g. "lsp.find_symbol" or "lsp.LspSymbolCollection") for the documentation of a single method
            or type, or a bare type name (e.g. "LanguageServerSymbol"), which is looked up across all facades.
            Unknown items are reported without affecting the documentation of the other items.
        :return: the requested documentation
        """
        if not items:
            return self.overview()
        described_in_call: set[str] = set()
        return "\n\n".join(self._describe_item(item, described_in_call) for item in items)

    def _describe_item(self, item: str, described_in_call: set[str]) -> str:
        facade_name, _, member_name = item.partition(".")
        try:
            if member_name:
                facade = self._get_facade(facade_name)
                referenced_type = facade.get_type(member_name)
                if referenced_type is not None:
                    return self._describe_type(referenced_type, described_in_call)
                return facade.describe_member(member_name)
            if facade_name in self._facades:
                return self._facades[facade_name].describe()
            # not a facade: look up the item as a type across all facades
            referenced_type = self._find_type(item)
            if referenced_type is None:
                raise ValueError(f"Unknown item '{item}': neither a facade nor a type. Available facades: {list(self._facades)}")
            return self._describe_type(referenced_type, described_in_call)
        except ValueError as e:
            return str(e)

    def _find_type(self, type_name: str) -> ReferencedType | None:
        for facade in self._facades.values():
            referenced_type = facade.get_type(type_name)
            if referenced_type is not None:
                return referenced_type
        return None

    def _describe_type(self, referenced_type: ReferencedType, described_in_call: set[str]) -> str:
        """
        Describes the given (explicitly requested) type along with the types it references (transitively), each at most
        once per call. Referenced types whose documentation was already provided earlier in the session are not repeated
        but pointed to (an explicit request always yields the full documentation).

        :param referenced_type: the requested type
        :param described_in_call: the names of the types already described in the current `info` call (updated)
        :return: the documentation
        """
        session = self._current_session
        parts = []
        if referenced_type.name not in described_in_call:
            parts.append(referenced_type.describe())
            described_in_call.add(referenced_type.name)
            if session is not None:
                session.described_type_names.add(referenced_type.name)

        # append the referenced types (breadth-first), unless already described in this call or earlier in the session
        pending = [cls.__name__ for cls in referenced_type.get_referenced_classes()]
        while pending:
            type_name = pending.pop(0)
            if type_name in described_in_call:
                continue
            contained_type = self._find_type(type_name)
            if contained_type is None:
                continue
            described_in_call.add(type_name)
            if session is not None and type_name in session.described_type_names:
                parts.append(f'type {type_name}: documented earlier in this session (request `s.info("{type_name}")` to see it again)\n')
            else:
                parts.append(contained_type.describe())
                if session is not None:
                    session.described_type_names.add(type_name)
                pending.extend(cls.__name__ for cls in contained_type.get_referenced_classes())
        return "\n".join(parts)


class SerenaRepl:
    """
    Executes Python code submitted by an LLM, binding the configured facades to the entrypoint object `s`
    and rendering the result of the execution as a string for the LLM.

    The code is executed like the cell of a notebook: it is executed at module level in the session's namespace,
    such that the names it binds (variables, functions, classes, imports) persist across executions, and if its last
    statement is an expression, the expression's value is the result of the execution.
    The entrypoint `s` is (re)bound in the namespace before every execution, such that persisted functions always
    access the current entrypoint.
    """

    SOURCE_NAME = "<serena_repl>"
    ENTRYPOINT_NAME = "s"
    _PERSISTED_NAME_PATTERN = re.compile(r"^(?!__)[A-Za-z_]\w*$")

    @classmethod
    def is_persisted_name(cls, name: str) -> bool:
        """
        :param name: a name in a session namespace
        :return: whether the name denotes a persisted item of the LLM's (as opposed to an implementation detail
            such as `__builtins__`)
        """
        return cls._PERSISTED_NAME_PATTERN.match(name) is not None

    def __init__(self, facades: list[Facade], api_scope: ApiScope) -> None:
        """
        :param facades: the candidate facades
        :param api_scope: the API scope, which determines which of the facades are made available
        """
        self._entrypoint = SerenaReplEntrypoint(facades, api_scope)

    @property
    def entrypoint(self) -> SerenaReplEntrypoint:
        return self._entrypoint

    @classmethod
    def _represent(cls, obj: Any) -> str:
        """
        Renders an arbitrary object as a string for the LLM. Representables render themselves,
        lists and tuples are rendered element-wise (one element per line), everything else via `str`.

        :param obj: the object to render
        :return: the textual representation
        """
        if isinstance(obj, Representable):
            return obj.represent()
        if isinstance(obj, list | tuple):
            if len(obj) == 0:
                return "[]"
            return "\n".join(cls._represent(item) for item in obj)
        return str(obj)

    def execute(self, code: str, session: SerenaSession | None = None) -> str:
        """
        Executes the given code and renders its result.
        Executions are expected to be serialised (the entrypoint holds the current session during execution).

        :param code: the Python code to execute
        :param session: the client session on whose behalf the code is executed (None for session-less execution,
            e.g. in tests), which determines e.g. which type documentation has already been provided
        :return: the representation of the code's result, or a description of the error if execution failed
        """
        namespace = session.repl_namespace if session is not None else {}
        self._entrypoint.set_current_session_(session, namespace)
        try:
            result = self._run(code, namespace)
        except Exception as e:
            return self._format_error(e, code)
        finally:
            self._entrypoint.set_current_session_(None, None)
        return self._represent(result)

    def _run(self, code: str, namespace: dict[str, Any]) -> Any:
        """
        Runs the given code at module level in the given namespace (as globals) with the entrypoint bound.

        :return: the value of the code's last statement if it is an expression, None otherwise
        """
        namespace[self.ENTRYPOINT_NAME] = self._entrypoint
        module = ast.parse(code, self.SOURCE_NAME)

        # separate a trailing expression, whose value is the result
        statements = module.body
        trailing_expression: ast.expr | None = None
        if statements and isinstance(statements[-1], ast.Expr):
            trailing_expression = statements[-1].value
            statements = statements[:-1]

        # execute the statements, then evaluate the trailing expression (both retain the original line numbers)
        if statements:
            exec(compile(ast.Module(body=statements, type_ignores=[]), self.SOURCE_NAME, "exec"), namespace)
        if trailing_expression is not None:
            return eval(compile(ast.Expression(body=trailing_expression), self.SOURCE_NAME, "eval"), namespace)
        return None

    def _format_error(self, e: Exception, code: str) -> str:
        """
        :param e: the exception raised during execution
        :param code: the code that was executed
        :return: an error message which locates the failure within the executed code
        """
        code_lines = code.splitlines()

        def location_line(line_number: int) -> str:
            line_text = code_lines[line_number - 1].strip() if 0 < line_number <= len(code_lines) else ""
            return f"  line {line_number}: {line_text}"

        # report syntax errors in the executed code (which carry no traceback frames of their own)
        if isinstance(e, SyntaxError) and e.filename == self.SOURCE_NAME and e.lineno is not None:
            message = f"SyntaxError: {e.msg}\n" + location_line(e.lineno)
            if "return" in (e.msg or "") and "outside function" in e.msg:
                message += "\nNote: the code is executed like a notebook cell; the value of the last expression is the result (do not use `return`)."
            return message

        # report runtime errors, locating them within the executed code
        location_lines = []
        for frame in traceback.extract_tb(e.__traceback__):
            if frame.filename != self.SOURCE_NAME or frame.lineno is None:
                continue
            location_lines.append(location_line(frame.lineno))
        return "\n".join([f"{type(e).__name__}: {e}", *location_lines])
