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
