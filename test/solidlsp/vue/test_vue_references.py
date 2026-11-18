# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest

from solidlsp.ls_config import LanguageServerId
from test.conftest import start_ls_context


@pytest.mark.vue
@pytest.mark.parametrize("extension", ["vue", "ts", "js"])
def test_references_exclude_declarations(tmp_path: Path, extension: str) -> None:
    source = "function unusedHelper() { return 42 }\nfunction usedHelper() { return 1 }\nconst result = usedHelper()\n"
    if extension == "vue":
        source = '<script setup lang="ts">\n' + source + "</script>\n<template>{{ result }}</template>\n"
    relative_path = f"References.{extension}"
    (tmp_path / relative_path).write_text(source, encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {"allowJs": true}, "include": ["*"]}', encoding="utf-8")

    with start_ls_context(LanguageServerId.VUE, repo_path=str(tmp_path)) as language_server:
        declaration_line = 1 if extension == "vue" else 0
        assert language_server.request_references(relative_path, declaration_line, 9) == []
        references = language_server.request_references(relative_path, declaration_line + 1, 9)
        assert [(ref["relativePath"], ref["range"]["start"]) for ref in references] == [
            (relative_path, {"line": declaration_line + 2, "character": 15})
        ]
