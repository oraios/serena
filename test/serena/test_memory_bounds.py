# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from serena.constants import LOG_MESSAGES_BUFFER_SIZE
from serena.project import Project
from serena.util.logging import MemoryLogHandler


class MemoryBoundsTest(unittest.TestCase):
    def test_later_alias_keeps_files_ignored_through_first_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "z_target").mkdir()
            (root / "z_target" / "leaf.py").write_text("pass\n")
            (root / "a_alias").symlink_to(root / "z_target", target_is_directory=True)
            project = SimpleNamespace(
                project_root=directory,
                is_ignored_path=lambda path, **kwargs: str(path).endswith("a_alias/leaf.py"),
            )
            self.assertEqual(Project.gather_source_files(project), ["z_target/leaf.py"])

    def test_directory_aliases_do_not_duplicate_source_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(9):
                (root / str(index)).mkdir()
            for index in range(8):
                for alias in ("a", "b"):
                    (root / str(index) / alias).symlink_to(root / str(index + 1), target_is_directory=True)
            (root / "8" / "leaf.py").write_text("pass\n")
            project = SimpleNamespace(project_root=directory, is_ignored_path=lambda *args, **kwargs: False)
            paths = Project.gather_source_files(project, "0")
            self.assertEqual(len(paths), 1)
            self.assertEqual(os.path.realpath(root / paths[0]), os.path.realpath(root / "8" / "leaf.py"))

    def test_later_alias_keeps_descendants_ignored_through_first_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "z_target" / "child").mkdir(parents=True)
            (root / "z_target" / "child" / "leaf.py").write_text("pass\n")
            (root / "a_alias").symlink_to(root / "z_target", target_is_directory=True)
            project = SimpleNamespace(
                project_root=directory,
                is_ignored_path=lambda path, **kwargs: str(path).endswith("a_alias/child"),
            )
            self.assertEqual(Project.gather_source_files(project), ["z_target/child/leaf.py"])

    def test_directory_cycle_terminates_and_keeps_distinct_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "child").mkdir()
            (root / "first.py").write_text("pass\n")
            (root / "child" / "second.py").write_text("pass\n")
            (root / "child" / "parent").symlink_to(root, target_is_directory=True)
            project = SimpleNamespace(project_root=directory, is_ignored_path=lambda *args, **kwargs: False)
            self.assertEqual(set(Project.gather_source_files(project)), {"first.py", "child/second.py"})

    def test_ignored_directory_is_not_traversed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ignored").mkdir()
            (root / "ignored" / "hidden.py").write_text("pass\n")
            (root / "visible.py").write_text("pass\n")
            project = SimpleNamespace(
                project_root=directory,
                is_ignored_path=lambda path, **kwargs: Path(path).name == "ignored",
            )
            self.assertEqual(Project.gather_source_files(project), ["visible.py"])

    def test_logging_delivers_messages_without_overload(self):
        delivered = threading.Event()
        handler = MemoryLogHandler()
        handler.add_emit_callback(lambda message: delivered.set())
        try:
            handler.emit(logging.LogRecord("test", logging.INFO, __file__, 1, "delivered", (), None))
            self.assertTrue(delivered.wait(2))
            self.assertIn("delivered", handler.get_log_messages().messages[0])
        finally:
            handler._stop_event.set()
            handler.worker_thread.join(2)
            handler.close()

    def test_logging_backlog_is_bounded_when_callback_stalls(self):
        entered = threading.Event()
        release = threading.Event()
        handler = MemoryLogHandler()

        def stalled_callback(message):
            entered.set()
            release.wait(5)

        handler.add_emit_callback(stalled_callback)
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "message", (), None)
        try:
            handler.emit(record)
            self.assertTrue(entered.wait(2))
            for _ in range(LOG_MESSAGES_BUFFER_SIZE + 10):
                handler.emit(record)
            self.assertLessEqual(handler._log_queue.qsize(), LOG_MESSAGES_BUFFER_SIZE)
        finally:
            handler._stop_event.set()
            release.set()
            handler.worker_thread.join(2)
            handler.close()


if __name__ == "__main__":
    unittest.main()
