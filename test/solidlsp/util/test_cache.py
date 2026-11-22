# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest

from solidlsp.util.cache import load_cache, save_cache


class _SaveInterruptedError(Exception):
    pass


class _InterruptsSave:
    def __reduce__(self) -> tuple:
        raise _SaveInterruptedError


def test_save_replaces_the_previous_cache(tmp_path: Path) -> None:
    cache_file = str(tmp_path / "cache.pkl")

    save_cache(cache_file, 1, {"a": 1})
    save_cache(cache_file, 1, {"b": 2})

    assert load_cache(cache_file, 1) == {"b": 2}


def test_interrupted_save_keeps_the_previous_cache_loadable(tmp_path: Path) -> None:
    cache_file = str(tmp_path / "cache.pkl")
    save_cache(cache_file, 1, {"a": 1})

    with pytest.raises(_SaveInterruptedError):
        save_cache(cache_file, 1, {"b": _InterruptsSave()})

    assert load_cache(cache_file, 1) == {"a": 1}


def test_save_creates_a_missing_cache_directory(tmp_path: Path) -> None:
    cache_file = str(tmp_path / "new" / "cache.pkl")

    save_cache(cache_file, 1, {"a": 1})

    assert load_cache(cache_file, 1) == {"a": 1}
