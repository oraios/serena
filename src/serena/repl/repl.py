"""
The REPL through which an LLM executes Python code against Serena's facades.
"""

# SPDX-License-Identifier: GPL-3.0-or-later

import ast
import logging
import re
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
        self._current_namespace: dict[str, Any] | None = None
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

    The code is executed as the body of a function, such that the `return` statement defines the result;
    code consisting of a single expression is evaluated and its value is the result.
    Names assigned at the top level of the code (variables, functions, classes, imports) persist in the session's
    namespace across executions (like the cells of a notebook), which serves as the globals of the executions.
    The entrypoint `s` is (re)bound in the namespace before every execution, such that persisted functions always
    access the current entrypoint.
    """

    SOURCE_NAME = "<serena_repl>"
    ENTRYPOINT_NAME = "s"
    _FUNCTION_NAME = "__serena_repl_fn__"
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
        Runs the given code in the given namespace (as globals) with the entrypoint bound, either as a single expression
        or as the body of a function whose return value is the result and whose top-level assignments are made global
        (such that they persist in the namespace).
        """
        namespace[self.ENTRYPOINT_NAME] = self._entrypoint

        # try to evaluate the code as a single expression
        try:
            compiled = compile(code, self.SOURCE_NAME, "eval")
        except SyntaxError:
            compiled = None
        if compiled is not None:
            return eval(compiled, namespace)

        # otherwise execute the code as the body of a function, declaring the names assigned at the top level as global.
        # The function is constructed at the AST level, such that the line numbers of the code are preserved.
        module = ast.parse(code, self.SOURCE_NAME)
        body: list[ast.stmt] = list(module.body)
        assigned_names = self._collect_top_level_assigned_names(body)
        if assigned_names:
            body.insert(0, ast.Global(names=sorted(assigned_names)))
        function = ast.FunctionDef(
            name=self._FUNCTION_NAME,
            args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
            body=body,
            decorator_list=[],
            returns=None,
        )
        wrapper = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
        exec(compile(wrapper, self.SOURCE_NAME, "exec"), namespace)
        try:
            return namespace[self._FUNCTION_NAME]()
        finally:
            del namespace[self._FUNCTION_NAME]

    @classmethod
    def _collect_top_level_assigned_names(cls, statements: list[ast.stmt]) -> set[str]:
        """
        :param statements: the top-level statements of the code
        :return: the names bound by the statements (assignment targets, function/class definitions, imports,
            loop/with targets, deletions and walrus assignments outside of nested scopes)
        """
        names: set[str] = set()

        def add_target(target: ast.expr) -> None:
            if isinstance(target, ast.Name):
                names.add(target.id)
            elif isinstance(target, ast.Tuple | ast.List):
                for element in target.elts:
                    add_target(element)
            elif isinstance(target, ast.Starred):
                add_target(target.value)

        def add_walrus_targets(node: ast.AST) -> None:
            # walrus assignments bind in the enclosing scope, unless within a nested scope
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda):
                    continue
                if isinstance(child, ast.NamedExpr):
                    add_target(child.target)
                add_walrus_targets(child)

        for statement in statements:
            match statement:
                case ast.Assign(targets=targets):
                    for target in targets:
                        add_target(target)
                case ast.AnnAssign(target=target) | ast.AugAssign(target=target):
                    add_target(target)
                case ast.FunctionDef(name=name) | ast.AsyncFunctionDef(name=name) | ast.ClassDef(name=name):
                    names.add(name)
                case ast.Import(names=aliases) | ast.ImportFrom(names=aliases):
                    for alias in aliases:
                        if alias.name != "*":
                            names.add(alias.asname or alias.name.split(".")[0])
                case ast.For(target=target) | ast.AsyncFor(target=target):
                    add_target(target)
                case ast.With(items=items) | ast.AsyncWith(items=items):
                    for item in items:
                        if item.optional_vars is not None:
                            add_target(item.optional_vars)
                case ast.Delete(targets=targets):
                    for target in targets:
                        add_target(target)
            add_walrus_targets(statement)
        return names

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
            return f"SyntaxError: {e.msg}\n" + location_line(e.lineno)

        # report runtime errors, locating them within the executed code
        location_lines = []
        for frame in traceback.extract_tb(e.__traceback__):
            if frame.filename != self.SOURCE_NAME or frame.lineno is None:
                continue
            location_lines.append(location_line(frame.lineno))
        return "\n".join([f"{type(e).__name__}: {e}", *location_lines])
