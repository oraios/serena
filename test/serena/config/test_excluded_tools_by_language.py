"""Tests for the per-language tool disabling feature (``excluded_tools_by_language``).

Covers configuration parsing/validation, the path->language resolution helper, and the
reverse lookup ``ProjectConfig.excluded_languages_for_tool``.
"""

import logging

import pytest

from serena.config.serena_config import ProjectConfig, languages_for_path
from serena.constants import PROJECT_TEMPLATE_FILE
from solidlsp.ls_config import Language


def _template_data() -> dict:
    data, _ = ProjectConfig._load_yaml_dict(PROJECT_TEMPLATE_FILE)
    data["project_name"] = "test"
    data["languages"] = ["typescript", "haxe", "python"]
    return data


class TestExcludedToolsByLanguageParsing:
    def test_default_is_empty_dict(self):
        config = ProjectConfig(project_name="test", languages=[Language.PYTHON])
        assert config.excluded_tools_by_language == {}

    def test_missing_from_dict_defaults_to_empty(self):
        data = _template_data()
        data.pop("excluded_tools_by_language", None)
        config = ProjectConfig._from_dict(data, local_override_keys=[])
        assert config.excluded_tools_by_language == {}

    def test_valid_map_parses(self):
        data = _template_data()
        data["excluded_tools_by_language"] = {
            "haxe": ["find_symbol", "replace_symbol_body"],
            "python": ["replace_content"],
        }
        config = ProjectConfig._from_dict(data, local_override_keys=[])
        assert config.excluded_tools_by_language == {
            Language.HAXE: ["find_symbol", "replace_symbol_body"],
            Language.PYTHON: ["replace_content"],
        }

    def test_none_value_treated_as_empty(self):
        data = _template_data()
        data["excluded_tools_by_language"] = None
        config = ProjectConfig._from_dict(data, local_override_keys=[])
        assert config.excluded_tools_by_language == {}

    def test_language_alias_is_normalised(self):
        """The 'javascript' alias should be normalised to typescript, consistent with the languages field."""
        data = _template_data()
        data["excluded_tools_by_language"] = {"javascript": ["find_symbol"]}
        config = ProjectConfig._from_dict(data, local_override_keys=[])
        assert config.excluded_tools_by_language == {Language.TYPESCRIPT: ["find_symbol"]}

    def test_unknown_language_raises(self):
        data = _template_data()
        data["excluded_tools_by_language"] = {"klingon": ["find_symbol"]}
        with pytest.raises(ValueError, match="klingon"):
            ProjectConfig._from_dict(data, local_override_keys=[])

    def test_language_not_in_project_raises(self):
        """A valid language that is not among the project's configured languages is an error."""
        data = _template_data()
        data["excluded_tools_by_language"] = {"go": ["find_symbol"]}
        with pytest.raises(ValueError, match="go"):
            ProjectConfig._from_dict(data, local_override_keys=[])

    def test_unknown_tool_raises(self):
        data = _template_data()
        data["excluded_tools_by_language"] = {"haxe": ["this_tool_does_not_exist"]}
        with pytest.raises(ValueError, match="this_tool_does_not_exist"):
            ProjectConfig._from_dict(data, local_override_keys=[])

    def test_language_agnostic_tool_warns(self, caplog):
        data = _template_data()
        data["excluded_tools_by_language"] = {"haxe": ["read_memory"]}
        with caplog.at_level(logging.WARNING):
            config = ProjectConfig._from_dict(data, local_override_keys=[])
        # the entry is still parsed (it is a valid tool name) but a warning is emitted
        assert config.excluded_tools_by_language == {Language.HAXE: ["read_memory"]}
        assert any("read_memory" in msg and "no effect" in msg for msg in caplog.messages)

    def test_roundtrips_through_yaml(self):
        config = ProjectConfig(
            project_name="test",
            languages=[Language.HAXE, Language.PYTHON],
            excluded_tools_by_language={Language.HAXE: ["find_symbol"]},
        )
        d = config._to_yaml_dict()
        assert d["excluded_tools_by_language"] == {"haxe": ["find_symbol"]}


class TestExcludedLanguagesForTool:
    def test_reverse_lookup(self):
        config = ProjectConfig(
            project_name="test",
            languages=[Language.HAXE, Language.PYTHON],
            excluded_tools_by_language={
                Language.HAXE: ["find_symbol", "replace_symbol_body"],
                Language.PYTHON: ["replace_content"],
            },
        )
        assert config.excluded_languages_for_tool("find_symbol") == {Language.HAXE}
        assert config.excluded_languages_for_tool("replace_content") == {Language.PYTHON}
        assert config.excluded_languages_for_tool("search_for_pattern") == set()

    def test_tool_excluded_for_multiple_languages(self):
        config = ProjectConfig(
            project_name="test",
            languages=[Language.HAXE, Language.PYTHON],
            excluded_tools_by_language={
                Language.HAXE: ["find_symbol"],
                Language.PYTHON: ["find_symbol"],
            },
        )
        assert config.excluded_languages_for_tool("find_symbol") == {Language.HAXE, Language.PYTHON}

    def test_empty_config(self):
        config = ProjectConfig(project_name="test", languages=[Language.PYTHON])
        assert config.excluded_languages_for_tool("find_symbol") == set()


class TestLanguagesForPath:
    def test_resolves_haxe(self):
        configured = [Language.TYPESCRIPT, Language.HAXE, Language.PYTHON]
        assert languages_for_path("src/Main.hx", configured) == {Language.HAXE}

    def test_resolves_typescript(self):
        configured = [Language.TYPESCRIPT, Language.HAXE, Language.PYTHON]
        assert languages_for_path("src/main.ts", configured) == {Language.TYPESCRIPT}

    def test_resolves_python(self):
        configured = [Language.TYPESCRIPT, Language.HAXE, Language.PYTHON]
        assert languages_for_path("src/main.py", configured) == {Language.PYTHON}

    def test_unmatched_extension_returns_empty(self):
        configured = [Language.TYPESCRIPT, Language.HAXE, Language.PYTHON]
        assert languages_for_path("README.md", configured) == set()

    def test_scoped_to_configured_languages_only(self):
        """A .go file must not resolve to Go if Go is not configured."""
        configured = [Language.TYPESCRIPT, Language.HAXE]
        assert languages_for_path("main.go", configured) == set()

    def test_extension_overlap_returns_all_matching(self):
        """If two configured languages match the same extension, both are returned."""
        # both cpp and c share the .h extension via the cpp matcher; here we use a clearer case:
        # typescript matches .js, and so does vue. With both configured, a .js file matches both.
        configured = [Language.TYPESCRIPT, Language.VUE]
        assert languages_for_path("app.js", configured) == {Language.TYPESCRIPT, Language.VUE}
