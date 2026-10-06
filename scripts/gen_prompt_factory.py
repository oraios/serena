"""
Autogenerates the `prompt_factory.py` module
"""
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

from add_spdx_headers import add_header
from sensai.util import logging

from interprompt import autogenerate_prompt_factory_module
from serena.constants import PROMPT_TEMPLATES_DIR_INTERNAL, REPO_ROOT

log = logging.getLogger(__name__)


def main():
    target_module_path = Path(REPO_ROOT) / "src" / "serena" / "generated" / "generated_prompt_factory.py"
    autogenerate_prompt_factory_module(
        prompts_dir=PROMPT_TEMPLATES_DIR_INTERNAL,
        target_module_path=str(target_module_path),
    )

    # re-add the license header, which the (externally maintained) generator template does not include
    add_header(target_module_path, "GPL-3.0-or-later")


if __name__ == "__main__":
    logging.run_main(main)
