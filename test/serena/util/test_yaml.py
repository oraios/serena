"""Tests for serena.util.yaml — focused on the atomic-write guarantee of ``save_yaml``.

Regression: ``~/.serena/serena_config.yml`` was corrupted in the field when a non-atomic
truncate-and-write saved a SHORTER value over a longer existing file (or two Serena processes
saved concurrently), leaving a stale tail (e.g. a dangling ``ena`` line) that made the YAML
unparsable, which wedged every later load. ``save_yaml`` now writes to a temp file and
``os.replace``s it onto the target, so each write is all-or-nothing.
"""

import os
import threading

from ruamel.yaml import YAML

from serena.util.yaml import load_yaml, save_yaml


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_save_yaml_roundtrips(tmp_path):
    path = str(tmp_path / "config.yml")
    save_yaml(path, {"projects": ["a", "b", "c"], "scalar": 1})
    loaded = load_yaml(path)
    assert list(loaded["projects"]) == ["a", "b", "c"]
    assert loaded["scalar"] == 1


def test_shorter_write_over_longer_leaves_no_stale_tail(tmp_path):
    """The exact field corruption: a long file overwritten by a much shorter one.

    A plain ``open(path, "w")`` truncates first, so this would pass even when buggy; the point
    of the assertion is that the final file parses and contains EXACTLY the new content — no
    leftover bytes from the longer previous version.
    """
    path = str(tmp_path / "config.yml")
    long_projects = [f"C:/Users/misch/Projects/some/really/long/path/number/{i}/serena" for i in range(50)]
    save_yaml(path, {"projects": long_projects})

    save_yaml(path, {"projects": ["C:/Users/misch/Projects/oraios/serena"]})

    loaded = load_yaml(path)
    assert list(loaded["projects"]) == ["C:/Users/misch/Projects/oraios/serena"]
    # no stale tail from the longer write survived
    assert "number/49" not in _read_text(path)
    # and it is still valid YAML on a fresh strict parse
    with open(path, encoding="utf-8") as f:
        YAML().load(f)


def test_no_tmp_files_left_behind(tmp_path):
    path = str(tmp_path / "config.yml")
    save_yaml(path, {"projects": ["a"]})
    leftovers = [p for p in os.listdir(tmp_path) if p != "config.yml"]
    assert leftovers == [], f"temp files not cleaned up: {leftovers}"


def test_concurrent_saves_never_corrupt(tmp_path):
    """Many concurrent writers must yield a file that always parses (last-writer-wins is fine;
    a corrupt interleave is not).
    """
    path = str(tmp_path / "config.yml")
    save_yaml(path, {"projects": ["seed"]})

    def writer(n: int) -> None:
        for _ in range(20):
            save_yaml(path, {"projects": [f"p{n}-{k}" for k in range(n + 1)]})

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # whatever won, the file must be complete + parseable (no corruption)
    loaded = load_yaml(path)
    assert "projects" in loaded
    assert all(isinstance(p, str) for p in loaded["projects"])
