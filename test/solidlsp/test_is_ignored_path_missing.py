"""Unit tests: missing-path handling in ``SolidLanguageServer``.

``is_ignored_path`` must not raise on missing paths, and symbol locations resolving to
non-existent files must be skipped. Language servers may report locations of generated
files that are not present on disk, e.g. JDTLS reporting a Lombok-generated
``LombokModel$LombokModelBuilder.class`` under ``target/classes``; the ignore check must
classify such paths instead of raising ``FileNotFoundError``.

No language markers: these use a local test double and run in catch-all.
"""

from __future__ import annotations

from pathlib import Path

import pathspec
import pytest

from solidlsp import SolidLanguageServer, ls_types
from solidlsp.ls_config import Language
from solidlsp.ls_utils import PathUtils


class _IgnoredPathServer(SolidLanguageServer):
    """Minimal test double exposing only :meth:`is_ignored_path` dependencies."""

    def __init__(
        self,
        root: Path,
        language: Language,
        *,
        ignored_dirnames: tuple[str, ...] = (),
        ignore_lines: tuple[str, ...] = (),
    ) -> None:
        self.repository_root_path = str(root)
        self.language = language
        self._ignored_dirnames = frozenset(ignored_dirnames)
        self._ignore_spec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, ignore_lines)

    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in self._ignored_dirnames

    def _start_server(self) -> None:
        raise AssertionError("The test double must not start a language server")

    def _create_base_initialize_params(self) -> dict[str, object]:
        raise AssertionError("The test double must not build initialize params")


def test_missing_lombok_class_under_target_is_ignored_not_raised(tmp_path: Path) -> None:
    """JDTLS-style missing build artifact under target/classes -- must be ignored, never raise."""
    ls = _IgnoredPathServer(tmp_path, Language.JAVA)
    missing = "target/classes/test_repo/LombokModel$LombokModelBuilder.class"

    assert not (tmp_path / missing).exists()
    assert ls.is_ignored_path(missing) is True


def test_missing_unsupported_extension_is_ignored(tmp_path: Path) -> None:
    ls = _IgnoredPathServer(tmp_path, Language.PYTHON)
    missing = "src/foo.pyc"
    assert not (tmp_path / missing).exists()
    assert ls.is_ignored_path(missing) is True


def test_missing_source_file_not_in_ignored_dir_is_not_ignored(tmp_path: Path) -> None:
    """A missing source path classifies as not-ignored."""
    ls = _IgnoredPathServer(tmp_path, Language.PYTHON)
    missing = "src/app.py"
    assert not (tmp_path / missing).exists()
    assert ls.is_ignored_path(missing) is False


def test_missing_source_file_under_ignored_dirname_is_ignored(tmp_path: Path) -> None:
    ls = _IgnoredPathServer(tmp_path, Language.PYTHON, ignored_dirnames=("generated",))
    missing = "generated/app.py"
    assert not (tmp_path / missing).exists()
    assert ls.is_ignored_path(missing) is True


def test_missing_directory_with_ignored_dirname_leaf_is_ignored(tmp_path: Path) -> None:
    """The leaf of a missing suffixless path may denote a directory and is checked against ignored dirnames."""
    ls = _IgnoredPathServer(tmp_path, Language.PYTHON, ignored_dirnames=("generated",))
    assert ls.is_ignored_path("generated", ignore_unsupported_files=False) is True
    assert ls.is_ignored_path("src/generated", ignore_unsupported_files=False) is True
    assert ls.is_ignored_path(".venv", ignore_unsupported_files=False) is True


def test_missing_extensionless_path_is_treated_as_directory(tmp_path: Path) -> None:
    """A missing suffixless path is not subject to the unsupported-extension rule for files."""
    ls = _IgnoredPathServer(tmp_path, Language.PYTHON)
    assert ls.is_ignored_path("newpkg") is False


def test_missing_ignored_by_pathspec_is_ignored(tmp_path: Path) -> None:
    ls = _IgnoredPathServer(tmp_path, Language.PYTHON, ignore_lines=("generated.py",))
    missing = "generated.py"
    assert not (tmp_path / missing).exists()
    assert ls.is_ignored_path(missing) is True


def test_missing_unsupported_extension_can_be_allowed(tmp_path: Path) -> None:
    ls = _IgnoredPathServer(tmp_path, Language.PYTHON)
    missing = "src/foo.pyc"
    assert not (tmp_path / missing).exists()
    assert ls.is_ignored_path(missing, ignore_unsupported_files=False) is False


def test_existing_path_under_ignored_dirname_is_ignored(tmp_path: Path) -> None:
    ls = _IgnoredPathServer(tmp_path, Language.PYTHON, ignored_dirnames=("generated",))
    source_file = tmp_path / "generated" / "app.py"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("x = 1\n")
    assert ls.is_ignored_path("generated/app.py") is True


def test_existing_source_file_is_not_ignored(tmp_path: Path) -> None:
    ls = _IgnoredPathServer(tmp_path, Language.PYTHON)
    src = tmp_path / "pkg" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text("x = 1\n")
    assert ls.is_ignored_path("pkg/mod.py") is False


@pytest.mark.parametrize(
    "rel",
    [
        "target/classes/test_repo/LombokModel$LombokModelBuilder.class",
        "build/classes/Foo.class",
        "out/production/Foo.class",
    ],
)
def test_java_build_output_paths_never_raise(tmp_path: Path, rel: str) -> None:
    """Compiled-class paths classify as ignored via the unsupported-extension rule, present or not
    (build dirnames are deliberately not hard-ignored for Java).
    """
    ls = _IgnoredPathServer(tmp_path, Language.JAVA)
    # neither present nor absent should raise
    assert ls.is_ignored_path(rel) is True
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    assert ls.is_ignored_path(rel) is True


class _StubSymbolLocationRequest(SolidLanguageServer.SymbolLocationRequest):
    """Minimal concrete subclass exposing only :meth:`convert_location_item` dependencies."""

    def send_request(self) -> object | None:
        raise AssertionError("The test double must not send LSP requests")

    def normalize_response(self, response: object | None) -> list[ls_types.Location]:
        raise AssertionError("The test double must not normalize LSP responses")


def _location_request(ls: SolidLanguageServer) -> SolidLanguageServer.SymbolLocationRequest:
    return _StubSymbolLocationRequest(ls, "src/app.py", 0, 0, request_name="test_request")


def _location_item(path: Path) -> dict:
    zero = {"line": 0, "character": 0}
    return {"uri": PathUtils.path_to_uri(str(path)), "range": {"start": zero, "end": zero}}


def test_location_at_missing_path_is_skipped(tmp_path: Path) -> None:
    """Locations whose absolute path is not on disk (e.g. LS-reported build artifacts) are dropped."""
    ls = _IgnoredPathServer(tmp_path, Language.JAVA)
    missing = tmp_path / "target" / "classes" / "LombokModel$LombokModelBuilder.class"
    assert not missing.exists()
    assert _location_request(ls).convert_location_item(_location_item(missing)) is None


def test_location_at_missing_source_path_is_skipped(tmp_path: Path) -> None:
    """A missing path that is not ignored is dropped by the existence check alone."""
    ls = _IgnoredPathServer(tmp_path, Language.PYTHON)
    assert ls.is_ignored_path("pkg/mod.py") is False
    assert _location_request(ls).convert_location_item(_location_item(tmp_path / "pkg" / "mod.py")) is None


def test_location_at_existing_ignored_path_is_skipped(tmp_path: Path) -> None:
    ls = _IgnoredPathServer(tmp_path, Language.PYTHON, ignored_dirnames=("generated",))
    source_file = tmp_path / "generated" / "app.py"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("x = 1\n")
    assert _location_request(ls).convert_location_item(_location_item(source_file)) is None


def test_location_at_existing_source_path_is_converted(tmp_path: Path) -> None:
    ls = _IgnoredPathServer(tmp_path, Language.PYTHON)
    source_file = tmp_path / "pkg" / "mod.py"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("x = 1\n")
    location = _location_request(ls).convert_location_item(_location_item(source_file))
    assert location is not None
    assert Path(location["absolutePath"]) == source_file
    assert Path(location["relativePath"]) == Path("pkg/mod.py")
