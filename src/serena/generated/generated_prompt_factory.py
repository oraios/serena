# ruff: noqa
# black: skip
# mypy: ignore-errors

# NOTE: This module is auto-generated from interprompt.autogenerate_prompt_factory_module, do not edit manually!

from interprompt.multilang_prompt import PromptList
from interprompt.prompt_factory import PromptFactoryBase
from typing import Any


class PromptFactory(PromptFactoryBase):
    """
    A class for retrieving and rendering prompt templates and prompt lists.
    """

    def create_info_jet_brains_debug_repl(self) -> str:
        return self._render_prompt("info_jet_brains_debug_repl", locals())

    def create_onboarding_prompt(self, *, system: Any) -> str:
        return self._render_prompt("onboarding_prompt", locals())

    def create_connection_prompt(self) -> str:
        return self._render_prompt("connection_prompt", locals())

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
