# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

import pytest

from serena.tools import SUCCESS_RESULT
from serena.tools.symbol_tools import SafeDeleteSymbol
from solidlsp.ls_config import LanguageServerId
from test.conftest import agent_for_project_context


@pytest.mark.vue
def test_safe_delete_vue_symbol(tmp_path: Path) -> None:
    source = (
        '<script setup lang="ts">\n'
        "function unusedHelper(): number {\n  return 42\n}\n"
        "function usedHelper(): number {\n  return 1\n}\n"
        "const result = usedHelper()\n"
        "</script>\n<template>{{ result }}</template>\n"
    )
    component = tmp_path / "Parent.vue"
    component.write_text(source, encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text('{"include": ["*.vue"]}', encoding="utf-8")
    (tmp_path / ".serena").mkdir()
    (tmp_path / ".serena" / "project.yml").write_text("project_name: vue_safe_delete\nlanguage_servers: [vue]\n", encoding="utf-8")

    with agent_for_project_context(LanguageServerId.VUE, repo_root_override=str(tmp_path)) as agent:
        tool = agent.get_tool(SafeDeleteSymbol)
        result = tool.apply(name_path_pattern="script setup/usedHelper", relative_path="Parent.vue")
        assert "Cannot delete" in result
        assert component.read_text(encoding="utf-8") == source

        result = tool.apply(name_path_pattern="script setup/unusedHelper", relative_path="Parent.vue")
        assert result == SUCCESS_RESULT
        assert component.read_text(encoding="utf-8") == source.replace("function unusedHelper(): number {\n  return 42\n}\n", "")
