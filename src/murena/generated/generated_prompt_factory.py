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

    def create_onboarding_prompt(self, *, system: Any) -> str:
        return self._render_prompt("onboarding_prompt", locals())

    def create_think_about_collected_information(self) -> str:
        return self._render_prompt("think_about_collected_information", locals())

    def create_think_about_task_adherence(self) -> str:
        return self._render_prompt("think_about_task_adherence", locals())

    def create_think_about_whether_you_are_done(self) -> str:
        return self._render_prompt("think_about_whether_you_are_done", locals())

    def create_summarize_changes(self) -> str:
        return self._render_prompt("summarize_changes", locals())

    def create_prepare_for_new_conversation(self) -> str:
        return self._render_prompt("prepare_for_new_conversation", locals())

    def create_system_prompt(
        self, *, available_markers: Any, available_tools: Any, context_system_prompt: Any, mode_system_prompts: Any
    ) -> str:
        return self._render_prompt("system_prompt", locals())
