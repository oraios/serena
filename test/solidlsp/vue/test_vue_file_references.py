# SPDX-License-Identifier: MIT
"""Component references queried from the component's own script setup."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.language_servers.vue_language_server import VueLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.conftest import get_repo_path, start_ls_context

pytestmark = pytest.mark.vue


@pytest.fixture(scope="module")
def language_server() -> Iterator[SolidLanguageServer]:
    root = get_repo_path(LanguageServerId.VUE).parent / "component_references"
    with start_ls_context(LanguageServerId.VUE, repo_path=str(root)) as server:
        yield server


def test_component_references_from_script_setup(language_server: SolidLanguageServer) -> None:
    symbols = language_server.request_document_symbols("src/components/Child.vue").get_all_symbols_and_roots()[0]
    script = next(symbol for symbol in symbols if symbol["name"] == "script setup")
    start = script["selectionRange"]["start"]

    references = language_server.request_references("src/components/Child.vue", start["line"], start["character"])

    by_path = {Path(ref["relativePath"]).as_posix(): ref for ref in references}
    assert set(by_path) == {"src/components/Parent.vue", "src/components/使用 方.vue"}
    for relative_path, ref in by_path.items():
        source = Path(ref["absolutePath"]).read_text(encoding="utf-8").splitlines()[1]
        start_col = len(source[: source.index("./Child.vue")].encode("utf-16-le")) // 2
        assert ref["range"] == {
            "start": {"line": 1, "character": start_col},
            "end": {"line": 1, "character": start_col + len("./Child.vue")},
        }, (relative_path, ref)
    assert len(references) == len(by_path)


def test_unused_component_has_no_references(language_server: SolidLanguageServer) -> None:
    assert language_server.request_references("src/components/UnusedChild.vue", 0, 1) == []


def test_component_reference_tracks_open_file_edits(language_server: SolidLanguageServer) -> None:
    assert isinstance(language_server, VueLanguageServer)
    path = "src/components/Parent.vue"
    with language_server.open_file(path):
        language_server.insert_text_at_position(path, 1, 0, "// shifted import\n")
        try:
            references = language_server.request_file_references("src/components/Child.vue")
            parent_refs = [ref for ref in references if Path(ref["relativePath"]).as_posix() == path]
            assert len(parent_refs) == 1
            assert parent_refs[0]["range"] == {
                "start": {"line": 2, "character": 19},
                "end": {"line": 2, "character": 30},
            }
        finally:
            language_server.delete_text_between_positions(path, {"line": 1, "character": 0}, {"line": 2, "character": 0})
