"""Configuration plumbing for ``Intelephense``'s ``file_filter``.

Serena treats only ``.php`` files as PHP sources by default, while Drupal projects keep ordinary
PHP in ``.module`` / ``.install`` / ``.inc`` / ``.theme`` / ``.profile`` / ``.engine`` files,
which therefore stay invisible to ``find_symbol`` and friends. ``ls_specific_settings["php"]``
now accepts a ``file_filter`` key mirroring the Perl mechanism from #1449 / #1642 (see #1710).

The unit tests pin the configuration plumbing without starting the language server, so they run
in every environment. They also cover the source-file matcher sync that keeps ``find_symbol``
consistent with the LS. The integration test at the bottom starts a real Intelephense and is
gated by the ``php`` marker like the rest of the PHP suite.
"""

from pathlib import Path

import pytest

from solidlsp.language_servers.intelephense import _DEFAULT_FILE_FILTER, Intelephense
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from solidlsp.settings import SolidLSPSettings
from test.conftest import get_repo_path, start_ls_context


def _settings(tmp_path: Path, ls_specific_settings: dict | None = None) -> SolidLSPSettings:
    """A SolidLSPSettings rooted under ``tmp_path`` with optional php overrides."""
    return SolidLSPSettings(
        solidlsp_dir=str(tmp_path / ".solidlsp"),
        ls_specific_settings=ls_specific_settings or {},
    )


class TestResolveFileFilter:
    def test_default_when_no_ls_specific_settings(self, tmp_path: Path) -> None:
        # Behaviour unchanged for projects that don't set ls_specific_settings at all.
        assert Intelephense._resolve_file_filter(_settings(tmp_path)) == _DEFAULT_FILE_FILTER

    def test_default_when_php_key_absent(self, tmp_path: Path) -> None:
        # ls_specific_settings configured for another language must not leak into PHP.
        settings = _settings(tmp_path, {Language.PYTHON: {"something": "unrelated"}})

        assert Intelephense._resolve_file_filter(settings) == _DEFAULT_FILE_FILTER

    def test_custom_file_filter_returned(self, tmp_path: Path) -> None:
        # #1710: a Drupal project must be able to surface .module / .install / ... files.
        custom = [".php", ".phtml", ".module", ".install", ".inc", ".theme", ".profile", ".engine"]
        settings = _settings(tmp_path, {Language.PHP: {"file_filter": custom}})

        assert Intelephense._resolve_file_filter(settings) == custom

    def test_default_list_is_not_mutated_across_calls(self, tmp_path: Path) -> None:
        # The resolver must copy the module-level default, otherwise one instance mutating its
        # returned list would corrupt every subsequently created default-configured instance.
        file_filter = Intelephense._resolve_file_filter(_settings(tmp_path))
        file_filter.append(".module")

        assert Intelephense._resolve_file_filter(_settings(tmp_path)) == _DEFAULT_FILE_FILTER
        assert ".module" not in _DEFAULT_FILE_FILTER


class TestResolveFilesAssociations:
    def test_default_filter_is_not_pushed(self) -> None:
        # Pushing globs derived from the default filter would replace Intelephense's built-in
        # associations ["*.php", "*.phtml"] and silently drop .phtml indexing, changing default
        # behavior; the push must stay gated off for default-configured sessions.
        assert Intelephense._resolve_files_associations(list(_DEFAULT_FILE_FILTER)) is None

    def test_explicitly_configured_default_is_not_pushed(self) -> None:
        assert Intelephense._resolve_files_associations([".php"]) is None

    def test_custom_filter_yields_globs(self) -> None:
        assert Intelephense._resolve_files_associations([".php", ".phtml", ".module"]) == [
            "*.php",
            "*.phtml",
            "*.module",
        ]


class TestSourceFnMatcherSync:
    def test_custom_file_filter_extends_php_matcher(self, tmp_path: Path) -> None:
        # #1710: find_symbol relies on Language.PHP.get_source_fn_matcher(); unless the configured
        # extensions are synced into it, symbols in .module / .install files stay invisible even
        # though the LS indexes them. get_source_fn_matcher() is a @cache singleton, so reset()
        # afterwards.
        matcher = Language.PHP.get_source_fn_matcher()
        try:
            assert not matcher.is_relevant_filename("hooks.module")  # guard: not matched by default

            file_filter = Intelephense._resolve_file_filter(
                _settings(tmp_path, {Language.PHP: {"file_filter": [".php", ".module", ".install"]}})
            )
            Intelephense._sync_source_fn_matcher(file_filter)

            assert matcher.is_relevant_filename("index.php")
            assert matcher.is_relevant_filename("hooks.module")
            assert matcher.is_relevant_filename("schema.install")
        finally:
            matcher.reset()

    def test_default_file_filter_leaves_matcher_unchanged(self, tmp_path: Path) -> None:
        # The default file_filter matches the existing PHP matcher extension, so syncing it must
        # be a no-op (no duplicate entries, no new matches).
        matcher = Language.PHP.get_source_fn_matcher()
        try:
            initial = list(matcher._file_extensions)
            Intelephense._sync_source_fn_matcher(Intelephense._resolve_file_filter(_settings(tmp_path)))

            assert sorted(matcher._file_extensions) == sorted(initial)
        finally:
            matcher.reset()

    def test_other_php_backends_unaffected(self, tmp_path: Path) -> None:
        # Only Language.PHP (Intelephense) is wired; the phpactor / phpantom matchers are separate
        # @cache singletons and must not pick up Intelephense's configuration.
        matcher = Language.PHP.get_source_fn_matcher()
        phpactor_matcher = Language.PHP_PHPACTOR.get_source_fn_matcher()
        phpantom_matcher = Language.PHP_PHPANTOM.get_source_fn_matcher()
        try:
            Intelephense._sync_source_fn_matcher([".php", ".module"])

            assert matcher.is_relevant_filename("hooks.module")
            assert not phpactor_matcher.is_relevant_filename("hooks.module")
            assert not phpantom_matcher.is_relevant_filename("hooks.module")
        finally:
            matcher.reset()

    def test_reset_prevents_cross_project_leak(self, tmp_path: Path) -> None:
        # The matcher is a per-language singleton shared across projects. Project A reconfigures
        # file_filter (adds .module); when project B is activated, SolidLanguageServer.__init__
        # resets the matcher first, so project B must NOT see .module even though project A added
        # it. Mirrors the reset-then-sync ordering of Intelephense.__init__.
        matcher = Language.PHP.get_source_fn_matcher()
        try:
            # project A: custom file_filter with .module
            filter_a = Intelephense._resolve_file_filter(_settings(tmp_path, {Language.PHP: {"file_filter": [".php", ".module"]}}))
            Intelephense._sync_source_fn_matcher(filter_a)
            assert matcher.is_relevant_filename("hooks.module")

            # project B activates: base __init__ resets, then default config is applied (no .module)
            matcher.reset()
            filter_b = Intelephense._resolve_file_filter(_settings(tmp_path / "proj_b"))
            Intelephense._sync_source_fn_matcher(filter_b)

            assert not matcher.is_relevant_filename("hooks.module"), (
                "project B inherited project A's .module - reset did not undo the reconfiguration"
            )
            assert matcher.is_relevant_filename("index.php")
        finally:
            matcher.reset()


@pytest.mark.php
class TestFileFilterIntegration:
    """End-to-end check that a custom ``file_filter`` makes a Drupal-style file visible.

    Starts a real Intelephense, hence gated by the ``php`` marker. The ``drupal_module.module``
    fixture stays invisible to every test that runs with default settings.
    """

    def test_module_file_symbols_and_references_visible(self) -> None:
        with start_ls_context(
            Language.PHP,
            ls_specific_settings={Language.PHP: {"file_filter": [".php", ".module"]}},
        ) as ls:
            # Layer 2 (files.associations push) must be asserted FIRST: the reference in the
            # never-opened drupal_module.module can only come from the server's association-driven
            # background index. request_full_symbol_tree below didOpens every matched file in the
            # LS, after which this assertion could pass even without the push.
            helper_php_path = str(get_repo_path(Language.PHP) / "helper.php")
            references = ls.request_references(helper_php_path, 2, len("function "))
            assert any(ref["uri"].endswith("drupal_module.module") for ref in references), (
                f"helperFunction call in drupal_module.module not found in references: {references}"
            )

            # Layer 1 (Serena's source matcher): the .module file takes part in symbol traversal.
            symbols = ls.request_full_symbol_tree()
            assert SymbolUtils.symbol_tree_contains_name(symbols, "drupal_module_help"), (
                "drupal_module_help from drupal_module.module not found in the symbol tree"
            )
            assert SymbolUtils.symbol_tree_contains_name(symbols, "DrupalModuleController"), (
                "DrupalModuleController from drupal_module.module not found in the symbol tree"
            )
