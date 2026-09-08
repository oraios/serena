"""
The REPL through which an LLM executes Python code against Serena's facades.
"""

# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import textwrap
import traceback
from typing import Any

from ..session import SerenaSession
from .facade import ApiScope, Facade, FacadeMethod, ReferencedType
from .representable import Representable

log = logging.getLogger(__name__)


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
        registered_facade_names = []
        for facade in facades:
            if api_scope.is_facade_enabled(facade.name):
                self._register(facade)
                registered_facade_names.append(facade.name)
        log.info("Registered %d/%d facades: %s", len(registered_facade_names), len(facades), registered_facade_names)

    def get_enabled_methods(self) -> list[FacadeMethod]:
        """
        :return: the list of all enabled methods across all facades
        """
        return [method for facade in self._facades.values() for method in facade.get_enabled_methods()]

    def set_current_session_(self, session: SerenaSession | None) -> None:
        """
        :param session: the session on whose behalf code is being executed (None if no code is being executed)
        """
        self._current_session = session

    def _register(self, facade: Facade) -> None:
        if facade.name in self._facades:
            raise ValueError(f"Duplicate facade name: {facade.name}")
        self._facades[facade.name] = facade
        setattr(self, facade.name, facade)

    def _get_facade(self, name: str) -> Facade:
        if name not in self._facades:
            raise ValueError(f"Unknown facade '{name}'. Available facades: {list(self._facades)}")
        return self._facades[name]

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
        pending = list(referenced_type.get_referenced_type_names())
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
                pending.extend(contained_type.get_referenced_type_names())
        return "\n".join(parts)


class SerenaRepl:
    """
    Executes Python code submitted by an LLM, binding the configured facades to the entrypoint object `s`
    and rendering the result of the execution as a string for the LLM.

    The code is executed as the body of a function, such that the `return` statement defines the result;
    code consisting of a single expression is evaluated and its value is the result.
    """

    SOURCE_NAME = "<serena_repl>"
    ENTRYPOINT_NAME = "s"
    _FUNCTION_NAME = "__serena_repl_fn__"

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
        self._entrypoint.set_current_session_(session)
        try:
            result = self._run(code)
        except Exception as e:
            return self._format_error(e, code)
        finally:
            self._entrypoint.set_current_session_(None)
        return self._represent(result)

    def _run(self, code: str) -> Any:
        """
        Runs the given code with the entrypoint bound, either as a single expression
        or as the body of a function whose return value is the result.
        """
        namespace: dict[str, Any] = {self.ENTRYPOINT_NAME: self._entrypoint}

        # try to evaluate the code as a single expression
        try:
            compiled = compile(code, self.SOURCE_NAME, "eval")
        except SyntaxError:
            compiled = None
        if compiled is not None:
            return eval(compiled, namespace)

        # otherwise execute the code as the body of a function
        source = f"def {self._FUNCTION_NAME}({self.ENTRYPOINT_NAME}):\n" + textwrap.indent(code, "    ")
        exec(compile(source, self.SOURCE_NAME, "exec"), namespace)
        return namespace[self._FUNCTION_NAME](self._entrypoint)

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
            return f"SyntaxError: {e.msg}\n" + location_line(e.lineno - 1)  # undo the function header offset

        # report runtime errors, locating them within the executed code
        location_lines = []
        for frame in traceback.extract_tb(e.__traceback__):
            if frame.filename != self.SOURCE_NAME or frame.lineno is None:
                continue
            line_number = frame.lineno - 1 if frame.name == self._FUNCTION_NAME else frame.lineno  # undo the function header offset
            location_lines.append(location_line(line_number))
        return "\n".join([f"{type(e).__name__}: {e}", *location_lines])
