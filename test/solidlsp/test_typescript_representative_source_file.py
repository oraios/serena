"""Regression test for oraios/serena#2090: additional-workspace activation must not pick a
root-level tool config (vitest.config.ts, jest.config.ts, ...) adjacent to tsconfig.json over
the project's actual source tree.

Exercises TypeScriptLanguageServer._find_representative_source_file directly against a real
filesystem layout, without spawning a language server process; same technique as
test_typescript_timeout_policy.py's _bare_ts_server.
"""

from solidlsp.language_servers.typescript_language_server import TypeScriptLanguageServer


def _bare_ts_server() -> TypeScriptLanguageServer:
    return object.__new__(TypeScriptLanguageServer)


class TestFindRepresentativeSourceFile:
    def test_prefers_nested_src_file_over_adjacent_tool_config(self, tmp_path) -> None:
        """The issue's own minimal layout: a tsconfig-adjacent vitest.config.ts must lose to a
        real source file nested under src/, even when that source file is not directly inside
        src/ itself (it is one level further down, under src/routes/).
        """
        pkg = tmp_path / "apps" / "api"
        routes = pkg / "src" / "routes"
        routes.mkdir(parents=True)
        (pkg / "tsconfig.json").write_text("{}")
        (pkg / "vitest.config.ts").write_text("export default {};")
        (routes / "money.ts").write_text("export const x = 1;")

        result = _bare_ts_server()._find_representative_source_file(str(tmp_path))

        assert result == str(routes / "money.ts")

    def test_falls_back_to_adjacent_file_when_no_src_dir_exists(self, tmp_path) -> None:
        """Projects with source files directly next to tsconfig.json (no src/ subdirectory)
        must keep working exactly as before.
        """
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "tsconfig.json").write_text("{}")
        (pkg / "index.ts").write_text("export const x = 1;")

        result = _bare_ts_server()._find_representative_source_file(str(tmp_path))

        assert result == str(pkg / "index.ts")

    def test_ignores_node_modules_under_src(self, tmp_path) -> None:
        """The src/ subtree walk must still respect is_ignored_dirname, or a vendored .ts file
        under src/node_modules could be selected instead of real project source.
        """
        pkg = tmp_path / "pkg"
        vendored = pkg / "src" / "node_modules" / "dep"
        real_src = pkg / "src" / "lib"
        vendored.mkdir(parents=True)
        real_src.mkdir(parents=True)
        (pkg / "tsconfig.json").write_text("{}")
        (pkg / "vitest.config.ts").write_text("export default {};")
        (vendored / "vendored.ts").write_text("export const y = 1;")
        (real_src / "app.ts").write_text("export const x = 1;")

        result = _bare_ts_server()._find_representative_source_file(str(tmp_path))

        assert result == str(real_src / "app.ts")

    def test_returns_none_when_nothing_matches(self, tmp_path) -> None:
        (tmp_path / "README.md").write_text("no typescript here")

        assert _bare_ts_server()._find_representative_source_file(str(tmp_path)) is None
