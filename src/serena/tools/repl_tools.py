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
        docs = self.get_apply_docstring_from_cls()
        if self.agent.is_single_project():
            docs += "\n\nAvailable facades:\n" + self.agent.get_repl().entrypoint.overview()
        else:
            docs += "\n\nAvailable facades are provided at project activation"
        return docs

    def apply(self, session: str, code: str) -> str:
        """
        Executes the given Python code, which has access to Serena's functionality through the object `s`.
        The functionality is organised in facades, which are attributes of `s` (e.g. `s.myfacade`).

        Documentation: Use `s.info("<facade>")` when you will use a facade's functionality (it documents all common
        operations at once) and `s.info("<facade>.<method>")` for a single or a rarely needed operation. Several items
        can be requested in one call, e.g. `s.info("lsp", "edit.replace_content")`.
        `s.info("<facade>")` documents the facade's operations only, not their result types. The facade listing
        provides result types (`method -> Type`); request their documentation via `s.info("<Type>")`, which
        includes the types they contain, ONLY if you intend to process results in code (filter, aggregate, chain
        calls).

        The code is executed like a notebook cell: if its last statement is an expression, the expression's value is
        the result. Results are rendered in a form suitable for you; lists are rendered element-wise,
        strings are passed through unchanged.

        Output size: methods with a `max_answer_chars` parameter limit the size of the rendered result (-1 uses the
        configured default). If the limit is exceeded, a shortened result (or no content) is rendered instead;
        adjust the limit only if there is no other way to obtain the content required for the task (e.g. by
        narrowing the query or processing the result in code and returning only what is needed).

        Persistence: variables, functions and classes defined at the top level of your code persist across calls
        within your session (like the cells of a notebook), so you can reuse results and define helper functions once.
        `s.vars()` lists the persisted items, `s.clear()` removes them. Do not store facades (`s.<facade>`) in
        variables; access them via `s` at call time. Do not keep large results longer than needed.

        :param session: your Serena session id, as provided in Serena's instructions (call `initial_instructions` if you do not have one)
        :param code: the Python code to execute
        :return: the representation of the returned value, or the error if execution failed
        """
        return self.agent.get_repl().execute(code, self.agent.get_session(session))
