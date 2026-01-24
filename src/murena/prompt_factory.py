import os

from murena.config.murena_config import MurenaPaths
from murena.constants import PROMPT_TEMPLATES_DIR_INTERNAL
from murena.generated.generated_prompt_factory import PromptFactory


class MurenaPromptFactory(PromptFactory):
    """
    A class for retrieving and rendering prompt templates and prompt lists.
    """

    def __init__(self) -> None:
        user_templates_dir = MurenaPaths().user_prompt_templates_dir
        os.makedirs(user_templates_dir, exist_ok=True)
        super().__init__(prompts_dir=[user_templates_dir, PROMPT_TEMPLATES_DIR_INTERNAL])
