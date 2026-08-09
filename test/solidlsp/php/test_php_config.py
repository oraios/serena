"""Configuration plumbing for ``Intelephense``'s ``file_filter``.

Serena treats only ``.php`` / ``.phtml`` files as PHP sources by default, while Drupal projects
keep ordinary PHP in ``.module`` / ``.install`` / ``.inc`` / ``.theme`` / ``.profile`` /
``.engine`` files, which therefore stay invisible to ``find_symbol`` and friends.
``ls_specific_settings["php"]`` accepts a ``file_filter`` key with additional extensions,
mirroring the Perl mechanism from #1449 / #1642 (see #1710).

The unit tests cover the default source-file matcher. The configuration plumbing itself lives
inline in ``Intelephense.__init__`` (matcher sync) and ``_start_server`` (the
``intelephense.files.associations`` push) and is exercised end-to-end by the integration test
at the bottom, which starts a real Intelephense and is gated by the ``php`` marker like the
rest of the PHP suite.
"""

import pytest

from solidlsp.ls_config import FilenameMatcher, LanguageServerId
from solidlsp.ls_utils import SymbolUtils
from test.conftest import get_repo_path, start_ls_context


class TestPhpSourceFnMatcherDefaults:
    def test_phtml_matched_by_default_for_all_php_language_servers(self) -> None:
        # .phtml is a standard (yet outdated) PHP extension, so all PHP language servers treat it
        # as a PHP source by default (#1710).
        for language in (LanguageServerId.PHP, LanguageServerId.PHP_PHPACTOR, LanguageServerId.PHP_PHPANTOM):
            matcher = language.get_source_fn_matcher()
            assert matcher.is_relevant_filename("index.php"), f"{language}: .php not matched"
            assert matcher.is_relevant_filename("template.phtml"), f"{language}: .phtml not matched"

    def test_module_not_matched_by_default(self) -> None:
        # guard for the integration test below: .module files only become visible via file_filter
        assert not LanguageServerId.PHP.get_source_fn_matcher().is_relevant_filename("hooks.module")

    def test_file_extensions_property_returns_copy(self) -> None:
        # _create_base_initialize_params derives the files.associations globs from this property;
        # mutating the returned list must not affect the matcher.
        matcher = FilenameMatcher(".php", ".phtml")
        extensions = matcher.file_extensions
        extensions.append(".module")

        assert ".module" not in matcher.file_extensions
        assert not matcher.is_relevant_filename("hooks.module")


@pytest.mark.php
class TestFileFilterIntegration:
    """End-to-end check that a custom ``file_filter`` makes a Drupal-style file visible.

    Starts a real Intelephense, hence gated by the ``php`` marker. The ``drupal_module.module``
    fixture stays invisible to every test that runs with default settings.
    """

    def test_module_file_symbols_and_references_visible(self) -> None:
        with start_ls_context(
            LanguageServerId.PHP,
            ls_specific_settings={LanguageServerId.PHP: {"file_filter": [".module"]}},
        ) as ls:
            # Layer 2 (files.associations) must be asserted FIRST: the reference in the
            # never-opened drupal_module.module can only come from the server's association-driven
            # background index. request_full_symbol_tree below didOpens every matched file in the
            # LS, after which this assertion could pass even without the associations.
            helper_php_path = str(get_repo_path(LanguageServerId.PHP) / "helper.php")
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
