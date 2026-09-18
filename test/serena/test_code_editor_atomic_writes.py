"""Tests that saving an edited source file cannot destroy the previous content (issue #1958).

``CodeEditor._save_edited_file`` is the third of the three direct ``open(path, "w")`` writes the
issue lists; the two in ``MemoryManager`` were addressed in #1969, which is also where
``write_file_atomic`` comes from.

The editor is exercised through a stub subclass so that the inherited save path can be driven
without a language server.
"""

import os
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from serena.code_editor import CodeEditor
from serena.util import file_system
from serena.util.file_system import write_file_atomic


class _InMemoryEditedFile(CodeEditor.EditedFile):
    """An ``EditedFile`` that holds its contents in memory."""

    def __init__(self, relative_path: str, contents: str) -> None:
        super().__init__(relative_path)
        self._contents = contents

    def get_contents(self) -> str:
        return self._contents

    def set_contents(self, contents: str) -> None:
        self._contents = contents

    def delete_text_between_positions(self, start_pos: Any, end_pos: Any) -> None:
        raise NotImplementedError

    def insert_text_at_position(self, pos: Any, text: str) -> None:
        raise NotImplementedError


class _StubCodeEditor(CodeEditor[Any]):
    """A ``CodeEditor`` whose only inherited behaviour under test is the file-saving path."""

    def __init__(self, project_root: str, encoding: str = "utf-8", newline: str | None = None) -> None:
        self.project_root = project_root
        self.encoding = encoding
        self.newline = newline

    @contextmanager
    def _open_file_context(self, relative_path: str) -> Iterator[CodeEditor.EditedFile]:
        abs_path = os.path.join(self.project_root, relative_path)
        with open(abs_path, encoding=self.encoding) as f:
            contents = f.read()
        yield _InMemoryEditedFile(relative_path, contents)

    def _find_unique_symbol(self, name_path: str, relative_file_path: str) -> Any:
        raise NotImplementedError

    def rename_symbol(self, name_path: str, relative_path: str, new_name: str) -> str:
        raise NotImplementedError


class TestSourceFileSaveIsAtomic:
    def _editor(self, tmp_path: Any, **kwargs: Any) -> _StubCodeEditor:
        return _StubCodeEditor(str(tmp_path), **kwargs)

    def test_interrupted_save_keeps_the_previous_file_content(self, tmp_path, monkeypatch):
        """A crash partway through the write must leave the file holding its old content.

        The crash is injected into the temp-file write that ``write_file_atomic`` performs, so on
        a non-atomic implementation nothing raises at all and this fails with ``DID NOT RAISE``,
        which is exactly the state the issue describes: the real file is truncated first and there
        is no intermediate copy to fall back to.
        """
        source = tmp_path / "module.py"
        original = "def original():\n    return 1\n" * 40
        source.write_text(original, encoding="utf-8")

        real_fdopen = os.fdopen

        def crashing_fdopen(fd: int, *args: Any, **kwargs: Any) -> Any:
            f = real_fdopen(fd, *args, **kwargs)
            real_write = f.write

            def crashing_write(data: str) -> int:
                real_write(data[: len(data) // 4])
                f.flush()
                raise RuntimeError("simulated crash mid-write")

            f.write = crashing_write
            return f

        monkeypatch.setattr(file_system.os, "fdopen", crashing_fdopen)

        editor = self._editor(tmp_path)
        with pytest.raises(RuntimeError, match="simulated crash mid-write"):
            with editor.edited_file_context("module.py") as edited:
                edited.set_contents("def replacement():\n    return 2\n" * 40)

        assert source.read_text(encoding="utf-8") == original
        assert list(tmp_path.iterdir()) == [source], "the partial temp file must not be left behind"

    def test_successful_save_writes_the_new_content(self, tmp_path):
        """Control: the ordinary path still writes what was asked for."""
        source = tmp_path / "module.py"
        source.write_text("old\n", encoding="utf-8")

        editor = self._editor(tmp_path)
        with editor.edited_file_context("module.py") as edited:
            edited.set_contents("new\n")

        assert source.read_text(encoding="utf-8") == "new\n"
        assert list(tmp_path.iterdir()) == [source]

    def test_save_into_a_subdirectory(self, tmp_path):
        """Every other test writes at the project root; the relative path is joined and resolved,
        so a nested file has to work the same way.
        """
        package = tmp_path / "pkg" / "sub"
        package.mkdir(parents=True)
        source = package / "module.py"
        source.write_text("old\n", encoding="utf-8")

        editor = self._editor(tmp_path)
        with editor.edited_file_context("pkg/sub/module.py") as edited:
            edited.set_contents("new\n")

        assert source.read_text(encoding="utf-8") == "new\n"
        assert list(package.iterdir()) == [source], "no temp file may be left beside the source"

    def test_save_writes_through_a_symlinked_source_file(self, tmp_path):
        """A symlinked source file must keep being written through to its target, as
        ``open(path, "w")`` did; the link itself must not be replaced by a regular file.
        """
        target_dir = tmp_path / "shared"
        target_dir.mkdir()
        target = target_dir / "shared.py"
        target.write_text("old\n", encoding="utf-8")
        project = tmp_path / "project"
        project.mkdir()
        link = project / "module.py"
        try:
            link.symlink_to(target)
        except OSError as e:
            pytest.skip(f"cannot create symlinks on this platform/permissions: {e}")

        editor = self._editor(project)
        with editor.edited_file_context("module.py") as edited:
            edited.set_contents("new\n")

        assert link.is_symlink(), "the source file's symlink must survive the edit"
        assert target.read_text(encoding="utf-8") == "new\n", "the edit must reach the link's target"

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Windows does not model POSIX permission bits; chmod only toggles the read-only flag"
    )
    def test_save_preserves_the_executable_bit(self, tmp_path):
        script = tmp_path / "run.sh"
        script.write_text("#!/bin/sh\necho old\n", encoding="utf-8")
        os.chmod(script, 0o755)

        editor = self._editor(tmp_path)
        with editor.edited_file_context("run.sh") as edited:
            edited.set_contents("#!/bin/sh\necho new\n")

        assert stat.S_IMODE(os.stat(script).st_mode) == 0o755

    def test_save_respects_the_configured_newline(self, tmp_path):
        source = tmp_path / "module.py"
        source.write_bytes(b"old\n")

        editor = self._editor(tmp_path, newline="\r\n")
        with editor.edited_file_context("module.py") as edited:
            edited.set_contents("a\nb\n")

        assert source.read_bytes() == b"a\r\nb\r\n"

    def test_save_respects_the_configured_encoding(self, tmp_path):
        source = tmp_path / "module.py"
        source.write_text("alt\n", encoding="latin-1")

        # newline is pinned so this test is about the encoding alone: LineEnding.NATIVE yields
        # newline=None, under which Python translates "\n" to os.linesep on write
        editor = self._editor(tmp_path, encoding="latin-1", newline="\n")
        with editor.edited_file_context("module.py") as edited:
            edited.set_contents("café\n")

        assert source.read_bytes() == "café\n".encode("latin-1")

    def test_save_with_native_newline_preserves_crlf_file(self, tmp_path):
        """Native line endings (newline=None) must not silently rewrite a CRLF file to the
        platform default: the file's dominant line ending is preserved. Without this, editing
        a CRLF source file on Linux converted its line endings (in full or in mixed form) to
        LF, which in practice forced a manual post-edit line-ending repair on Windows sources.
        """
        source = tmp_path / "module.mqh"
        source.write_bytes(b"a\r\nb\r\n")

        editor = self._editor(tmp_path, newline=None)
        with editor.edited_file_context("module.mqh") as edited:
            edited.set_contents("a\r\nb\r\nnew\r\n")

        assert source.read_bytes() == b"a\r\nb\r\nnew\r\n"

    def test_save_with_native_newline_preserves_lf_file(self, tmp_path):
        source = tmp_path / "module.py"
        source.write_bytes(b"a\nb\n")

        editor = self._editor(tmp_path, newline=None)
        with editor.edited_file_context("module.py") as edited:
            edited.set_contents("a\nb\nnew\n")

        # the file is LF-dominant, so the dominant ending is preserved regardless of the
        # platform: open(newline="\n") disables the platform translation even on Windows
        assert source.read_bytes() == b"a\nb\nnew\n"

    def test_save_translates_embedded_crlf_without_corruption(self, tmp_path):
        """Content lines that already end in CRLF (e.g. returned untranslated by a language
        server or the JetBrains plugin) must not be doubled to CRCRLF by the translation.
        """
        source = tmp_path / "module.mqh"
        source.write_bytes(b"a\r\nb\r\n")

        editor = self._editor(tmp_path, newline="\r\n")
        with editor.edited_file_context("module.mqh") as edited:
            edited.set_contents("a\r\nb\r\nnew\r\n")

        assert source.read_bytes() == b"a\r\nb\r\nnew\r\n"


class TestWriteFileAtomicNativeLineEnding:
    """``write_file_atomic`` is also called for files that do not exist yet (e.g. through
    ``create_text_file``); without a dominant ending to preserve, it must keep deferring to
    the platform default, exactly as a plain ``open(path, "w")`` did.
    """

    def test_new_file_gets_the_platform_default(self, tmp_path):
        target = tmp_path / "new.mqh"

        write_file_atomic(str(target), "a\nb\n", encoding="utf-8", newline=None)

        expected = b"a\nb\n" if sys.platform != "win32" else b"a\r\nb\r\n"
        assert target.read_bytes() == expected
