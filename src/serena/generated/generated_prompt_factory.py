# ruff: noqa
# black: skip
# mypy: ignore-errors

# NOTE: This module is auto-generated from interprompt.autogenerate_prompt_factory_module, do not edit manually!

from interprompt.prompt_factory import PromptFactoryBase
from typing import Any


class PromptFactory(PromptFactoryBase):
    """
    A class for retrieving and rendering prompt templates and prompt lists.
    """

    def get_info_jet_brains_debug_repl_template_string(self) -> str:
        return self.get_prompt_template_string("info_jet_brains_debug_repl")

    def create_info_jet_brains_debug_repl(self) -> str:
        return self._render_prompt("info_jet_brains_debug_repl", locals())

    def get_onboarding_prompt_template_string(self) -> str:
        return self.get_prompt_template_string("onboarding_prompt")

    def create_onboarding_prompt(self, *, system: Any) -> str:
        return self._render_prompt("onboarding_prompt", locals())

    def get_connection_prompt_template_string(self) -> str:
        return self.get_prompt_template_string("connection_prompt")

    def create_connection_prompt(self) -> str:
        return self._render_prompt("connection_prompt", locals())

    def get_system_prompt_template_string(self) -> str:
        return self.get_prompt_template_string("system_prompt")

    def create_system_prompt(
        self,
        *,
        available_markers: Any,
        available_tools: Any,
        context_system_prompt: Any,
        global_memories_list: Any,
        mode_system_prompts: Any,
    ) -> str:
        return self._render_prompt("system_prompt", locals())

    def get_cc_system_prompt_override_template_string(self) -> str:
        return self.get_prompt_template_string("cc_system_prompt_override")

    def create_cc_system_prompt_override(self) -> str:
        return self._render_prompt("cc_system_prompt_override", locals())
