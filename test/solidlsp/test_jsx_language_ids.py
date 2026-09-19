# SPDX-License-Identifier: MIT
"""LanguageId mapping for .tsx/.jsx across Angular, Vue and Svelte adapters.

Regression guard for the same failure mode fixed for typescript-language-server in
#1436: opening JSX with ``typescript``/``javascript`` makes the parser treat JSX as
syntax errors and truncate symbol ranges at the first multi-line expression.

These unit tests call ``_get_language_id_for_file`` without starting a language
server, so a revert of the mapping fails CI even when LS integration tests are
deselected.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from solidlsp.language_servers.angular_language_server import AngularLanguageServer, AngularTypeScriptServer
from solidlsp.language_servers.svelte_language_server import SvelteLanguageServer, SvelteTypeScriptServer
from solidlsp.language_servers.vue_language_server import VueLanguageServer, VueTypeScriptServer

# Mapping methods may fall through to ``self.language_id`` for non-JSX extensions.
_SELF = SimpleNamespace(language_id="svelte", repository_root_path="/tmp")

_ADAPTORS = [
    pytest.param(AngularTypeScriptServer, id="angular-ts-companion"),
    pytest.param(AngularLanguageServer, id="angular"),
    pytest.param(VueTypeScriptServer, id="vue-ts-companion"),
    pytest.param(VueLanguageServer, id="vue"),
    pytest.param(SvelteTypeScriptServer, id="svelte-ts-companion"),
    pytest.param(SvelteLanguageServer, id="svelte"),
]


@pytest.mark.parametrize("server_cls", _ADAPTORS)
def test_tsx_uses_typescriptreact(server_cls) -> None:
    # The mapping methods only inspect the path for JSX; they do not need a live server.
    assert server_cls._get_language_id_for_file(_SELF, "component.tsx") == "typescriptreact"
    assert server_cls._get_language_id_for_file(_SELF, "src/app/Widget.TSX") == "typescriptreact"


@pytest.mark.parametrize("server_cls", _ADAPTORS)
def test_jsx_uses_javascriptreact(server_cls) -> None:
    assert server_cls._get_language_id_for_file(_SELF, "component.jsx") == "javascriptreact"
    assert server_cls._get_language_id_for_file(_SELF, "src/lib/Widget.JSX") == "javascriptreact"


@pytest.mark.parametrize("server_cls", _ADAPTORS)
def test_plain_ts_and_js_unchanged(server_cls) -> None:
    assert server_cls._get_language_id_for_file(_SELF, "mod.ts") == "typescript"
    assert server_cls._get_language_id_for_file(_SELF, "mod.js") == "javascript"


@pytest.mark.parametrize(
    ("server_cls", "path", "expected"),
    [
        pytest.param(AngularTypeScriptServer, "app.component.html", "html", id="angular-ts-html"),
        pytest.param(AngularLanguageServer, "app.component.html", "html", id="angular-html"),
        pytest.param(VueTypeScriptServer, "src/App.vue", "vue", id="vue-ts-vue"),
        pytest.param(VueLanguageServer, "src/App.vue", "vue", id="vue-vue"),
        pytest.param(SvelteTypeScriptServer, "src/lib/components/Header.svelte", "svelte", id="svelte-ts-svelte"),
        # SvelteLanguageServer falls through to self.language_id for .svelte (instance default "svelte")
        pytest.param(SvelteLanguageServer, "src/lib/components/Header.svelte", "svelte", id="svelte-svelte"),
    ],
)
def test_framework_specific_extensions_preserved(server_cls, path: str, expected: str) -> None:
    self = SimpleNamespace(language_id=expected)
    assert server_cls._get_language_id_for_file(self, path) == expected
