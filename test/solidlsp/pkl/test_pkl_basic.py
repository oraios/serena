# SPDX-License-Identifier: GPL-3.0-or-later
import shutil
from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.conftest import start_default_ls_context

pytestmark = pytest.mark.skipif(shutil.which("pkl-lsp") is None, reason="Pkl language server requires the pkl-lsp executable")


@pytest.mark.pkl
class TestPklLanguageServer:
    @pytest.mark.parametrize("language_server", [LanguageServerId.PKL], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.PKL], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Language server starts and attaches to the test repository."""
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [LanguageServerId.PKL], indirect=True)
    def test_definition_within_file(self, language_server: SolidLanguageServer) -> None:
        """The use of ``helper`` in main.pkl resolves to its declaration in lib/shared.pkl."""
        definitions = language_server.request_definition("main.pkl", line=2, column=21)

        definition_lines = self._definition_lines(definitions)
        assert (Path("lib", "shared.pkl").as_posix(), 4) in definition_lines, (
            f"definition of helper not found at lib/shared.pkl:4. Found: {definition_lines}"
        )

    @pytest.mark.parametrize("language_server", [LanguageServerId.PKL], indirect=True)
    def test_definition_across_files_on_a_fresh_server(self, language_server: SolidLanguageServer) -> None:
        """Cross-file definitions must not depend on another request having opened the defining file.

        The module-scoped ``language_server`` fixture is shared, so earlier tests may already have opened
        lib/shared.pkl. This test starts its own server and touches nothing but the referencing file, which
        is what a real session's first request looks like.
        """
        with start_default_ls_context(LanguageServerId.PKL) as fresh_language_server:
            definitions = fresh_language_server.request_definition("main.pkl", line=2, column=21)

        definition_lines = self._definition_lines(definitions)
        assert (Path("lib", "shared.pkl").as_posix(), 4) in definition_lines, (
            f"definition of helper not found at lib/shared.pkl:4. Found: {definition_lines}"
        )

    @pytest.mark.parametrize("language_server", [LanguageServerId.PKL], indirect=True)
    def test_hover(self, language_server: SolidLanguageServer) -> None:
        """Hovering a reference yields the declaration's documentation."""
        hover = language_server.request_hover("main.pkl", line=2, column=21)

        assert hover is not None, "no hover information returned for helper"
        contents = hover["contents"]
        hover_text = contents["value"] if isinstance(contents, dict) else contents
        assert "helper" in hover_text, f"hover for helper does not mention it. Found: {hover_text!r}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.PKL], indirect=True)
    def test_document_symbols_are_empty(self, language_server: SolidLanguageServer) -> None:
        """The server implements no textDocument/documentSymbol, so no symbols are reported.

        The server answers the request with an internal error rather than an unsupported-method error, so
        this asserts that Serena reports the limitation as an empty result instead of failing.
        """
        assert language_server.request_definition("main.pkl", line=2, column=21), "the server does not understand the fixture"

        all_symbols, _ = language_server.request_document_symbols("lib/shared.pkl").get_all_symbols_and_roots()

        assert all_symbols == [], f"expected no symbols from the Pkl language server. Found: {[s['name'] for s in all_symbols]}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.PKL], indirect=True)
    def test_full_symbol_tree_is_empty(self, language_server: SolidLanguageServer) -> None:
        """The project-wide symbol tree is empty as well, so the symbol tools report nothing rather than a file-only tree."""
        assert language_server.request_definition("main.pkl", line=2, column=21), "the server does not understand the fixture"

        assert language_server.request_full_symbol_tree() == []

    @pytest.mark.parametrize("language_server", [LanguageServerId.PKL], indirect=True)
    def test_references_are_empty(self, language_server: SolidLanguageServer) -> None:
        """The server implements no textDocument/references, so Serena reports no references instead of failing.

        The position is the declaration of ``helper``, which main.pkl references, so a server with
        find-references support would not return an empty result here.
        """
        assert language_server.request_definition("main.pkl", line=2, column=21), "the server does not understand the fixture"

        assert language_server.request_references("lib/shared.pkl", line=4, column=9) == []

    @pytest.mark.parametrize("language_server", [LanguageServerId.PKL], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.PKL], indirect=True)
    def test_diagnostics_report_unresolved_references(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """A genuine Pkl error surfaces as a pushed diagnostic, since the server implements no pull requests.

        The generation is sampled before the file is opened, so a publication left over from an earlier
        test cannot satisfy the request.
        """
        broken_relative_path = "diagnostics_sample.pkl"
        broken_content = "module diagnostics_sample\n\nz = doesNotExist\n"
        broken_path = repo_path / broken_relative_path
        broken_path.write_text(broken_content)
        try:
            generation_before = language_server.get_published_diagnostics_generation(broken_relative_path)
            diagnostics = language_server.request_published_text_document_diagnostics(
                broken_relative_path, after_generation=generation_before, timeout=10, allow_cached=False
            )
        finally:
            broken_path.unlink(missing_ok=True)

        assert diagnostics is not None, "no diagnostics were published for the unresolved reference"
        messages = [diagnostic["message"] for diagnostic in diagnostics]
        assert any("doesNotExist" in message for message in messages), (
            f"diagnostic does not name the unresolved reference. Found: {messages}"
        )

    @staticmethod
    def _definition_lines(definitions: list[dict]) -> set[tuple[str, int]]:
        """(relative path, 0-indexed start line) per definition; paths use the platform separator."""
        return {(definition["relativePath"], definition["range"]["start"]["line"]) for definition in definitions}
