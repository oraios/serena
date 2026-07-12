"""Configuration plumbing for ``PerlLanguageServer``'s fileFilter / ignoreDirs.

``Perl::LanguageServer`` only indexes files whose extension is in ``perl.fileFilter`` and skips
directories listed in ``perl.ignoreDirs``; both are pushed to the LS at startup (see
``_start_server``). The defaults must stay backward-compatible, but projects with non-standard
layouts — e.g. ``.cgi`` / ``.psgi`` Perl web handlers that can dominate a mature codebase — need
a way to extend visibility (#1449).

These tests pin the configuration plumbing without starting the language server (which would
require a Perl runtime), so they run in every environment. They also cover the source-file matcher
sync that keeps ``find_symbol`` consistent with the LS (#1449).
"""

from pathlib import Path

from solidlsp.language_servers.perl_language_server import (
    _DEFAULT_FILE_FILTER,
    _DEFAULT_IGNORE_DIRS,
    PerlLanguageServer,
)
from solidlsp.ls_config import FilenameMatcher, Language
from solidlsp.settings import SolidLSPSettings


def _settings(tmp_path: Path, ls_specific_settings: dict | None = None) -> SolidLSPSettings:
    """A SolidLSPSettings rooted under ``tmp_path`` with optional perl overrides."""
    return SolidLSPSettings(
        solidlsp_dir=str(tmp_path / ".solidlsp"),
        ls_specific_settings=ls_specific_settings or {},
    )


class TestResolveFilterSettings:
    def test_defaults_when_no_ls_specific_settings(self, tmp_path: Path) -> None:
        # Behaviour unchanged for projects that don't set ls_specific_settings at all.
        file_filter, ignore_dirs = PerlLanguageServer._resolve_filter_settings(_settings(tmp_path))

        assert file_filter == _DEFAULT_FILE_FILTER
        assert ignore_dirs == _DEFAULT_IGNORE_DIRS

    def test_defaults_when_perl_key_absent(self, tmp_path: Path) -> None:
        # ls_specific_settings configured for another language must not leak into Perl.
        settings = _settings(tmp_path, {Language.PYTHON: {"something": "unrelated"}})

        file_filter, ignore_dirs = PerlLanguageServer._resolve_filter_settings(settings)

        assert file_filter == _DEFAULT_FILE_FILTER
        assert ignore_dirs == _DEFAULT_IGNORE_DIRS

    def test_custom_file_filter_makes_extra_extensions_visible(self, tmp_path: Path) -> None:
        # #1449: a Perl web backend must be able to surface .cgi / .psgi handlers.
        custom = [".pm", ".pl", ".t", ".cgi", ".psgi"]
        settings = _settings(tmp_path, {Language.PERL: {"file_filter": custom}})

        file_filter, _ = PerlLanguageServer._resolve_filter_settings(settings)

        assert file_filter == custom
        assert ".cgi" in file_filter

    def test_custom_ignore_dirs(self, tmp_path: Path) -> None:
        custom = [".git", "blib", "local", "cover_db", "t"]
        settings = _settings(tmp_path, {Language.PERL: {"ignore_dirs": custom}})

        _, ignore_dirs = PerlLanguageServer._resolve_filter_settings(settings)

        assert ignore_dirs == custom

    def test_both_overrides_apply_independently(self, tmp_path: Path) -> None:
        file_filter = [".pm", ".pl", ".cgi"]
        ignore_dirs = [".git", "vendor"]
        settings = _settings(
            tmp_path,
            {Language.PERL: {"file_filter": file_filter, "ignore_dirs": ignore_dirs}},
        )

        resolved_filter, resolved_dirs = PerlLanguageServer._resolve_filter_settings(settings)

        assert resolved_filter == file_filter
        assert resolved_dirs == ignore_dirs

    def test_default_lists_are_not_mutated_across_instances(self, tmp_path: Path) -> None:
        # The resolver must copy the module-level defaults, otherwise one instance mutating its
        # returned list (or the LS handlers appending to self._file_filter) would corrupt every
        # subsequently created default-configured instance.
        file_filter, _ = PerlLanguageServer._resolve_filter_settings(_settings(tmp_path))
        file_filter.append(".cgi")

        next_filter, _ = PerlLanguageServer._resolve_filter_settings(_settings(tmp_path))

        assert next_filter == _DEFAULT_FILE_FILTER
        assert ".cgi" not in _DEFAULT_FILE_FILTER


class TestFilenameMatcherAddExtensions:
    def test_adds_new_extension(self) -> None:
        matcher = FilenameMatcher(".pm", ".pl")

        matcher.add_extensions(".cgi")

        assert matcher.is_relevant_filename("lib/Foo.pm")
        assert matcher.is_relevant_filename("web/handler.cgi")

    def test_is_idempotent(self) -> None:
        # Re-adding an existing extension must not duplicate it; calling sync twice (e.g. across
        # two PerlLanguageServer instances) must be a no-op.
        matcher = FilenameMatcher(".pm", ".pl")
        baseline = len(matcher._file_extensions)

        matcher.add_extensions(".pm", ".pl")
        matcher.add_extensions(".cgi")
        matcher.add_extensions(".cgi")

        assert len(matcher._file_extensions) == baseline + 1
        assert matcher.is_relevant_filename("foo.cgi")

    def test_respects_case_insensitivity(self) -> None:
        matcher = FilenameMatcher(".pm", case_sensitive=False)

        matcher.add_extensions(".CGI")

        # case-insensitive matcher normalises to lower case
        assert matcher.is_relevant_filename("Handler.Cgi")
        assert ".cgi" in matcher._file_extensions
        assert ".CGI" not in matcher._file_extensions


class TestFilenameMatcherReset:
    def test_reset_undoes_added_extensions(self) -> None:
        matcher = FilenameMatcher(".pm", ".pl")

        matcher.add_extensions(".cgi", ".psgi")
        assert matcher.is_relevant_filename("h.cgi")

        matcher.reset()

        assert not matcher.is_relevant_filename("h.cgi")
        assert not matcher.is_relevant_filename("h.psgi")
        assert matcher.is_relevant_filename("h.pm")

    def test_reset_restores_original_after_case_insensitive_add(self) -> None:
        matcher = FilenameMatcher(".PM", case_sensitive=False)

        matcher.add_extensions(".cgi")
        matcher.reset()

        # original extension survives the round-trip (normalised to lower case at construction)
        assert matcher._file_extensions == [".pm"]
        assert not matcher.is_relevant_filename("h.cgi")

    def test_reset_is_idempotent(self) -> None:
        # SolidLanguageServer.__init__ calls reset on every activation; repeated resets must be safe
        # and must not shrink below the original configuration.
        matcher = FilenameMatcher(".pm", ".pl")
        baseline = len(matcher._file_extensions)

        matcher.add_extensions(".cgi")
        matcher.reset()
        matcher.reset()

        assert len(matcher._file_extensions) == baseline


class TestSourceFnMatcherSync:
    def test_custom_file_filter_extends_perl_matcher(self, tmp_path: Path) -> None:
        # #1449: find_symbol relies on Language.PERL.get_source_fn_matcher(); unless the configured
        # extensions are synced into it, symbols in .cgi/.psgi files stay invisible even though the
        # LS indexes them. get_source_fn_matcher() is a @cache singleton, so reset() afterwards.
        matcher = Language.PERL.get_source_fn_matcher()
        try:
            assert not matcher.is_relevant_filename("handler.cgi")  # guard: not matched by default

            file_filter, _ = PerlLanguageServer._resolve_filter_settings(
                _settings(tmp_path, {Language.PERL: {"file_filter": [".pm", ".pl", ".t", ".cgi", ".psgi"]}})
            )
            PerlLanguageServer._sync_source_fn_matcher(file_filter)

            assert matcher.is_relevant_filename("lib/Foo.pm")
            assert matcher.is_relevant_filename("web/handler.cgi")
            assert matcher.is_relevant_filename("app.psgi")
        finally:
            matcher.reset()

    def test_default_file_filter_leaves_matcher_unchanged(self, tmp_path: Path) -> None:
        # The default file_filter matches the existing Perl matcher extensions, so syncing it must
        # be a no-op (no duplicate entries, no new matches).
        matcher = Language.PERL.get_source_fn_matcher()
        try:
            initial = list(matcher._file_extensions)
            file_filter, _ = PerlLanguageServer._resolve_filter_settings(_settings(tmp_path))
            PerlLanguageServer._sync_source_fn_matcher(file_filter)

            assert sorted(matcher._file_extensions) == sorted(initial)
        finally:
            matcher.reset()

    def test_reset_prevents_cross_project_leak(self, tmp_path: Path) -> None:
        # The matcher is a per-language singleton shared across projects. Project A reconfigures
        # file_filter (adds .cgi); when project B is activated, SolidLanguageServer.__init__ resets
        # the matcher first, so project B must NOT see .cgi even though project A added it.
        # Mirrors the reset-then-sync ordering of PerlLanguageServer.__init__.
        matcher = Language.PERL.get_source_fn_matcher()
        try:
            # project A: custom file_filter with .cgi
            filter_a, _ = PerlLanguageServer._resolve_filter_settings(
                _settings(tmp_path, {Language.PERL: {"file_filter": [".pm", ".pl", ".t", ".cgi"]}})
            )
            PerlLanguageServer._sync_source_fn_matcher(filter_a)
            assert matcher.is_relevant_filename("handler.cgi")

            # project B activates: base __init__ resets, then default config is applied (no .cgi)
            matcher.reset()
            filter_b, _ = PerlLanguageServer._resolve_filter_settings(_settings(tmp_path / "proj_b"))
            PerlLanguageServer._sync_source_fn_matcher(filter_b)

            assert not matcher.is_relevant_filename("handler.cgi"), (
                "project B inherited project A's .cgi — reset did not undo the reconfiguration"
            )
            assert matcher.is_relevant_filename("lib/Foo.pm")
        finally:
            matcher.reset()
