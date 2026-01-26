"""
Autogenerates the `prompt_factory.py` module
"""

from pathlib import Path

from sensai.util import logging
from serena.constants import PROMPT_TEMPLATES_DIR_INTERNAL, REPO_ROOT

from interprompt import autogenerate_prompt_factory_module

log = logging.getLogger(__name__)


def main():
    autogenerate_prompt_factory_module(
        prompts_dir=PROMPT_TEMPLATES_DIR_INTERNAL,
        target_module_path=str(Path(REPO_ROOT) / "src" / "serena" / "generated" / "generated_prompt_factory.py"),
    )


if __name__ == "__main__":
    logging.run_main(main)
