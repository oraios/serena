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

from serena.util.yaml import YamlCommentNormalisation, load_yaml, save_yaml, transfer_yaml_comments


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


# The comment block that the template documents for ``ignored_paths``; in a user's config it ends up
# following the nested ``ls_specific_settings`` mapping, which is where ruamel attaches it.
_IGNORED_PATHS_COMMENT = "# list of paths to ignore across all projects."

_TEMPLATE = f"""\
ls_specific_settings: {{}}

{_IGNORED_PATHS_COMMENT}
# Same syntax as gitignore, so you can use * and **.
ignored_paths: []

# whether to log verbosely
log_level: 20
"""

_USER_CONFIG = f"""\
ls_specific_settings:
  java:
    use_system_java_home: true

{_IGNORED_PATHS_COMMENT}
# Same syntax as gitignore, so you can use * and **.
ignored_paths: []

# whether to log verbosely
log_level: 20
"""


def _save_like_serena_config_does(path: str, template_path: str) -> None:
    """One save cycle of the global configuration: load, take the template's comments, write back."""
    config = load_yaml(path, comment_normalisation=YamlCommentNormalisation.LEADING_WITH_CONVERSION_FROM_TRAILING)
    template = load_yaml(template_path, comment_normalisation=YamlCommentNormalisation.LEADING)
    transfer_yaml_comments(template, config, YamlCommentNormalisation.LEADING, force_update_all=True)
    save_yaml(path, config)


def test_comment_after_nested_mapping_is_not_duplicated_on_save(tmp_path):
    """A comment block following a nested mapping must not be duplicated by each save.

    Regression: ruamel attaches such a block to the *last entry of the nested mapping*, at any
    depth. The normalisation only ever inspects top-level keys, so the block survived untouched,
    was written back out, and was then joined by the copy that the caller transfers onto the
    top-level key the block actually documents. Every save added one more copy: a config in the
    field had accumulated thirty of them, growing by one per project registration.
    """
    template_path = str(tmp_path / "template.yml")
    config_path = str(tmp_path / "config.yml")
    with open(template_path, "w", encoding="utf-8") as f:
        f.write(_TEMPLATE)
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(_USER_CONFIG)

    _save_like_serena_config_does(config_path, template_path)
    assert _read_text(config_path).count(_IGNORED_PATHS_COMMENT) == 1

    # and it stays at one, however many times the configuration is saved
    for _ in range(3):
        _save_like_serena_config_does(config_path, template_path)
    assert _read_text(config_path).count(_IGNORED_PATHS_COMMENT) == 1

    # the settings themselves are untouched
    loaded = load_yaml(config_path)
    assert loaded["ls_specific_settings"]["java"]["use_system_java_home"] is True
    assert loaded["log_level"] == 20


def test_saving_is_idempotent_for_a_config_with_nested_mappings(tmp_path):
    """Two consecutive saves produce byte-identical files: nothing accumulates."""
    template_path = str(tmp_path / "template.yml")
    config_path = str(tmp_path / "config.yml")
    with open(template_path, "w", encoding="utf-8") as f:
        f.write(_TEMPLATE)
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(_USER_CONFIG)

    _save_like_serena_config_does(config_path, template_path)
    once = _read_text(config_path)
    _save_like_serena_config_does(config_path, template_path)
    assert _read_text(config_path) == once
