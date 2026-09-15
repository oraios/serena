"""
Unit tests for the Angular warm-up seed search.

Deliberately **not** marked ``angular``: this is pure filesystem walking with no language
server started (the whole class runs in <0.1s), and these are the regressions most worth
catching in the default suite rather than behind the slow, node-dependent job.
"""


class TestAngularWarmUpSeedFile:
    """Unit tests for the warm-up seed search (``_find_representative_source_file``).

    Pure filesystem walking — no language server is started.
    """

    @staticmethod
    def _find(directory) -> str | None:
        from solidlsp.language_servers.angular_language_server import AngularLanguageServer

        # Bypass __init__ (which would install/launch the LS). Safe only because the walk reads no
        # instance state — just the class' own is_ignored_dirname and MAX_SEED_SEARCH_DIRS. Give it
        # instance state and this construction starts raising AttributeError instead.
        ls = object.__new__(AngularLanguageServer)
        return AngularLanguageServer._find_representative_source_file(ls, str(directory))

    @staticmethod
    def _write(path, content: str = "export const x = 1;\n") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def test_prefers_component_over_plain_ts(self, tmp_path) -> None:
        (tmp_path / "tsconfig.json").write_text("{}")
        self._write(tmp_path / "src" / "main.ts")
        self._write(tmp_path / "src" / "app" / "app.component.ts")
        assert self._find(tmp_path) == str(tmp_path / "src" / "app" / "app.component.ts")

    def test_falls_back_to_any_ts_file(self, tmp_path) -> None:
        (tmp_path / "tsconfig.json").write_text("{}")
        self._write(tmp_path / "src" / "main.ts")
        assert self._find(tmp_path) == str(tmp_path / "src" / "main.ts")

    def test_skips_declaration_and_spec_files(self, tmp_path) -> None:
        """``.d.ts`` carries no project, and specs are excluded from the app tsconfig."""
        (tmp_path / "tsconfig.json").write_text("{}")
        self._write(tmp_path / "src" / "types.d.ts")
        self._write(tmp_path / "src" / "app.component.spec.ts")
        assert self._find(tmp_path) is None

    def test_never_descends_into_node_modules(self, tmp_path) -> None:
        """A seed inside node_modules would resolve the dependency's project, not the app's."""
        (tmp_path / "tsconfig.json").write_text("{}")
        self._write(tmp_path / "node_modules" / "some-lib" / "lib.component.ts")
        assert self._find(tmp_path) is None

    def test_returns_none_without_tsconfig(self, tmp_path) -> None:
        """Regression: without a tsconfig.json ngserver never loads a project and never sends
        ``projectLoadingFinish``, so warming up would burn the full NG_SERVER_READY_TIMEOUT on
        every startup (measured 31s vs 1s) for nothing.
        """
        self._write(tmp_path / "src" / "app" / "app.component.ts")
        assert self._find(tmp_path) is None

    def test_finds_tsconfig_in_subproject(self, tmp_path) -> None:
        """Monorepo layout: the tsconfig.json lives in the sub-project, not at the walk root."""
        self._write(tmp_path / "projects" / "app" / "src" / "app.component.ts")
        (tmp_path / "projects" / "app" / "tsconfig.json").write_text("{}")
        assert self._find(tmp_path) == str(tmp_path / "projects" / "app" / "src" / "app.component.ts")

    def test_returns_none_for_empty_directory(self, tmp_path) -> None:
        assert self._find(tmp_path) is None

    def test_stops_scanning_once_a_fallback_is_in_hand(self, tmp_path, monkeypatch) -> None:
        """A tree with no ``.component.ts`` must not be walked to the end just to prove it.

        Without the budget the component preference can never be satisfied, so the walk runs over
        the whole (pruned) source tree of a monorepo on every startup.
        """
        from solidlsp.language_servers.angular_language_server import AngularLanguageServer

        (tmp_path / "tsconfig.json").write_text("{}")
        self._write(tmp_path / "a" / "main.ts")
        for i in range(5):
            self._write(tmp_path / "z" / f"pkg{i}" / "index.ts")

        monkeypatch.setattr(AngularLanguageServer, "MAX_SEED_SEARCH_DIRS", 1)
        assert self._find(tmp_path) == str(tmp_path / "a" / "main.ts")

    def test_seed_choice_is_stable_across_directory_orderings(self, tmp_path) -> None:
        """``os.walk`` lists subdirectories in filesystem order; sorting keeps the seed the same
        file on every machine rather than whichever sibling happened to be listed first.
        """
        (tmp_path / "tsconfig.json").write_text("{}")
        self._write(tmp_path / "zzz" / "late.ts")
        self._write(tmp_path / "aaa" / "early.ts")
        assert self._find(tmp_path) == str(tmp_path / "aaa" / "early.ts")
