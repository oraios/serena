"""Basic integration tests for the Bazel/Starlark language server (starpls)."""

from pathlib import Path

import pytest

from serena.util.text_utils import find_text_coordinates
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_types import SymbolKind
from solidlsp.ls_utils import SymbolUtils
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, read_repo_file, request_all_symbols


@pytest.mark.starlark
class TestStarlarkLanguageServer:
    """Verifies that starpls drives the symbol and reference APIs Serena depends on.

    The test repo (``test/resources/repos/starlark/test_repo``) is a minimal Bazel module
    without external dependencies (so behavior is identical with and without bazel installed):

    - ``defs.bzl`` defines ``TOOL_VERSION``, ``format_label`` (uses ``TOOL_VERSION``) and
      ``gen_files`` (calls ``format_label``).
    - ``BUILD.bazel`` loads ``gen_files``/``TOOL_VERSION`` from ``defs.bzl``, declares the
      ``:docs`` target and the ``config_version`` variable.
    - ``src/BUILD.bazel`` loads ``gen_files`` and declares ``:src_docs``.
    - ``src/main.star`` is standard-dialect Starlark defining ``GREETING_PREFIX`` and ``greet``.

    Note: starpls (v0.1.22) resolves ``textDocument/references`` only within the file the
    request is made in; cross-file navigation is covered via ``textDocument/definition``,
    which resolves through ``load()`` statements.
    """

    @pytest.mark.parametrize("language_server", [LanguageServerId.STARLARK], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.STARLARK], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """The server starts and reports the expected repository root."""
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [LanguageServerId.STARLARK], indirect=True)
    def test_document_symbols_defs_bzl(self, language_server: SolidLanguageServer) -> None:
        """``defs.bzl`` exposes its constant and functions with the expected kinds."""
        all_symbols, _root_symbols = language_server.request_document_symbols("defs.bzl").get_all_symbols_and_roots()

        symbols_by_name = {s.get("name"): s for s in all_symbols}
        for expected in ("TOOL_VERSION", "format_label", "gen_files"):
            assert expected in symbols_by_name, f"{expected} missing from defs.bzl symbols: {sorted(symbols_by_name)}"

        assert symbols_by_name["format_label"]["kind"] == SymbolKind.Function
        assert symbols_by_name["gen_files"]["kind"] == SymbolKind.Function
        assert symbols_by_name["TOOL_VERSION"]["kind"] == SymbolKind.Variable

    @pytest.mark.parametrize("language_server", [LanguageServerId.STARLARK], indirect=True)
    def test_document_symbols_build_file(self, language_server: SolidLanguageServer) -> None:
        """``BUILD.bazel`` exposes its target (as ``:docs``) and top-level variable, but not load items."""
        all_symbols, _root_symbols = language_server.request_document_symbols("BUILD.bazel").get_all_symbols_and_roots()

        names = [s.get("name") for s in all_symbols]
        assert ":docs" in names, f"Expected the :docs target in BUILD.bazel symbols: {names}"
        assert "config_version" in names, f"Expected config_version in BUILD.bazel symbols: {names}"
        # names brought in via load() are not document symbols in starpls
        assert "gen_files" not in names, f"load()ed names must not appear as document symbols: {names}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.STARLARK], indirect=True)
    def test_full_symbol_tree_contains_cross_file_names(self, language_server: SolidLanguageServer) -> None:
        """The repository-wide symbol tree covers .bzl, BUILD.bazel and .star files."""
        symbols = language_server.request_full_symbol_tree()

        for expected in (
            "TOOL_VERSION",  # defs.bzl
            "format_label",  # defs.bzl
            "gen_files",  # defs.bzl
            ":docs",  # BUILD.bazel
            "config_version",  # BUILD.bazel
            ":src_docs",  # src/BUILD.bazel
            "GREETING_PREFIX",  # src/main.star
            "greet",  # src/main.star
        ):
            assert SymbolUtils.symbol_tree_contains_name(symbols, expected), f"{expected} missing from full symbol tree"

    @pytest.mark.parametrize("language_server", [LanguageServerId.STARLARK], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.STARLARK], indirect=True)
    def test_find_definition_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """``gen_files`` called in ``BUILD.bazel`` resolves to its definition in ``defs.bzl``."""
        build_content = read_repo_file(language_server, "BUILD.bazel")
        call_coords = find_text_coordinates(build_content, r"^(gen_files)\(")
        assert call_coords is not None, "Could not locate the gen_files call in BUILD.bazel"

        definitions = language_server.request_definition(str(repo_path / "BUILD.bazel"), call_coords.line, call_coords.col + 1)
        assert definitions, f"Expected a definition for gen_files, got {definitions=}"

        defs_content = read_repo_file(language_server, "defs.bzl")
        def_coords = find_text_coordinates(defs_content, r"def (gen_files)\(")
        assert def_coords is not None

        target = definitions[0]
        assert target["uri"].endswith("defs.bzl"), f"Expected definition in defs.bzl, got {target['uri']}"
        assert target["range"]["start"]["line"] == def_coords.line, f"Expected definition at line {def_coords.line}, got {target}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.STARLARK], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.STARLARK], indirect=True)
    def test_find_definition_within_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """The ``format_label`` call inside ``gen_files`` resolves to its definition."""
        defs_content = read_repo_file(language_server, "defs.bzl")
        call_coords = find_text_coordinates(defs_content, r"labels\.append\((format_label)\(")
        assert call_coords is not None, "Could not locate the format_label call in defs.bzl"

        definitions = language_server.request_definition(str(repo_path / "defs.bzl"), call_coords.line, call_coords.col + 1)
        assert definitions, f"Expected a definition for format_label, got {definitions=}"

        def_coords = find_text_coordinates(defs_content, r"def (format_label)\(")
        assert def_coords is not None

        target = definitions[0]
        assert target["uri"].endswith("defs.bzl")
        assert target["range"]["start"]["line"] == def_coords.line, f"Expected definition at line {def_coords.line}, got {target}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.STARLARK], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.STARLARK], indirect=True)
    def test_find_references_function_within_file(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """References for ``format_label`` from its definition site include its call site.

        starpls (v0.1.22) resolves references only within the requested file; cross-file
        coverage is provided by ``test_find_definition_across_files``.
        """
        defs_content = read_repo_file(language_server, "defs.bzl")
        def_coords = find_text_coordinates(defs_content, r"def (format_label)\(")
        assert def_coords is not None

        references = language_server.request_references(str(repo_path / "defs.bzl"), def_coords.line, def_coords.col + 1)
        assert references, f"Expected references for format_label, got {references=}"

        call_coords = find_text_coordinates(defs_content, r"labels\.append\((format_label)\(")
        assert call_coords is not None
        ref_pairs = {(ref["uri"].split("/")[-1], ref["range"]["start"]["line"]) for ref in references}
        assert ("defs.bzl", call_coords.line) in ref_pairs, f"Expected the call site at line {call_coords.line}, got {sorted(ref_pairs)}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.STARLARK], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.STARLARK], indirect=True)
    def test_find_references_constant_from_use_site(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """References for ``TOOL_VERSION`` from its use site include declaration and use."""
        defs_content = read_repo_file(language_server, "defs.bzl")
        use_coords = find_text_coordinates(defs_content, r'"-" \+ (TOOL_VERSION)')
        assert use_coords is not None, "Could not locate the TOOL_VERSION use in defs.bzl"

        references = language_server.request_references(str(repo_path / "defs.bzl"), use_coords.line, use_coords.col + 1)
        assert references, f"Expected references for TOOL_VERSION, got {references=}"

        decl_coords = find_text_coordinates(defs_content, r"^(TOOL_VERSION) = ")
        assert decl_coords is not None
        ref_lines = {ref["range"]["start"]["line"] for ref in references if ref["uri"].endswith("defs.bzl")}
        assert {decl_coords.line, use_coords.line} <= ref_lines, (
            f"Expected declaration line {decl_coords.line} and use line {use_coords.line} in {sorted(ref_lines)}"
        )

    @pytest.mark.parametrize("language_server", [LanguageServerId.STARLARK], indirect=True)
    def test_bare_symbol_names(self, language_server: SolidLanguageServer) -> None:
        """Starlark symbols must have bare names (no whitespace/bracket/paren/comma pollution).

        ``:`` is allowed because starpls names BUILD targets ``:<target_name>`` by design.
        """
        malformed_symbols = [s for s in request_all_symbols(language_server) if has_malformed_name(s, colon_allowed=True)]
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )
