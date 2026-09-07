"""
The REPL through which an LLM executes Python code against Serena's facades.
"""

# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import textwrap
import traceback
from typing import Any

from .facade import ApiScope, Facade
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
        registered_facade_names = []
        for facade in facades:
            if api_scope.is_facade_enabled(facade.name):
                self._register(facade)
                registered_facade_names.append(facade.name)
        log.info("Registered %d/%d facades: %s", len(registered_facade_names), len(facades), registered_facade_names)

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
        """
        return "\n".join(
            f"s.{facade.name}: {facade.description}\n  methods: {', '.join(facade.enabled_method_names)}"
            for facade in self._facades.values()
        )

    def info(self, path: str = "") -> str:
        """
        Provides documentation on the available functionality.

        :param path: the empty string for an overview of all facades, a facade name (e.g. "lsp") for the
            documentation of all of the facade's methods, or a dotted method path (e.g. "lsp.find_symbol")
            for the documentation of a single method
        :return: the requested documentation
        """
        if path == "":
            return self.overview()
        facade_name, _, method_name = path.partition(".")
        facade = self._get_facade(facade_name)
        if method_name == "":
            return facade.describe()
        return facade.describe_method(method_name)


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

    def execute(self, code: str) -> str:
        """
        Executes the given code and renders its result.

        :param code: the Python code to execute
        :return: the representation of the code's result, or a description of the error if execution failed
        """
        try:
            result = self._run(code)
        except Exception as e:
            return self._format_error(e, code)
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
