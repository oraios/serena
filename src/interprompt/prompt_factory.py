import logging
import os
from typing import Any

from .multilang_prompt import DEFAULT_LANG_CODE, LanguageFallbackMode, MultiLangPromptCollection, PromptList

log = logging.getLogger(__name__)


class PromptFactoryBase:
    """Base class for auto-generated prompt factory classes."""

    def __init__(self, prompts_dir: str | list[str], lang_code: str = DEFAULT_LANG_CODE, fallback_mode=LanguageFallbackMode.EXCEPTION):
        """
        :param prompts_dir: the directory containing the prompt templates and prompt lists.
            If a list is provided, will look for prompt templates in the dirs from left to right
            (first one containing the desired template wins).
        :param lang_code: the language code to use for retrieving the prompt templates and prompt lists.
            Leave as `default` for single-language use cases.
        :param fallback_mode: the fallback mode to use when a prompt template or prompt list is not found for the requested language.
            Irrelevant for single-language use cases.
        """
        self.lang_code = lang_code
        self._prompt_collection = MultiLangPromptCollection(prompts_dir, fallback_mode=fallback_mode)

    def _render_prompt(self, prompt_name: str, params: dict[str, Any]) -> str:
        del params["self"]
        return self._prompt_collection.render_prompt_template(prompt_name, params, lang_code=self.lang_code)

    def _get_prompt_list(self, prompt_name: str) -> PromptList:
        return self._prompt_collection.get_prompt_list(prompt_name, self.lang_code)


def autogenerate_prompt_factory_module(prompts_dir: str, target_module_path: str) -> None:
    """
    Auto-generates a prompt factory module for the given prompt directory.
    The generated `PromptFactory` class is meant to be the central entry class for retrieving and rendering prompt templates and prompt
    lists in your application.
    It will contain one method per prompt template and prompt list, and is useful for both single- and multi-language use cases.

    :param prompts_dir: the directory containing the prompt templates and prompt lists
    :param target_module_path: the path to the target module file (.py). Important: The module will be overwritten!
    """
    generated_code = """
# ruff: noqa
# black: skip
# mypy: ignore-errors

# NOTE: This module is auto-generated from interprompt.autogenerate_prompt_factory_module, do not edit manually!

from interprompt.multilang_prompt import PromptList
from interprompt.prompt_factory import PromptFactoryBase
from typing import Any


class PromptFactory(PromptFactoryBase):
    \"""
    A class for retrieving and rendering prompt templates and prompt lists.
    \"""
"""
    # ---- add methods based on prompt template names and parameters and prompt list names ----
    prompt_collection = MultiLangPromptCollection(prompts_dir)

    for template_name in prompt_collection.get_prompt_template_names():
        template_parameters = prompt_collection.get_prompt_template_parameters(template_name)
        if len(template_parameters) == 0:
            method_params_str = ""
        else:
            method_params_str = ", *, " + ", ".join([f"{param}: Any" for param in template_parameters])
        generated_code += f"""
    def create_{template_name}(self{method_params_str}) -> str:
        return self._render_prompt('{template_name}', locals())
"""
    for prompt_list_name in prompt_collection.get_prompt_list_names():
        generated_code += f"""
    def get_list_{prompt_list_name}(self) -> PromptList:
        return self._get_prompt_list('{prompt_list_name}')
"""
    os.makedirs(os.path.dirname(target_module_path), exist_ok=True)
    with open(target_module_path, "w", encoding="utf-8") as f:
        f.write(generated_code)
    log.info(f"Prompt factory generated successfully in {target_module_path}")
