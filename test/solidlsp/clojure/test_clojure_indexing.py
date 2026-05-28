"""Regression tests for clojure-lsp project-wide indexing.

Bug: ``find_referencing_symbols`` (and the underlying ``request_references``)
returns incomplete cross-file results unless the referencing files have already
been opened/indexed during the current session via ``find_symbol`` /
``get_symbols_overview``. The result is deterministically partial — it grows as
more files happen to get indexed by side-effect — which silently biases call
graphs towards files the user has already explored.

The tests here use a fresh module-scoped language server and probe a symbol
whose references live in a file (``extra.clj``) that no other test in this
module touches. The references must be returned even though no prior tool call
has caused the file to be opened in the LSP.
"""

from pathlib import Path

import pytest

from serena.util.text_utils import find_text_coordinates
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language
from test.conftest import language_tests_enabled
from test.solidlsp.conftest import read_repo_file

from . import CORE_PATH, TEST_APP_PATH

EXTRA_PATH = str(TEST_APP_PATH / "extra.clj")
SUBMODULE_CONSUMER_PATH = str(Path("sub_module") / "src" / "sub_module_app" / "consumer.clj")


@pytest.mark.skipif(not language_tests_enabled(Language.CLOJURE), reason="Clojure tests are disabled")
@pytest.mark.clojure
class TestClojureProjectIndexing:
    """Covers the "indexing leaks through results" bug for clojure-lsp.

    The fixture is module-scoped, so all tests within this class share a single
    server. We deliberately avoid any operation that would open ``extra.clj``
    (``get_symbols_overview``, ``find_symbol``, ``open_file``) before asserting
    on references — otherwise the bug would be masked by the side-effectful
    indexing of those calls.
    """

    @pytest.mark.parametrize("language_server", [Language.CLOJURE], indirect=True)
    def test_request_references_includes_unopened_file(self, language_server: SolidLanguageServer) -> None:
        # locate the definition of `multiply` in core.clj without hardcoding coords
        core_content = read_repo_file(language_server, CORE_PATH)
        coords = find_text_coordinates(core_content, r"\(defn (multiply)\b", require_unique=True)
        assert coords is not None, "Could not locate the 'multiply' definition in core.clj"

        # request references straight away — nothing has caused extra.clj to be opened in the LSP
        refs = language_server.request_references(CORE_PATH, coords.line, coords.col)
        ref_paths = {r.get("relativePath", "") for r in refs}

        # extra.clj contains two real call sites (in double-product and triple-product);
        # they must be returned regardless of whether the file was opened beforehand
        extra_refs = [r for r in refs if r.get("relativePath", "").endswith("extra.clj")]
        assert extra_refs, (
            "Expected references to 'multiply' to include call sites from extra.clj, "
            f"but got files: {sorted(ref_paths)}. "
            "This indicates clojure-lsp is only indexing files that have been opened "
            "during the session, so cross-file references are silently incomplete."
        )
        assert len(extra_refs) >= 2, (
            f"Expected at least 2 references in extra.clj (double-product and triple-product), got {len(extra_refs)}: {extra_refs}"
        )

    @pytest.mark.parametrize("language_server", [Language.CLOJURE], indirect=True)
    def test_request_references_includes_unopened_sibling_module_file(self, language_server: SolidLanguageServer) -> None:
        """Mirrors the real-world penpot bug repro: ``multiply`` is defined in one
        module (root ``src/``) and consumed from a sibling module that has its
        own ``deps.edn`` (``sub_module/``). With clojure-lsp running at the
        repository root, references to ``multiply`` must include the sibling
        module's call sites — even when no prior tool call has opened those
        files in the LSP.
        """
        core_content = read_repo_file(language_server, CORE_PATH)
        coords = find_text_coordinates(core_content, r"\(defn (multiply)\b", require_unique=True)
        assert coords is not None, "Could not locate the 'multiply' definition in core.clj"

        refs = language_server.request_references(CORE_PATH, coords.line, coords.col)
        ref_paths = {r.get("relativePath", "") for r in refs}

        consumer_refs = [
            r for r in refs if r.get("relativePath", "").replace("\\", "/").endswith("sub_module/src/sub_module_app/consumer.clj")
        ]
        assert consumer_refs, (
            "Expected references to 'multiply' to include call sites from the sibling module "
            "(sub_module/src/sub_module_app/consumer.clj), but got files: "
            f"{sorted(ref_paths)}. This mirrors the penpot bug: clojure-lsp does not appear to "
            "index files in sibling modules until they are explicitly opened via find_symbol / "
            "get_symbols_overview, so reference search returns silently incomplete results."
        )

    @pytest.mark.parametrize("language_server", [Language.CLOJURE], indirect=True)
    def test_request_referencing_symbols_includes_unopened_file(self, language_server: SolidLanguageServer) -> None:
        core_content = read_repo_file(language_server, CORE_PATH)
        coords = find_text_coordinates(core_content, r"\(defn (multiply)\b", require_unique=True)
        assert coords is not None, "Could not locate the 'multiply' definition in core.clj"

        # request_referencing_symbols is what the user-facing find_referencing_symbols tool calls into
        refs = language_server.request_referencing_symbols(CORE_PATH, coords.line, coords.col)

        referencing_names = {ref.symbol.get("name", "") for ref in refs if hasattr(ref, "symbol")}
        # double-product and triple-product live in extra.clj and both call multiply
        assert "double-product" in referencing_names or "triple-product" in referencing_names, (
            "Expected referencing symbols to include functions from extra.clj (double-product / triple-product), "
            f"but got: {sorted(referencing_names)}. "
            "extra.clj appears not to have been indexed by clojure-lsp because no prior tool call opened it."
        )
