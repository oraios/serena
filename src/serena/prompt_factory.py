import os

from serena.constants import PROMPT_TEMPLATES_DIR_IN_USER_HOME, PROMPT_TEMPLATES_DIR_INTERNAL
from serena.generated.generated_prompt_factory import PromptFactory


class SerenaPromptFactory(PromptFactory):
    """
    A class for retrieving and rendering prompt templates and prompt lists.
    """

    def __init__(self) -> None:
        os.makedirs(PROMPT_TEMPLATES_DIR_IN_USER_HOME, exist_ok=True)
        super().__init__(prompts_dir=[PROMPT_TEMPLATES_DIR_IN_USER_HOME, PROMPT_TEMPLATES_DIR_INTERNAL])
