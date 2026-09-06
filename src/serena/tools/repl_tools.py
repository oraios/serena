"""
Tools which provide access to Serena's functionality through Python code execution
"""

# SPDX-License-Identifier: GPL-3.0-or-later

from serena.tools.tools_base import Tool, ToolMarkerBeta


class SerenaReplTool(Tool, ToolMarkerBeta):
    """
    Executes Python code which accesses Serena's functionality programmatically.
    """

    def get_apply_docstring(self) -> str:
        return self.get_apply_docstring_from_cls() + "\n\nAvailable facades:\n" + self.agent.get_repl().entrypoint.overview()

    def apply(self, code: str) -> str:
        """
        Executes the given Python code, which has access to Serena's functionality through the object `s`.
        The functionality is organised in facades, which are attributes of `s` (e.g. `s.myfacade`).
        Use `s.info()` to list the facades, `s.info("<facade>")` to see a facade's methods and
        `s.info("<facade>.<method>")` for the documentation of a single method.

        The code is executed as the body of a function, so use `return` to define the result;
        a single expression is evaluated and its value returned directly.
        Returned objects are rendered in a form suitable for you; lists are rendered element-wise.
        Returned strings are passed through unchanged.

        :param code: the Python code to execute
        :return: the representation of the returned value, or the error if execution failed
        """
        return self.agent.get_repl().execute(code)
