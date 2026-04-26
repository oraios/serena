from typing import Any

import jinja2
import jinja2.meta
import jinja2.nodes
import jinja2.visitor

from interprompt.util.class_decorators import singleton


class ParameterizedTemplateInterface:
    def get_parameters(self) -> list[str]: ...


@singleton
class _JinjaEnvProvider:
    def __init__(self) -> None:
        self._env: jinja2.Environment | None = None

    def get_env(self) -> jinja2.Environment:
        if self._env is None:
            self._env = jinja2.Environment()
        return self._env


class JinjaTemplate(ParameterizedTemplateInterface):
    def __init__(self, template_string: str) -> None:
        self._template_string = template_string
        self._template = _JinjaEnvProvider().get_env().from_string(self._template_string)
        parsed_content = self._template.environment.parse(self._template_string)
        self._parameters = sorted(jinja2.meta.find_undeclared_variables(parsed_content))

    def get_template_string(self) -> str:
        return self._template_string

    def render(self, **params: Any) -> str:
        """Renders the template with the given kwargs. You can find out which parameters are required by calling get_parameter_names()."""
        return self._template.render(**params)

    def get_parameters(self) -> list[str]:
        """A sorted list of parameter names that are extracted from the template string. It is impossible to know the types of the parameter
        values, they can be primitives, dicts or dict-like objects.

        :return: the list of parameter names
        """
        return self._parameters
