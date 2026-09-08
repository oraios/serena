"""
Tools which provide access to Serena's functionality through Python code execution
"""

# SPDX-License-Identifier: GPL-3.0-or-later

from serena.tools.tools_base import Tool, ToolMarkerBeta, ToolMarkerOptional


class SerenaReplTool(Tool, ToolMarkerOptional, ToolMarkerBeta):
    """
    Executes Python code which accesses Serena's functionality programmatically.
    """

    def get_apply_docstring(self) -> str:
        return self.get_apply_docstring_from_cls() + "\n\nAvailable facades:\n" + self.agent.get_repl().entrypoint.overview()

    def apply(self, code: str) -> str:
        """
        Executes the given Python code, which has access to Serena's functionality through the object `s`.
        The functionality is organised in facades, which are attributes of `s` (e.g. `s.myfacade`); the available
        facades and their methods are listed below.

        Documentation: Use `s.info("<facade>")` when you will use a facade's functionality (it documents all common
        operations at once) and `s.info("<facade>.<method>")` for a single or a rarely needed operation. Several items
        can be requested in one call, e.g. `s.info("lsp", "edit.replace_content")`.
        `s.info("<facade>")` documents the facade's operations only, not their result types. Result types are given
        in the method listing below (`method -> Type`); request their documentation via `s.info("<Type>")`, which
        includes the types they contain, ONLY if you intend to process results in code (filter, aggregate, chain
        calls). If you simply want the result, return it directly: returned objects are rendered for you.

        The code is executed as the body of a function, so use `return` to define the result;
        a single expression is evaluated and its value returned directly.
        Returned objects are rendered in a form suitable for you; lists are rendered element-wise.
        Returned strings are passed through unchanged.

        :param code: the Python code to execute
        :return: the representation of the returned value, or the error if execution failed
        """
        return self.agent.get_repl().execute(code)
