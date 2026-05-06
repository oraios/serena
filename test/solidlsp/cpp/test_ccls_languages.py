import os

import pytest

from solidlsp.ls_config import Language
from test.conftest import start_ls_context


@pytest.mark.cpp
class TestCCLSLanguages:
    @pytest.mark.parametrize(
        "lang, unit, names",
        [
            ("C", "a.c", {"main"}),
            ("Objective-C", "a.m", {"main", "Hello", "-hello"}),
        ],
    )
    def test_get_document_symbols(self, lang: str, unit: str, names: set[str]) -> None:
        with start_ls_context(Language.CPP) as ccls:
            path = os.path.join(lang, unit)
            symbols = ccls.request_document_symbols(path).get_all_symbols_and_roots()
            symbols = symbols[0] if symbols and isinstance(symbols[0], list) else symbols
            symbols = {s.get("name") for s in symbols}
            assert names == symbols, f"Expected '{names}' in document symbols, got: {symbols}"
