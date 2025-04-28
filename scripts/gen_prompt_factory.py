from sensai.util import logging

from serena.llm.multilang_prompt import MultiLangPromptTemplateCollection

log = logging.getLogger(__name__)


def main():
    coll = MultiLangPromptTemplateCollection()

    package = "src/serena"

    # collect methods to generate
    indent = "    "
    methods = []
    for mpt in coll.prompt_templates.values():
        prompt_name = mpt.name
        params = mpt.get_parameters()

        # Special handling for system_prompt
        if prompt_name == "system_prompt":
            methods.append(
                f"def create_{prompt_name}(self) -> str:"
                + f"\n{indent}{indent}# Prepare context and modes for the template"
                + f'\n{indent}{indent}context_str = ""'
                + f"\n{indent}{indent}if self.context:"
                + f"\n{indent}{indent}    context_str = self.context.system_prompt_addition"
                + f"\n{indent}{indent}"
                + f"\n{indent}{indent}mode_strings = []"
                + f"\n{indent}{indent}for mode in self.modes:"
                + f"\n{indent}{indent}    mode_strings.append(mode.system_prompt_addition)"
                + f"\n{indent}{indent}"
                + f"\n{indent}{indent}# Create locals for the template"
                + f'\n{indent}{indent}template_locals = {{"self": self, "context": context_str, "modes": mode_strings}}'
                + f"\n{indent}{indent}"
                + f"\n{indent}{indent}return self._format_prompt('{prompt_name}', template_locals)\n\n{indent}"
            )
        else:
            if len(params) == 0:
                params_str = ""
            else:
                params_str = ", *, " + ", ".join(params)
            methods.append(
                f"def create_{prompt_name}(self{params_str}) -> str:"
                + f"\n{indent}{indent}return self._format_prompt('{prompt_name}', locals())\n\n{indent}"
            )

    for mpl in coll.prompt_lists.values():
        prompt_name = mpl.name
        methods.append(
            f"def get_list_{prompt_name}(self) -> PromptList:" + f"\n{indent}{indent}return self._get_list('{prompt_name}')\n\n{indent}"
        )

    # write prompt factory with added methods
    with open("code_templates/prompt_factory_template.py") as f:
        code = f.read()
    methods_str = "".join(methods)
    code = code.replace("# methods", methods_str)

    prompt_factory_module = f"{package}/llm/prompt_factory.py"
    with open(prompt_factory_module, "w") as f:
        f.write(code)
    log.info(f"Prompt factory generated successfully in {prompt_factory_module}")


if __name__ == "__main__":
    logging.run_main(main)
