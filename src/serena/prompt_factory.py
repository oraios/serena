import os

from serena.config.serena_config import SerenaPaths
from serena.constants import PROMPT_TEMPLATES_DIR_INTERNAL
from serena.generated.generated_prompt_factory import PromptFactory


class SerenaPromptFactory(PromptFactory):
    """
    A class for retrieving and rendering prompt templates and prompt lists.
    """

    def __init__(self) -> None:
        user_templates_dir = SerenaPaths().user_prompt_templates_dir
        os.makedirs(user_templates_dir, exist_ok=True)
        super().__init__(prompts_dir=[user_templates_dir, PROMPT_TEMPLATES_DIR_INTERNAL])

    def create_cc_system_prompt_override(self, *, jetbrains_backend: bool, tool_names: dict[str, str]) -> str:
        """
        :param jetbrains_backend: whether the active language backend is JetBrains, in which case the
            JetBrains-only refactoring tools are additionally listed in the rendered prompt
        :param tool_names: mapping from tool names to the names effective under the active language
            backend (see :meth:`SerenaAgent.create_prompt_tool_names_mapping`), used to render
            backend-aware tool references in the prompt
        :return: the Claude Code system prompt override
        """
        return super().create_cc_system_prompt_override(jetbrains_backend=jetbrains_backend, tool_names=tool_names)
