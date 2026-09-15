# SPDX-License-Identifier: MIT

"""Benchmark for the warm file buffer cache (see PR "perf(ls): warm file buffer cache").

Reproduces the notification-count and byte-volume numbers quoted in the PR description
by driving `open_file()` against a mocked LSP notification endpoint — no real language
server required.

The workload models Serena's symbolic editing flow (``EditedFileContext``): a sequence of
symbolic edits on the same file, where each edit opens the file through the
``open_file()`` context manager and closes it on exit. Without the warm buffer cache,
closing the context sends didClose, forcing a full didOpen — including the entire file
content — on the next edit. With the warm buffer cache, the didClose is deferred, so
consecutive reopens reuse the still-open LSP document (no notification when unchanged,
didChange when the file changed on disk).

Usage: uv run python scripts/profile_warm_buffers.py [num_edits] [file_lines]
"""

import os
import random
import sys
from pathlib import Path
from tempfile import mkdtemp
from unittest.mock import MagicMock

from solidlsp.ls import SolidLanguageServer


class _BenchmarkLanguageServer(SolidLanguageServer):
    def _start_server(self) -> None:
        raise AssertionError("Not used in this benchmark")

    def _create_base_initialize_params(self) -> dict:
        return {}


def make_server(tmp_path: Path, warm_ttl: float) -> tuple[SolidLanguageServer, dict[str, int]]:
    """
    Creates a minimal SolidLanguageServer with byte-counting LSP notifications.

    :param tmp_path: directory in which the benchmark file is created
    :param warm_ttl: the warm buffer TTL in seconds (0 disables warm reuse across edits)
    :return: tuple of (server, per-notification byte counter dict)
    """
    bytes_by_notification: dict[str, int] = {"didOpen": 0, "didChange": 0, "didClose": 0}

    def notify_factory(name: str):
        def handler(params: dict) -> None:
            if name == "didOpen":
                text = params["textDocument"]["text"]
            elif name == "didChange":
                text = params["contentChanges"][0]["text"]
            else:
                text = ""
            bytes_by_notification[name] += len(text)

        return handler

    server_mock = MagicMock()
    server_mock.notify = MagicMock()
    server_mock.notify.did_open_text_document.side_effect = notify_factory("didOpen")
    server_mock.notify.did_change_text_document.side_effect = notify_factory("didChange")
    server_mock.notify.did_close_text_document.side_effect = notify_factory("didClose")
    server_mock.is_running.return_value = True

    language_server = object.__new__(_BenchmarkLanguageServer)
    language_server.ls_id = "python"
    language_server.repository_root_path = str(tmp_path)
    language_server.server_started = True
    language_server.open_file_buffers = {}
    language_server._warm_file_buffers = {}
    language_server._warm_buffer_ttl = warm_ttl
    language_server._encoding = "utf-8"
    language_server.language_id = "python"
    language_server.server = server_mock
    return language_server, bytes_by_notification


def generate_synthetic_content(num_lines: int) -> str:
    """Generates synthetic pseudo-code content with a fixed seed (no real-world code)."""
    rng = random.Random(5678)
    return "\n".join(f"    local_variable_{i} = value_{rng.randint(0, 999)}  # line {i}" for i in range(num_lines)) + "\n"


def run_edit_sequence(num_edits: int, file_lines: int, warm_ttl: float) -> tuple[dict[str, int], dict[str, int], int]:
    """
    Simulates `num_edits` sequential symbolic edits on the same file, each going through
    the full open_file() context manager cycle. Every second edit modifies the file on disk
    (as a real symbolic edit would persist its result), the others are pure reopens.

    :return: (notification counts, byte volume per notification type, file size in bytes)
    """
    tmp_path = Path(mkdtemp())
    file_path = tmp_path / "sample.py"
    content = generate_synthetic_content(file_lines)
    file_path.write_text(content, encoding="utf-8")
    file_size = file_path.stat().st_size

    server, bytes_by_notification = make_server(tmp_path, warm_ttl)
    counts: dict[str, int] = {"didOpen": 0, "didChange": 0, "didClose": 0}

    method_by_key = {"didOpen": "did_open_text_document", "didChange": "did_change_text_document", "didClose": "did_close_text_document"}
    for name in counts:
        mock_fn = getattr(server.server.notify, method_by_key[name])
        base = mock_fn.side_effect

        def wrapped(params: dict, _name: str = name, _base=base) -> None:
            counts[_name] += 1
            _base(params)

        mock_fn.side_effect = wrapped

    for i in range(num_edits):
        with server.open_file("sample.py") as fb:
            if i % 2 == 0:  # simulate a symbolic edit every other iteration
                fb.contents = fb.contents + f"  # edit {i}\n"
                file_path.write_text(fb.contents, encoding="utf-8")
                future = file_path.stat().st_mtime + (i + 1) * 10.0
                os.utime(file_path, (future, future))  # make the change visible on disk
    return counts, bytes_by_notification, file_size


def main() -> None:
    num_edits = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    file_lines = int(sys.argv[2]) if len(sys.argv) > 2 else 2000

    counts_upstream, bytes_upstream, file_size = run_edit_sequence(num_edits, file_lines, warm_ttl=0.0)
    counts_warm, bytes_warm, _ = run_edit_sequence(num_edits, file_lines, warm_ttl=30.0)

    total_bytes = lambda b: sum(b.values())
    print(f"workload: {num_edits} sequential edits on the same {file_lines}-line file ({file_size:,} bytes per full read)")
    print()
    print("notification counts (fewer didOpen/didClose is better):")
    print(f"  upstream (no warm cache): {counts_upstream}")
    print(f"  warm file buffer cache:   {counts_warm}")
    print()
    up_total = total_bytes(bytes_upstream)
    warm_total = total_bytes(bytes_warm)
    print(f"bytes sent to the LS (didOpen+didChange payloads): upstream={up_total:,}  warm={warm_total:,}")
    print(f"bytes avoided: {up_total - warm_total:,} ({100.0 * (up_total - warm_total) / up_total:.0f}% reduction)")


if __name__ == "__main__":
    main()
