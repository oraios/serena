"""
`FilenameMatcher` routes an extensionless script to a language by its shebang line.
"""

import os
from pathlib import Path

import pytest

from solidlsp.ls_config import FilenameMatcher, LanguageServerId


def _script(tmp_path: Path, name: str, first_line: str) -> str:
    path = tmp_path / name
    path.write_text(first_line + "\nprint('hi')\n", encoding="utf-8")
    return str(path)


@pytest.mark.parametrize(
    "first_line",
    [
        "#!/usr/bin/env python3",
        "#!/usr/bin/env python",
        "#!/usr/bin/python3.12",
        "#!/usr/bin/env -S python3 -u",
        "#!/usr/bin/env PYTHONUNBUFFERED=1 python3",
    ],
)
def test_python_shebangs_match_the_python_matcher(tmp_path: Path, first_line: str) -> None:
    matcher = FilenameMatcher(".py", shebang_interpreters=("python",))
    assert matcher.is_relevant_filename(_script(tmp_path, "check-things", first_line))


@pytest.mark.parametrize("first_line", ["#!/bin/bash", "#!/usr/bin/env bash", "#!/bin/sh -e"])
def test_shell_shebangs_match_the_bash_matcher(tmp_path: Path, first_line: str) -> None:
    matcher = FilenameMatcher(".sh", shebang_interpreters=("bash", "sh"))
    assert matcher.is_relevant_filename(_script(tmp_path, "dev", first_line))


def test_a_foreign_interpreter_does_not_match(tmp_path: Path) -> None:
    matcher = FilenameMatcher(".py", shebang_interpreters=("python",))
    assert not matcher.is_relevant_filename(_script(tmp_path, "dev", "#!/bin/bash"))


def test_the_extension_decides_when_there_is_one(tmp_path: Path) -> None:
    matcher = FilenameMatcher(".py", shebang_interpreters=("python",))
    assert not matcher.is_relevant_filename(_script(tmp_path, "notes.txt", "#!/usr/bin/env python3"))
    assert matcher.is_relevant_filename(_script(tmp_path, "plain.py", "#!/bin/bash"))


def test_no_shebang_no_match(tmp_path: Path) -> None:
    matcher = FilenameMatcher(".py", shebang_interpreters=("python",))
    assert not matcher.is_relevant_filename(_script(tmp_path, "README", "Just prose."))
    (tmp_path / "empty").write_bytes(b"")
    assert not matcher.is_relevant_filename(str(tmp_path / "empty"))


def test_a_bare_filename_or_a_directory_is_never_sniffed(tmp_path: Path) -> None:
    matcher = FilenameMatcher(".py", shebang_interpreters=("python",))
    assert not matcher.is_relevant_filename("check-things")
    (tmp_path / "bin").mkdir()
    assert not matcher.is_relevant_filename(str(tmp_path / "bin"))


def test_a_matcher_without_interpreters_never_reads_files(tmp_path: Path) -> None:
    matcher = FilenameMatcher(".java")
    assert not matcher.is_relevant_filename(_script(tmp_path, "run", "#!/usr/bin/env python3"))


def test_the_verdict_follows_the_file_when_it_changes(tmp_path: Path) -> None:
    matcher = FilenameMatcher(".py", shebang_interpreters=("python",))
    path = _script(tmp_path, "tool", "#!/usr/bin/env python3")
    assert matcher.is_relevant_filename(path)
    Path(path).write_text("#!/bin/bash\necho\n", encoding="utf-8")
    os.utime(path, (1, 1))  # a different mtime: the cached verdict must not be reused
    assert not matcher.is_relevant_filename(path)


def test_python_and_bash_languages_declare_their_interpreters(tmp_path: Path) -> None:
    assert LanguageServerId.PYTHON.get_source_fn_matcher().is_relevant_filename(_script(tmp_path, "check", "#!/usr/bin/env python3"))
    assert LanguageServerId.BASH.get_source_fn_matcher().is_relevant_filename(_script(tmp_path, "dev", "#!/usr/bin/env bash"))
    assert not LanguageServerId.PYTHON.get_source_fn_matcher().is_relevant_filename(_script(tmp_path, "dev2", "#!/usr/bin/env bash"))
