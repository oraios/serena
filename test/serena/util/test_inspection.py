"""Unit tests for :func:`serena.util.inspection.determine_programming_language_composition`."""

from pathlib import Path

from serena.util.inspection import determine_programming_language_composition
from solidlsp.ls_config import Language


def _touch(directory: Path, *names: str) -> None:
    for name in names:
        (directory / name).write_text("content", encoding="utf-8")


class TestDetermineProgrammingLanguageComposition:
    def test_single_language_repo(self, tmp_path: Path) -> None:
        _touch(tmp_path, "a.py", "b.py", "c.py")
        composition = determine_programming_language_composition(str(tmp_path))
        assert composition[Language.PYTHON] == 100.0

    def test_unrecognised_files_do_not_dilute_percentages(self, tmp_path: Path) -> None:
        # 2 source files vs many files that belong to no supported language
        _touch(tmp_path, "main.py", "util.py")
        _touch(tmp_path, *[f"note_{i}.txt" for i in range(20)])
        _touch(tmp_path, "logo.png", "LICENSE", "data.csv")

        composition = determine_programming_language_composition(str(tmp_path))

        # previously: 2 / 25 files = 8% — now the denominator is recognised source files only
        assert composition[Language.PYTHON] == 100.0

    def test_mixed_language_percentages_relative_to_recognised_files(self, tmp_path: Path) -> None:
        _touch(tmp_path, "a.py", "b.py", "c.py", "d.go")
        _touch(tmp_path, *[f"asset_{i}.dat" for i in range(50)])

        composition = determine_programming_language_composition(str(tmp_path))

        assert composition[Language.PYTHON] == 75.0
        assert composition[Language.GO] == 25.0

    def test_repo_without_recognised_files(self, tmp_path: Path) -> None:
        _touch(tmp_path, "readme.txt", "logo.png")
        assert determine_programming_language_composition(str(tmp_path)) == {}

    def test_empty_repo(self, tmp_path: Path) -> None:
        assert determine_programming_language_composition(str(tmp_path)) == {}
