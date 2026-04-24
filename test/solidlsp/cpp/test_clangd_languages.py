import os

import pytest

from solidlsp.ls_config import Language
from test.conftest import start_ls_context


@pytest.mark.cpp
class TestClangdLanguages:
    @pytest.mark.parametrize(
        "lang, unit, names",
        [
            ("C", "a.c", {"main"}),
            ("CUDA", "a.cu", {"main", "cuda_hello"}),
            ("CXX20", "a.cpp", {"main"}),
            ("CXX20", "b.cpp", {"add", "add_f32"}),
            ("CXX20", "b.cppm", {"add", "add_f32", "add_u32"}),
            ("HIP", "a.hip", {"add_vectors"}),
            ("OpenCL", "a.cl", {"add_vectors"}),
            ("Objective-C", "a.m", {"main", "Hello", "-hello"}),
        ],
    )
    def test_get_document_symbols(self, lang: str, unit: str, names: set[str]) -> None:
        with start_ls_context(Language.CPP) as clangd:
            path = os.path.join(lang, unit)
            symbols = clangd.request_document_symbols(path).get_all_symbols_and_roots()
            symbols = symbols[0] if symbols and isinstance(symbols[0], list) else symbols
            symbols = {s.get("name") for s in symbols}
            assert names == symbols, f"Expected '{names}' in document symbols, got: {symbols}"
