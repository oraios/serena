import logging
import os
from enum import Enum
from typing import Any, Generic, Literal, TypeVar

import yaml
from sensai.util.string import ToStringMixin

from .jinja_template import JinjaTemplate, ParameterizedTemplateInterface

log = logging.getLogger(__name__)


class PromptTemplate(ToStringMixin, ParameterizedTemplateInterface):
    def __init__(self, name: str, jinja_template_string: str) -> None:
        self.name = name
        self._jinja_template = JinjaTemplate(jinja_template_string.strip())

    def _tostring_exclude_private(self) -> bool:
        return True

    def render(self, **params: Any) -> str:
        return self._jinja_template.render(**params)

    def get_parameters(self) -> list[str]:
        return self._jinja_template.get_parameters()


class PromptList:
    def __init__(self, items: list[str]) -> None:
        self.items = [x.strip() for x in items]

    def to_string(self) -> str:
        bullet = " * "
        indent = " " * len(bullet)
        items = [x.replace("\n", "\n" + indent) for x in self.items]
        return "\n * ".join(items)


T = TypeVar("T")
DEFAULT_LANG_CODE = "default"


class LanguageFallbackMode(Enum):
    """
    Defines what to do if there is no item for the given language.
    """

    ANY = "any"
    """
    Return the item for any language (the first one found)
    """
    EXCEPTION = "exception"
    """
    If the requested language is not found, raise an exception
    """
    USE_DEFAULT_LANG = "use_default_lang"
    """
    If the requested language is not found, use the default language
    """


class _MultiLangContainer(Generic[T], ToStringMixin):
    """
    A container of items (usually, all having the same semantic meaning) which are associated with different languages.
    Can also be used for single-language purposes by always using the default language code.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._lang2item: dict[str, T] = {}
        """Maps language codes to items"""

    def _tostring_excludes(self) -> list[str]:
        return ["lang2item"]

    def _tostring_additional_entries(self) -> dict[str, Any]:
        return dict(languages=list(self._lang2item.keys()))

    def get_language_codes(self) -> list[str]:
        """The language codes for which items are registered in the container."""
        return list(self._lang2item.keys())

    def add_item(self, item: T, lang_code: str = DEFAULT_LANG_CODE, allow_overwrite: bool = False) -> None:
        """Adds an item to the container, representing the same semantic entity as the other items in the container but in a different language.

        :param item: the item to add
        :param lang_code: the language shortcode for which to add the item. Use the default for single-language use cases.
        :param allow_overwrite: if True, allow overwriting an existing entry for the same language
        """
        if not allow_overwrite and lang_code in self._lang2item:
            raise KeyError(f"Item for language '{lang_code}' already registered for name '{self.name}'")
        self._lang2item[lang_code] = item

    def has_item(self, lang_code: str = DEFAULT_LANG_CODE) -> bool:
        return lang_code in self._lang2item

    def get_item(self, lang: str = DEFAULT_LANG_CODE, fallback_mode: LanguageFallbackMode = LanguageFallbackMode.EXCEPTION) -> T:
        """
        Gets the item for the given language.

        :param lang: the language shortcode for which to obtain the prompt template. A default language can be specified.
        :param fallback_mode: defines what to do if there is no item for the given language
        :return: the item
        """
        try:
            return self._lang2item[lang]
        except KeyError as outer_e:
            if fallback_mode == LanguageFallbackMode.EXCEPTION:
                raise KeyError(f"Item for language '{lang}' not found for name '{self.name}'") from outer_e
            if fallback_mode == LanguageFallbackMode.ANY:
                try:
                    return next(iter(self._lang2item.values()))
                except StopIteration as e:
                    raise KeyError(f"No items registered for any language in container '{self.name}'") from e
            if fallback_mode == LanguageFallbackMode.USE_DEFAULT_LANG:
                try:
                    return self._lang2item[DEFAULT_LANG_CODE]
                except KeyError as e:
                    raise KeyError(
                        f"Item not found neither for {lang=} nor for the default language '{DEFAULT_LANG_CODE}' in container '{self.name}'"
                    ) from e

    def __len__(self) -> int:
        return len(self._lang2item)


class MultiLangPromptTemplate(ParameterizedTemplateInterface):
    """
    Represents a prompt template with support for multiple languages.
    The parameters of all prompt templates (for all languages) are (must be) the same.
    """

    def __init__(self, name: str) -> None:
        self._prompts_container = _MultiLangContainer[PromptTemplate](name)

    def __len__(self) -> int:
        return len(self._prompts_container)

    @property
    def name(self) -> str:
        return self._prompts_container.name

    def add_prompt_template(
        self, prompt_template: PromptTemplate, lang_code: str = DEFAULT_LANG_CODE, allow_overwrite: bool = False
    ) -> None:
        """
        Adds a prompt template for a new language.
        The parameters of all prompt templates (for all languages) are (must be) the same, so if a prompt template is already registered,
        the parameters of the new prompt template should be the same as the existing ones.

        :param prompt_template: the prompt template to add
        :param lang_code: the language code for which to add the prompt template. For single-language use cases, you should always use the default language code.
        :param allow_overwrite: whether to allow overwriting an existing entry for the same language
        """
        incoming_parameters = prompt_template.get_parameters()
        if len(self) > 0:
            parameters = self.get_parameters()
            if parameters != incoming_parameters:
                raise ValueError(
                    f"Cannot add prompt template for language '{lang_code}' to MultiLangPromptTemplate '{self.name}'"
                    f"because the parameters are inconsistent: {parameters} vs {prompt_template.get_parameters()}"
                )

        self._prompts_container.add_item(prompt_template, lang_code, allow_overwrite)

    def get_prompt_template(
        self, lang_code: str = DEFAULT_LANG_CODE, fallback_mode: LanguageFallbackMode = LanguageFallbackMode.EXCEPTION
    ) -> PromptTemplate:
        return self._prompts_container.get_item(lang_code, fallback_mode)

    def get_parameters(self) -> list[str]:
        if len(self) == 0:
            raise RuntimeError(
                f"No prompt templates registered for MultiLangPromptTemplate '{self.name}', make sure to register a prompt template before accessing the parameters"
            )
        first_prompt_template = next(iter(self._prompts_container._lang2item.values()))
        return first_prompt_template.get_parameters()

    def render(
        self,
        params: dict[str, Any],
        lang_code: str = DEFAULT_LANG_CODE,
        fallback_mode: LanguageFallbackMode = LanguageFallbackMode.EXCEPTION,
    ) -> str:
        prompt_template = self.get_prompt_template(lang_code, fallback_mode)
        return prompt_template.render(**params)

    def has_item(self, lang_code: str = DEFAULT_LANG_CODE) -> bool:
        return self._prompts_container.has_item(lang_code)


class MultiLangPromptList(_MultiLangContainer[PromptList]):
    pass


class MultiLangPromptCollection:
    """
    Main class for managing a collection of prompt templates and prompt lists, with support for multiple languages.
    All data will be read from the yamls directly contained in the given directory on initialization.
    It is thus assumed that you manage one directory per prompt collection.

    The yamls are assumed to be either of the form

    ```yaml
    lang: <language_code> # optional, defaults to "default"
    prompts:
      <prompt_name>:
        <prompt_template_string>
      <prompt_list_name>: [<prompt_string_1>, <prompt_string_2>, ...]

    ```

    When specifying prompt templates for multiple languages, make sure that the Jinja template parameters
    (inferred from the things inside the `{{ }}` in the template strings) are the same for all languages
    (you will get an exception otherwise).

    The prompt names must be unique (for the same language) within the collection.
    """

    def __init__(self, prompts_dir: str | list[str], fallback_mode: LanguageFallbackMode = LanguageFallbackMode.EXCEPTION) -> None:
        """
        :param prompts_dir: the directory containing the prompt templates and prompt lists.
            If a list is provided, will look for prompt templates in the dirs from left to right
            (first one containing the desired template wins).
        :param fallback_mode: the fallback mode to use when a prompt template or prompt list is not found for the requested language.
            May be reset after initialization.
        """
        self._multi_lang_prompt_templates: dict[str, MultiLangPromptTemplate] = {}
        self._multi_lang_prompt_lists: dict[str, MultiLangPromptList] = {}
        if isinstance(prompts_dir, str):
            prompts_dir = [prompts_dir]

        # Add prompts from multiple directories, prioritizing names from the left.
        # If name collisions appear in the first directory, an error is raised (so the first directory should have no
        # internal collisions, this helps in avoiding errors)
        # For all following directories, on a collision the new value will be ignored.
        # This also means that for the following directories, there is no error check on collisions internal to them.
        # We assume that they are correct (i.e., they have no internal collisions).
        first_prompts_dir, fallback_prompt_dirs = prompts_dir[0], prompts_dir[1:]
        self._load_from_disc(first_prompts_dir, on_name_collision="raise")
        for fallback_prompt_dir in fallback_prompt_dirs:
            # already loaded prompts have priority
            self._load_from_disc(fallback_prompt_dir, on_name_collision="skip")

        self.fallback_mode = fallback_mode

    def _add_prompt_template(
        self,
        name: str,
        template_str: str,
        lang_code: str = DEFAULT_LANG_CODE,
        on_name_collision: Literal["skip", "overwrite", "raise"] = "raise",
    ) -> None:
        """
        :param name: name of the prompt template
        :param template_str: the Jinja template string
        :param lang_code: the language code for which to add the prompt template.
        :param on_name_collision: how to deal with name/lang_code collisions
        """
        allow_overwrite = False
        prompt_template = PromptTemplate(name, template_str)
        mlpt = self._multi_lang_prompt_templates.get(name)
        if mlpt is None:
            mlpt = MultiLangPromptTemplate(name)
            self._multi_lang_prompt_templates[name] = mlpt
        if mlpt.has_item(lang_code):
            if on_name_collision == "raise":
                raise KeyError(f"Prompt '{name}' for {lang_code} already exists!")
            if on_name_collision == "skip":
                log.debug(f"Skipping prompt '{name}' since it already exists.")
                return
            elif on_name_collision == "overwrite":
                allow_overwrite = True
        mlpt.add_prompt_template(prompt_template, lang_code=lang_code, allow_overwrite=allow_overwrite)

    def _add_prompt_list(
        self,
        name: str,
        prompt_list: list[str],
        lang_code: str = DEFAULT_LANG_CODE,
        on_name_collision: Literal["skip", "overwrite", "raise"] = "raise",
    ) -> None:
        """
        :param name: name of the prompt list
        :param prompt_list: a list of prompts
        :param lang_code: the language code for which to add the prompt list.
        :param on_name_collision: how to deal with name/lang_code collisions
        """
        allow_overwrite = False
        multilang_prompt_list = self._multi_lang_prompt_lists.get(name)
        if multilang_prompt_list is None:
            multilang_prompt_list = MultiLangPromptList(name)
            self._multi_lang_prompt_lists[name] = multilang_prompt_list
        if multilang_prompt_list.has_item(lang_code):
            if on_name_collision == "raise":
                raise KeyError(f"Prompt '{name}' for {lang_code} already exists!")
            if on_name_collision == "skip":
                log.debug(f"Skipping prompt '{name}' since it already exists.")
                return
            elif on_name_collision == "overwrite":
                allow_overwrite = True
        multilang_prompt_list.add_item(PromptList(prompt_list), lang_code=lang_code, allow_overwrite=allow_overwrite)

    def _load_from_disc(self, prompts_dir: str, on_name_collision: Literal["skip", "overwrite", "raise"] = "raise") -> None:
        """Loads all prompt templates and prompt lists from yaml files in the given directory.

        :param prompts_dir:
        :param on_name_collision: how to deal with name/lang_code collisions
        """
        for fn in os.listdir(prompts_dir):
            if not fn.endswith((".yml", ".yaml")):
                log.debug(f"Skipping non-YAML file: {fn}")
                continue
            path = os.path.join(prompts_dir, fn)
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            try:
                prompts_data = data["prompts"]
            except KeyError as e:
                raise KeyError(f"Invalid yaml structure (missing 'prompts' key) in file {path}") from e

            lang_code = prompts_data.get("lang", DEFAULT_LANG_CODE)
            # add the data to the collection
            for prompt_name, prompt_template_or_list in prompts_data.items():
                if isinstance(prompt_template_or_list, list):
                    self._add_prompt_list(prompt_name, prompt_template_or_list, lang_code=lang_code, on_name_collision=on_name_collision)
                elif isinstance(prompt_template_or_list, str):
                    self._add_prompt_template(
                        prompt_name, prompt_template_or_list, lang_code=lang_code, on_name_collision=on_name_collision
                    )
                else:
                    raise ValueError(
                        f"Invalid prompt type for {prompt_name} in file {path} (should be str or list): {prompt_template_or_list}"
                    )

    def get_prompt_template_names(self) -> list[str]:
        return list(self._multi_lang_prompt_templates.keys())

    def get_prompt_list_names(self) -> list[str]:
        return list(self._multi_lang_prompt_lists.keys())

    def __len__(self) -> int:
        return len(self._multi_lang_prompt_templates)

    def get_multilang_prompt_template(self, prompt_name: str) -> MultiLangPromptTemplate:
        """The MultiLangPromptTemplate object for the given prompt name. For single-language use cases, you should use the `get_prompt_template` method instead."""
        return self._multi_lang_prompt_templates[prompt_name]

    def get_multilang_prompt_list(self, prompt_name: str) -> MultiLangPromptList:
        return self._multi_lang_prompt_lists[prompt_name]

    def get_prompt_template(
        self,
        prompt_name: str,
        lang_code: str = DEFAULT_LANG_CODE,
    ) -> PromptTemplate:
        """The PromptTemplate object for the given prompt name and language code."""
        return self.get_multilang_prompt_template(prompt_name).get_prompt_template(lang_code=lang_code, fallback_mode=self.fallback_mode)

    def get_prompt_template_parameters(self, prompt_name: str) -> list[str]:
        """The parameters of the PromptTemplate object for the given prompt name."""
        return self.get_multilang_prompt_template(prompt_name).get_parameters()

    def get_prompt_list(self, prompt_name: str, lang_code: str = DEFAULT_LANG_CODE) -> PromptList:
        """The PromptList object for the given prompt name and language code."""
        return self.get_multilang_prompt_list(prompt_name).get_item(lang_code)

    def _has_prompt_list(self, prompt_name: str, lang_code: str = DEFAULT_LANG_CODE) -> bool:
        multi_lang_prompt_list = self._multi_lang_prompt_lists.get(prompt_name)
        if multi_lang_prompt_list is None:
            return False
        return multi_lang_prompt_list.has_item(lang_code)

    def _has_prompt_template(self, prompt_name: str, lang_code: str = DEFAULT_LANG_CODE) -> bool:
        multi_lang_prompt_template = self._multi_lang_prompt_templates.get(prompt_name)
        if multi_lang_prompt_template is None:
            return False
        return multi_lang_prompt_template.has_item(lang_code)

    def render_prompt_template(
        self,
        prompt_name: str,
        params: dict[str, Any],
        lang_code: str = DEFAULT_LANG_CODE,
    ) -> str:
        """Renders the prompt template for the given prompt name and language code."""
        return self.get_prompt_template(prompt_name, lang_code=lang_code).render(**params)
