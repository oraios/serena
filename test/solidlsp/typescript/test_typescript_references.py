# SPDX-License-Identifier: MIT

"""Tests for TypeScript references through imports, barrel re-exports and implementing members."""

from pathlib import Path

import pytest

from solidlsp.ls_config import LanguageServerId
from test.conftest import TYPESCRIPT_LANGUAGE_BACKENDS, find_identifier_position, start_ls_context

REPO_PATH = Path(__file__).parent.parent.parent / "resources" / "repos" / "typescript" / "references_barrel"

# queried symbol -> (file, identifier at the declaration, expected references as (file, 0-based line))
EXPECTED_REFERENCES = {
    "settings": ("src/types.ts", "settings", {("src/app.ts", 0), ("src/app.ts", 5), ("src/index.ts", 1)}),
    "Item": ("src/types.ts", "Item", {("src/app.ts", 1), ("src/app.ts", 4), ("src/index.ts", 2)}),
    "Polite": ("src/polite.ts", "Polite", {("src/app.ts", 2), ("src/app.ts", 6), ("src/index.ts", 0)}),
    "retired": ("src/types.ts", "retired", {("src/index.ts", 3)}),
    "Greeter.greet": ("src/types.ts", "greet", {("src/app.ts", 6), ("src/polite.ts", 3)}),
}


@pytest.mark.typescript
class TestTypeScriptReferences:
    @pytest.mark.parametrize("ls_id", TYPESCRIPT_LANGUAGE_BACKENDS)
    def test_references_include_imports_reexports_and_implementations(self, ls_id: LanguageServerId) -> None:
        """
        References must include import and ``import type`` lines, barrel re-exports and implementing members,
        but not the declaration of the queried symbol itself.
        """
        with start_ls_context(ls_id, repo_path=str(REPO_PATH)) as ls:
            actual = {}
            for name, (file_path, identifier, _) in EXPECTED_REFERENCES.items():
                position = find_identifier_position(REPO_PATH / file_path, identifier)
                assert position is not None, f"Could not find '{identifier}' in {file_path}"
                refs = ls.request_references(file_path, *position)
                actual[name] = {(Path(ref["relativePath"]).as_posix(), ref["range"]["start"]["line"]) for ref in refs}

        assert actual == {name: expected for name, (_, _, expected) in EXPECTED_REFERENCES.items()}

    @pytest.mark.parametrize("ls_id", TYPESCRIPT_LANGUAGE_BACKENDS)
    def test_referencing_symbols_include_imports_reexports_and_implementations(self, ls_id: LanguageServerId) -> None:
        """
        Referencing symbols, requested with the arguments of ``find_referencing_symbols``, must be found at the same
        locations as the references.
        """
        with start_ls_context(ls_id, repo_path=str(REPO_PATH)) as ls:
            actual = {}
            for name, (file_path, identifier, _) in EXPECTED_REFERENCES.items():
                position = find_identifier_position(REPO_PATH / file_path, identifier)
                assert position is not None, f"Could not find '{identifier}' in {file_path}"
                refs = ls.request_referencing_symbols(
                    file_path, *position, include_imports=False, include_self=False, include_file_symbols=True
                )
                actual[name] = {(Path(ref.symbol["location"]["relativePath"]).as_posix(), ref.line) for ref in refs}

        assert actual == {name: expected for name, (_, _, expected) in EXPECTED_REFERENCES.items()}
