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


class _FakeFB:
    def __init__(self, language_id: str) -> None:
        self.language_id = language_id


class _FakeNotify:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict | None]] = []

    def send_notification(self, method: str, params: dict | None = None) -> None:
        self.sent.append((method, params))


class _FakeServer:
    def __init__(self) -> None:
        self.notify = _FakeNotify()


class _FakeSvelteLS:
    """Minimal stand-in for SvelteLanguageServer._wrap_notify_send_for_ts_js_mirror."""

    def __init__(self) -> None:
        self.server = _FakeServer()
        self.open_file_buffers: dict[str, _FakeFB] = {}


@pytest.mark.parametrize(
    ("uri", "language_id", "expect_mirror"),
    [
        pytest.param("file:///proj/a.tsx", "typescriptreact", True, id="tsx-typescriptreact"),
        pytest.param("file:///proj/b.jsx", "javascriptreact", True, id="jsx-javascriptreact"),
        pytest.param("file:///proj/c.ts", "typescript", True, id="ts-typescript"),
        pytest.param("file:///proj/d.js", "javascript", True, id="js-javascript"),
        pytest.param("file:///proj/e.mts", "typescript", True, id="mts-typescript"),
        pytest.param("file:///proj/f.mjs", "javascript", True, id="mjs-javascript"),
        pytest.param("file:///proj/g.svelte", "svelte", False, id="svelte-skipped"),
        pytest.param("file:///proj/App.vue", "vue", False, id="vue-skipped"),
    ],
)
def test_svelte_did_change_mirror_follows_ts_js_extensions(uri: str, language_id: str, expect_mirror: bool) -> None:
    """Svelte $/onDidChangeTsOrJsFile must include .tsx/.jsx after typescriptreact mapping.

    A languageId whitelist dropped those files once they opened as typescriptreact/javascriptreact
    (review on #2066); the check now uses `_is_ts_file`, shared with the rest of SvelteLanguageServer.
    """
    ls = _FakeSvelteLS()
    SvelteLanguageServer._wrap_notify_send_for_ts_js_mirror(ls)
    ls.open_file_buffers[uri] = _FakeFB(language_id)

    changes = [{"text": "x"}]
    ls.server.notify.send_notification(
        "textDocument/didChange",
        {"textDocument": {"uri": uri}, "contentChanges": changes},
    )

    assert ("textDocument/didChange", {"textDocument": {"uri": uri}, "contentChanges": changes}) in ls.server.notify.sent
    mirror = ("$/onDidChangeTsOrJsFile", {"uri": uri, "changes": changes})
    if expect_mirror:
        assert mirror in ls.server.notify.sent
    else:
        assert mirror not in ls.server.notify.sent


def test_svelte_did_change_mirror_skips_when_no_open_buffer() -> None:
    ls = _FakeSvelteLS()
    SvelteLanguageServer._wrap_notify_send_for_ts_js_mirror(ls)
    uri = "file:///proj/orphan.tsx"
    changes = [{"text": "x"}]
    ls.server.notify.send_notification(
        "textDocument/didChange",
        {"textDocument": {"uri": uri}, "contentChanges": changes},
    )
    assert ("$/onDidChangeTsOrJsFile", {"uri": uri, "changes": changes}) not in ls.server.notify.sent
